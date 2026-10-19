"""Shared modeling table: labels, chronological splits, station selection and normalization.

Order matters to avoid leakage:
1. labels (observado, aprovacao, qualificador, anomalia) from the raw values and USGS codes;
2. chronological split by calendar dates (same cut dates for every station);
3. station selection using statistics of the training block only;
4. hidden evaluation points inside validacao / calibracao / teste;
5. per-station normalization fitted on visible training points only.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


# USGS qualifiers that flag a measurement problem (case-insensitive). The OGC API returns them
# in upper case, joined by ";" (e.g. "ESTIMATED;ICE", "EQUIP;ESTIMATED", "BACKWATER;ESTIMATED;REVISED").
# ESTIMATED, REVISED and FORCEINTERPOLATION are data-processing notes, not problems: they do not match.
PROBLEM_QUALIFIERS = r"\b(?:eqp|equip\w*|ice|bkw|backwater|mnt|maint\w*|fld|flood\w*)\b"
SPLITS = ("treino", "validacao", "calibracao", "teste")
COLUMNS = [
    "sensor_id", "t", "data", "split", "y_bruto", "y",
    "observado", "escondido_aval", "visivel", "aprovacao", "qualificador", "anomalia",
]


@dataclass(frozen=True)
class SelectionConfig:
    """Station-selection conditions (computed on the training block only)."""

    n_sensors: int = 10                        # 1 = univariate case
    min_completeness: float = 0.95             # fraction of training days with a value
    max_zero_frac: float = 0.05                # drops intermittent rivers
    candidates: tuple[str, ...] | None = None  # e.g. neighbouring stations from pares_nldi_*.csv
    seed: int = 42


@dataclass(frozen=True)
class SplitConfig:
    """Chronological blocks and evaluation masking."""

    fracs: tuple[float, float, float, float] = (0.60, 0.15, 0.10, 0.15)  # order of SPLITS
    hidden_frac: float = 0.10       # share of eligible days hidden in each non-training block
    hidden_block_len: int = 1       # 1 = isolated days; >1 = runs of consecutive days (harder gaps)
    log_transform: bool = True      # log1p before standardizing (discharge is heavily skewed)
    seed: int = 42


def add_labels(full: pd.DataFrame) -> pd.DataFrame:
    """Rename to the shared format and derive observado, aprovacao, qualificador and anomalia."""
    df = full.rename(columns={
        "monitoring_location_id": "sensor_id", "date": "data", "value_cfs": "y_bruto",
    }).sort_values(["sensor_id", "data"], ignore_index=True)
    df["sensor_id"] = df["sensor_id"].astype(str)
    df["t"] = df.groupby("sensor_id").cumcount()
    df["observado"] = df["y_bruto"].notna().astype(int)
    # aprovacao: "Approved" / "Provisional" ("" when there is no value)
    # qualificador: USGS qualifiers such as "Ice" or "Equipment" ("" when none; several joined by ";")
    df["aprovacao"] = df.get("approval_status", pd.Series("", index=df.index)).fillna("").astype(str)
    df["qualificador"] = df.get("qualifier", pd.Series("", index=df.index)).fillna("").astype(str)
    df["anomalia"] = df["qualificador"].str.contains(
        PROBLEM_QUALIFIERS, case=False, regex=True).astype(int)
    return df


def assign_splits(df: pd.DataFrame, cfg: SplitConfig) -> pd.DataFrame:
    """Chronological blocks from calendar dates only, identical for every station."""
    if len(cfg.fracs) != len(SPLITS) or not np.isclose(sum(cfg.fracs), 1.0):
        raise ValueError(f"fracs precisa ter {len(SPLITS)} valores somando 1.")
    dates = np.sort(df["data"].unique())
    edges = [dates[int(c * len(dates))] for c in np.cumsum(cfg.fracs)[:-1]]
    df = df.copy()
    df["split"] = pd.cut(
        df["data"], bins=[pd.Timestamp.min, *edges, pd.Timestamp.max],
        right=False, labels=SPLITS,
    ).astype(str)
    return df


def select_stations(df: pd.DataFrame, cfg: SelectionConfig) -> list[str]:
    """Pick cfg.n_sensors stations that pass the conditions on the training block."""
    train = df[df["split"] == "treino"]
    stats = train.groupby("sensor_id").agg(
        completeness=("observado", "mean"),
        zero_frac=("y_bruto", lambda v: v.eq(0).sum() / max(v.notna().sum(), 1)),
        has_negative=("y_bruto", lambda v: bool((v < 0).any())),
    )
    ok = stats[
        (stats["completeness"] >= cfg.min_completeness)
        & (stats["zero_frac"] <= cfg.max_zero_frac)
        & ~stats["has_negative"]
    ]
    if cfg.candidates is not None:
        ok = ok[ok.index.isin(cfg.candidates)]
    if len(ok) < cfg.n_sensors:
        raise ValueError(f"Só {len(ok)} estações passam nos filtros; pedido: {cfg.n_sensors}.")
    return sorted(ok.sample(n=cfg.n_sensors, random_state=cfg.seed).index)


def hide_evaluation_points(df: pd.DataFrame, cfg: SplitConfig) -> pd.DataFrame:
    """Hide observed, unflagged days outside training; the true value stays in y_bruto."""
    rng = np.random.default_rng(cfg.seed)
    df = df.copy()
    df["escondido_aval"] = 0
    eligible = (df["split"] != "treino") & (df["observado"] == 1) & (df["anomalia"] == 0)
    length = max(cfg.hidden_block_len, 1)
    for _, idx in df[eligible].groupby(["sensor_id", "split"]).groups.items():
        idx = np.asarray(idx)
        n_starts = int(cfg.hidden_frac * len(idx) / length)
        if n_starts == 0:
            continue
        starts = rng.choice(idx, size=n_starts, replace=False)
        rows = np.unique((starts[:, None] + np.arange(length)).ravel())
        rows = rows[np.isin(rows, idx)]  # keep runs inside the same station/block and eligible
        df.loc[rows, "escondido_aval"] = 1
    df["visivel"] = ((df["observado"] == 1) & (df["escondido_aval"] == 0)).astype(int)
    return df


def normalize(df: pd.DataFrame, cfg: SplitConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-station standardization fitted on visible training points only."""
    z = np.log1p(df["y_bruto"]) if cfg.log_transform else df["y_bruto"]
    fit = (df["split"] == "treino") & (df["visivel"] == 1)
    stats = z[fit].groupby(df.loc[fit, "sensor_id"]).agg(["mean", "std"])
    df = df.copy()
    df["y"] = (z - df["sensor_id"].map(stats["mean"])) / df["sensor_id"].map(stats["std"])
    return df, stats


def prepare_model_dataset(
    full: pd.DataFrame,
    selection: SelectionConfig = SelectionConfig(),
    splits: SplitConfig = SplitConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the shared table from the full daily calendar (output of complete_daily_calendar)."""
    df = assign_splits(add_labels(full), splits)
    df = df[df["sensor_id"].isin(select_stations(df, selection))]
    df = hide_evaluation_points(df, splits)
    df, stats = normalize(df, splits)
    return df[COLUMNS].reset_index(drop=True), stats


def split_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per split: date range, rows, visible/hidden points, flagged anomalies, provisional share."""
    provisional = df["aprovacao"].str.contains("provisional", case=False, regex=False)
    return (
        df.assign(provisorio=provisional.astype(int))
        .groupby("split", sort=False)
        .agg(
            inicio=("data", "min"), fim=("data", "max"), linhas=("t", "size"),
            visiveis=("visivel", "sum"), escondidos=("escondido_aval", "sum"),
            anomalias=("anomalia", "sum"), provisorios=("provisorio", "sum"),
        )
    )
