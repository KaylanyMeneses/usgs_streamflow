"""Forecast task shared by the three models: origins, horizons, targets, inputs cut at the
origin and baselines.

An *origin* is the last day the model may see; a *horizon* h is how many days after the origin
the predicted day is (target day = origem + h). Origins are placed every ``origin_step`` days
inside each block (validacao, calibracao, teste); the first one is the last day before the block,
so its first target is the first day of the block. Targets never leave that block, so the
blocks keep their roles:

- validacao: choose hyperparameters with the forecast error;
- calibracao: conformal factor per horizon (wider intervals for longer horizons);
- teste: final metrics, once.

Everything is deterministic given (serie, ForecastConfig): models built from the same base and
the same config are evaluated on exactly the same origins and targets. Rules at each origin:
the model reads only visible days (visivel = 1) up to the origin; targets are days with a value
and without an anomaly label (``avaliar = 1``), like the reconstruction metrics.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model_inputs import seasonal_features

FORECAST_COLUMNS = ["sensor_id", "origem", "h", "media", "q025", "q975"]
SPLITS = ("validacao", "calibracao", "teste")


@dataclass(frozen=True)
class ForecastConfig:
    """Forecast task. ``horizons`` and ``origin_step`` can be changed freely; keep the default
    for the comparison between models and use other values as additional analyses."""

    horizons: tuple[int, ...] = (1, 7, 30)   # days after the origin, e.g. tuple(range(1, 31))
    origin_step: int = 30                    # days between two consecutive origins
    splits: tuple[str, ...] = SPLITS

    def __post_init__(self) -> None:
        horizons = tuple(sorted({int(h) for h in self.horizons}))
        if not horizons or horizons[0] < 1:
            raise ValueError("horizons deve ter inteiros >= 1.")
        if int(self.origin_step) < 1:
            raise ValueError("origin_step deve ser >= 1.")
        unknown = set(self.splits) - set(SPLITS)
        if unknown:
            raise ValueError(f"Blocos desconhecidos em splits: {sorted(unknown)}. Use {SPLITS}.")
        object.__setattr__(self, "horizons", horizons)
        object.__setattr__(self, "origin_step", int(self.origin_step))
        object.__setattr__(self, "splits", tuple(self.splits))


def _blocks(serie: pd.DataFrame) -> pd.DataFrame:
    return serie.groupby("split")["t"].agg(inicio="min", fim="max")


def forecast_origins(serie: pd.DataFrame, cfg: ForecastConfig = ForecastConfig()) -> pd.DataFrame:
    """One row per (split, origem): origens a cada ``origin_step`` dias dentro de cada bloco."""
    blocks = _blocks(serie)
    dates = serie.drop_duplicates("t").set_index("t")["data"]
    rows = []
    for split in cfg.splits:
        start, end = blocks.loc[split, "inicio"], blocks.loc[split, "fim"]
        for origem in range(start - 1, end - cfg.horizons[0] + 1, cfg.origin_step):
            rows.append({"split": split, "origem": origem, "data_origem": dates.get(origem)})
    return pd.DataFrame(rows)


def forecast_targets(serie: pd.DataFrame, cfg: ForecastConfig = ForecastConfig()) -> pd.DataFrame:
    """One row per (sensor_id, origem, h) whose target day t = origem + h stays inside the block.

    ``avaliar`` = 1 when the target day has a value and no anomaly label (enters the metrics).
    ``y``/``y_bruto`` are the true values: for evaluation only, never a model input.
    """
    origins = forecast_origins(serie, cfg)
    end = _blocks(serie)["fim"]
    grid = origins.merge(pd.DataFrame({"h": cfg.horizons}), how="cross")
    grid["t"] = grid["origem"] + grid["h"]
    grid = grid[grid["t"] <= grid["split"].map(end)]
    cols = ["sensor_id", "t", "data", "y", "y_bruto", "observado", "anomalia", "aprovacao"]
    out = grid.drop(columns="data_origem").merge(serie[cols], on="t", how="left")
    out["avaliar"] = ((out["observado"] == 1) & (out["anomalia"] == 0)).astype(int)
    out = out.drop(columns=["observado", "anomalia"])
    order = ["sensor_id", "split", "origem", "h", "t", "data", "y", "y_bruto", "aprovacao", "avaliar"]
    return out[order].sort_values(["sensor_id", "origem", "h"]).reset_index(drop=True)


def forecast_summary(targets: pd.DataFrame) -> pd.DataFrame:
    """Origins and evaluated targets per block and horizon (check that every horizon has data)."""
    return (targets.groupby(["split", "h"], sort=False)
            .agg(origens=("origem", "nunique"), alvos=("avaliar", "size"), avaliados=("avaliar", "sum"))
            .reset_index())


def check_forecast_output(out: pd.DataFrame) -> pd.DataFrame:
    """Validate a forecast output (one row per sensor_id, origem, h)."""
    missing = set(FORECAST_COLUMNS).difference(out.columns)
    if missing:
        raise ValueError(f"Saída de forecast sem colunas: {sorted(missing)}")
    if out.duplicated(["sensor_id", "origem", "h"]).any():
        raise ValueError("A saída de forecast tem mais de uma linha por (sensor_id, origem, h).")
    if (out["q025"] > out["q975"]).any():
        raise ValueError("Há intervalos com q025 > q975.")
    return out.assign(sensor_id=out["sensor_id"].astype(str))


# ---------------------------------------------------------------- inputs cut at the origin

def context_until(table: pd.DataFrame, origem: int) -> pd.DataFrame:
    """Rows the model may read at the origin: visible days with t <= origem (any table that has
    sensor_id, t, y and visivel: the serie or the entradas of the GP)."""
    return table[(table["t"] <= origem) & (table["visivel"] == 1)]


def gp_forecast_inputs(table: pd.DataFrame, sensor_id: str, origem: int, horizons) -> dict:
    """Model 1, one station: context up to the origin and the days to predict."""
    ctx = context_until(table[table["sensor_id"] == sensor_id], origem).sort_values("t")
    return {"t_context": ctx["t"].to_numpy(float), "y_context": ctx["y"].to_numpy(float),
            "t_pred": origem + np.asarray(horizons, float), "h": np.asarray(horizons, int)}


def gp_global_forecast_inputs(table: pd.DataFrame, origem: int, horizons, stations=None) -> dict:
    """Model 1, several stations together: X = [t, station index], as in gp_global_arrays."""
    sensors = sorted(table["sensor_id"].unique()) if stations is None else list(stations)
    idx = {sid: i for i, sid in enumerate(sensors)}
    ctx = context_until(table[table["sensor_id"].isin(idx)], origem)
    ctx = ctx.assign(estacao=ctx["sensor_id"].map(idx)).sort_values(["estacao", "t"])
    h = np.asarray(horizons, int)
    X_pred = np.column_stack([np.tile(origem + h, len(sensors)), np.repeat(np.arange(len(sensors)), len(h))])
    return {"sensors": sensors, "X_context": ctx[["t", "estacao"]].to_numpy(float),
            "y_context": ctx["y"].to_numpy(float), "X_pred": X_pred.astype(float),
            "h": np.tile(h, len(sensors))}


def rgp_forecast_inputs(rgp: dict, origem: int, horizons) -> dict:
    """Model 2: sequences cut at the origin (the RNN never reads days after it).

    ``rgp`` comes from rgp_inputs / rgp_arrays (optionally with add_seasonal_channels); column j
    of the (S, T) arrays is day t = j. Calendar features of the predicted days are known in
    advance and returned in ``sazonal_pred`` when present.
    """
    T = rgp["y"].shape[1]
    if not 0 <= origem < T:
        raise ValueError(f"origem {origem} fora da sequência (0..{T - 1}).")
    h = np.asarray(horizons, int)
    out = {"sensors": rgp["sensors"], "rnn_in": rgp["rnn_in"][:, : origem + 1],
           "y": rgp["y"][:, : origem + 1], "mask": rgp["mask"][:, : origem + 1],
           "t_pred": origem + h, "h": h}
    if "sazonal" in rgp:
        keep = out["t_pred"] < T
        out["sazonal_pred"] = rgp["sazonal"][out["t_pred"][keep]]
    return out


def gplvm_forecast_inputs(seq: dict, origem: int, horizons) -> dict:
    """Model 3 (option b, latent dynamics): windows up to the origin and where the targets fall.

    ``seq`` comes from gplvm_sequence / gplvm_sequence_arrays. Context = windows that start on or
    before the origin; cells after the origin are masked (mask = 0, Y = 0). For each horizon,
    ``alvos`` gives the future window (``janela``) and the position inside it (``posicao``).
    """
    t_start = seq["t_inicio"]
    n_ctx = int((t_start <= origem).sum())
    if n_ctx == 0:
        raise ValueError(f"Nenhuma janela começa até a origem {origem}.")
    t_idx = seq["t_idx"][:, :n_ctx]
    after = t_idx > origem
    mask = np.where(after, 0.0, seq["mask"][:, :n_ctx])
    Y = np.where(after, 0.0, seq["Y"][:, :n_ctx])
    w = seq["Y"].shape[2]
    offset = int(t_start[0])
    t_pred = origem + np.asarray(horizons, int)
    alvos = pd.DataFrame({"h": np.asarray(horizons, int), "t": t_pred,
                          "janela": (t_pred - offset) // w, "posicao": (t_pred - offset) % w})
    return {"sensors": seq["sensors"], "Y": Y, "mask": mask, "t_idx": t_idx,
            "sazonal": seq["sazonal"][:n_ctx], "alvos": alvos,
            "sazonal_futuro": seq["sazonal"][n_ctx:]}


# ---------------------------------------------------------------- baselines

def _visible_matrix(serie: pd.DataFrame) -> pd.DataFrame:
    y = serie["y"].where(serie["visivel"] == 1)
    return serie.assign(y=y).pivot(index="sensor_id", columns="t", values="y")


def persistence_forecast(serie: pd.DataFrame, targets: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Baseline: the last visible value up to the origin, repeated for every horizon.

    The interval comes from the training errors of the same horizon: quantiles, per station, of
    y[t + h] - y[t] over pairs of visible training days.
    """
    Y = _visible_matrix(serie)
    last = Y.ffill(axis=1)
    train_end = int(serie.loc[serie["split"] == "treino", "t"].max())
    tr = Y.loc[:, :train_end].to_numpy(float)
    rows = []
    for h in sorted(targets["h"].unique()):
        diff = tr[:, h:] - tr[:, :-h]
        lo = np.nanquantile(diff, alpha / 2, axis=1)
        hi = np.nanquantile(diff, 1 - alpha / 2, axis=1)
        rows.append(pd.DataFrame({"sensor_id": Y.index, "h": h, "lo": lo, "hi": hi}))
    spread = pd.concat(rows, ignore_index=True)
    keys = targets[["sensor_id", "origem", "h"]].drop_duplicates()
    stacked = last.stack().rename("media").rename_axis(["sensor_id", "origem"]).reset_index()
    out = keys.merge(stacked, on=["sensor_id", "origem"], how="left").merge(spread, on=["sensor_id", "h"])
    out["q025"], out["q975"] = out["media"] + out["lo"], out["media"] + out["hi"]
    return out[FORECAST_COLUMNS].dropna(subset=["media"]).reset_index(drop=True)


