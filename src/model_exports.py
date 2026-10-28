"""Save and load the input of each model as Parquet, next to the shared modeling table.

Layout (``base`` is the NOME of the table saved by 02_serie_modelos.ipynb):

    data/exports/<base>.parquet                      shared table (serie)
    data/exports/<base>/modelo1_gp/entradas.parquet  one row per (station, day)
    data/exports/<base>/modelo2_rgp/entradas.parquet one row per (station, day)
    data/exports/<base>/modelo3_gplvm/janelas.parquet one row per window
    data/exports/<base>/<modelo>/config.json         choices used to build the table

Every table keeps ``sensor_id`` and ``t``, so the arrays can be rebuilt and the model output
mapped back to the shared table. gp_arrays, rgp_arrays and gplvm_arrays return exactly what
gp_inputs, rgp_inputs and gplvm_inputs return; gp_global_arrays gives the GP input of several
stations together, with X = [t, station index]. Anomaly labels are not saved here: they stay in the
shared table, which is what the evaluation reads.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import EXPORT_ROOT
from .model_inputs import gp_inputs, gplvm_inputs, rgp_inputs

FILES = {
    "modelo1_gp": "entradas.parquet",
    "modelo2_rgp": "entradas.parquet",
    "modelo3_gplvm": "janelas.parquet",
}
GPLVM_FIELDS = (("t", "t_idx"), ("y", "Y"), ("mask", "mask"), ("true", "Y_true"), ("hidden", "hidden"))


def inputs_dir(base: str, modelo: str) -> Path:
    if modelo not in FILES:
        raise ValueError(f"Modelo desconhecido: {modelo!r}. Use um de {sorted(FILES)}.")
    return EXPORT_ROOT / base / modelo


def save_inputs(table: pd.DataFrame, base: str, modelo: str, config: dict) -> Path:
    """Save a model input table and its config. If it already exists with the same config,
    nothing is rewritten; with a different config, stop instead of mixing inputs."""
    if not (EXPORT_ROOT / f"{base}.parquet").exists():
        raise FileNotFoundError(f"Base {base!r} não encontrada em {EXPORT_ROOT}. Rode o 02_serie_modelos.ipynb.")
    folder = inputs_dir(base, modelo)
    path, config_path = folder / FILES[modelo], folder / "config.json"
    config = json.loads(json.dumps({"base": base, "modelo": modelo, **config}))   # tuples -> lists
    if path.exists():
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        if saved != config:
            raise ValueError(f"Já existe uma entrada de {modelo} para a base {base!r} com outras escolhas.\n"
                             f"Salva: {saved}\nAtual: {config}\nApague a pasta {folder} para gerar de novo.")
        print(f"Entrada já existente, mantida: {path}")
        return path
    folder.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path, index=False)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Entrada salva em {path}")
    return path


def load_inputs(base: str, modelo: str) -> tuple[pd.DataFrame, dict]:
    """Read a saved model input table and its config."""
    folder = inputs_dir(base, modelo)
    path = folder / FILES[modelo]
    if not path.exists():
        raise FileNotFoundError(f"Entrada não encontrada: {path}. Rode o notebook de entradas do {modelo}.")
    return pd.read_parquet(path), json.loads((folder / "config.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Modelo 1: GP Student-t

def gp_table(serie: pd.DataFrame) -> pd.DataFrame:
    """One row per (station, day). ``ajuste`` = 1 on the days that fit the model (visible
    training days); ``visivel`` = context the model may read; ``escondido_aval`` = hidden days,
    whose ``y`` is for evaluation only."""
    out = serie[["sensor_id", "t", "data", "split", "y", "visivel", "escondido_aval"]].copy()
    out.insert(5, "ajuste", ((out["split"] == "treino") & (out["visivel"] == 1)).astype(int))
    return out.sort_values(["sensor_id", "t"]).reset_index(drop=True)


def gp_arrays(table: pd.DataFrame, sensor_id: str) -> dict:
    """Arrays of one station, same keys as gp_inputs."""
    return gp_inputs(table, sensor_id)


def gp_global_arrays(table: pd.DataFrame, stations: list[str] | None = None) -> dict:
    """Arrays of several stations together, for a global GP (e.g. multitask kernel
    K_time x IndexKernel(station)). Same structure as gp_inputs, but every X has two columns,
    [t, station index], and ``sensors`` gives the station of each index.

    ``stations`` selects and orders the stations (default: all in the table, sorted).
    """
    sensors = sorted(table["sensor_id"].unique()) if stations is None else list(stations)
    missing = set(sensors) - set(table["sensor_id"].unique())
    if missing:
        raise ValueError(f"Estações fora da tabela: {sorted(missing)[:5]}")
    idx = {sid: i for i, sid in enumerate(sensors)}
    s = table[table["sensor_id"].isin(idx)].assign(estacao=lambda d: d["sensor_id"].map(idx))
    s = s.sort_values(["estacao", "t"])

    def xy(d):
        return d[["t", "estacao"]].to_numpy(float), d["y"].to_numpy(float)

    vis = s[s["visivel"] == 1]
    X_train, y_train = xy(s[s["ajuste"] == 1])
    X_context, y_context = xy(vis)
    splits = {}
    for name, g in s.groupby("split", sort=False):
        X_visible, y_visible = xy(g[g["visivel"] == 1])
        X_hidden, y_hidden = xy(g[g["escondido_aval"] == 1])
        splits[name] = {"X_all": xy(g)[0], "X_visible": X_visible, "y_visible": y_visible,
                        "X_hidden": X_hidden, "y_hidden": y_hidden}
    return {
        "sensors": sensors,
        "X_train": X_train, "y_train": y_train,
        "X_context": X_context, "y_context": y_context,
        "X_all": xy(s)[0],
        "splits": splits,
    }


# ---------------------------------------------------------------- Modelo 2: RGP-t

def rgp_table(serie: pd.DataFrame) -> pd.DataFrame:
    """One row per (station, day). ``y_entrada`` = value read by the RNN (0 where not visible);
    ``visivel`` = mask; ``y_true`` = real value (NaN without value), for evaluation only."""
    out = serie[["sensor_id", "t", "data", "split", "visivel", "escondido_aval"]].copy()
    out.insert(4, "y_entrada", serie["y"].where(serie["visivel"] == 1, 0.0).fillna(0.0))
    out["y_true"] = serie["y"]
    return out.sort_values(["sensor_id", "t"]).reset_index(drop=True)


def rgp_arrays(table: pd.DataFrame) -> dict:
    """Arrays of all stations, same keys as rgp_inputs."""
    return rgp_inputs(table.rename(columns={"y_true": "y"}))


# ---------------------------------------------------------------- Modelo 3: Bayesian GPLVM

def gplvm_table(serie: pd.DataFrame, window: int = 7, max_missing: float = 0.5) -> pd.DataFrame:
    """One row per window: sensor_id, split and, for each position k of the window,
    t_k (day), y_k (value, 0 where not visible), mask_k, true_k (real value) and hidden_k."""
    gl = gplvm_inputs(serie, window=window, max_missing=max_missing)
    out = gl["meta"].copy()
    for prefix, key in GPLVM_FIELDS:
        arr = gl[key]
        for k in range(window):
            out[f"{prefix}_{k}"] = arr[:, k]
    return out


def gplvm_arrays(table: pd.DataFrame) -> dict:
    """Windows of all blocks, same keys as gplvm_inputs (use select_split for one block)."""
    window = sum(c.startswith("y_") and c[2:].isdigit() for c in table.columns)
    arrays = {key: table[[f"{prefix}_{k}" for k in range(window)]].to_numpy()
              for prefix, key in GPLVM_FIELDS}
    arrays["t_idx"] = arrays["t_idx"].astype(int)
    for key in ("Y", "mask", "Y_true", "hidden"):
        arrays[key] = arrays[key].astype(float)
    arrays["meta"] = table[["sensor_id", "split"]].reset_index(drop=True)
    return arrays