def climatology_forecast(serie: pd.DataFrame, targets: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Baseline: mean of the same day of the year in the visible training days, per station.
    The interval comes from the quantiles of the training residuals. Ignores the origin."""
    fit = serie[(serie["split"] == "treino") & (serie["visivel"] == 1)]
    fit = fit.assign(doy=fit["data"].dt.dayofyear.clip(upper=365))
    clim = fit.groupby(["sensor_id", "doy"])["y"].mean().rename("media").reset_index()
    resid = fit.merge(clim, on=["sensor_id", "doy"]).assign(r=lambda d: d["y"] - d["media"])
    q = resid.groupby("sensor_id")["r"].quantile([alpha / 2, 1 - alpha / 2]).unstack()
    q.columns = ["lo", "hi"]
    out = targets[["sensor_id", "origem", "h", "data"]].assign(doy=lambda d: d["data"].dt.dayofyear.clip(upper=365))
    out = out.merge(clim, on=["sensor_id", "doy"], how="left").merge(q, left_on="sensor_id", right_index=True)
    out["q025"], out["q975"] = out["media"] + out["lo"], out["media"] + out["hi"]
    return out[FORECAST_COLUMNS].dropna(subset=["media"]).reset_index(drop=True)


__all__ = [
    "FORECAST_COLUMNS", "ForecastConfig", "check_forecast_output", "climatology_forecast",
    "context_until", "forecast_origins", "forecast_summary", "forecast_targets",
    "gp_forecast_inputs", "gp_global_forecast_inputs", "gplvm_forecast_inputs",
    "persistence_forecast", "rgp_forecast_inputs", "seasonal_features",
]
