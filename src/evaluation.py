"""Shared evaluation: model output format, reconstruction metrics and anomaly detection metrics.

Every model returns one row per (sensor_id, t) with the columns in OUTPUT_COLUMNS
(values in the ``y`` scale). Metrics are computed only on the requested split
(normally ``teste``); thresholds and conformal factors come from ``calibracao``.
"""

import numpy as np
import pandas as pd


OUTPUT_COLUMNS = ["sensor_id", "t", "media", "q025", "q975", "escore"]


def check_output(out: pd.DataFrame) -> pd.DataFrame:
    """Validate a model output and return it with sensor_id as string."""
    missing = set(OUTPUT_COLUMNS).difference(out.columns)
    if missing:
        raise ValueError(f"Saída do modelo sem colunas: {sorted(missing)}")
    if out.duplicated(["sensor_id", "t"]).any():
        raise ValueError("A saída tem mais de uma linha por (sensor_id, t).")
    if (out["q025"] > out["q975"]).any():
        raise ValueError("Há intervalos com q025 > q975.")
    return out.assign(sensor_id=out["sensor_id"].astype(str))


def _join(serie: pd.DataFrame, out: pd.DataFrame) -> pd.DataFrame:
    return serie.merge(check_output(out), on=["sensor_id", "t"], how="left", validate="one_to_one")


def to_cfs(values: pd.Series, sensor_id: pd.Series, stats: pd.DataFrame, log_transform: bool = True):
    """Undo the per-station normalization (y scale -> ft3/s)."""
    z = values * sensor_id.map(stats["std"]) + sensor_id.map(stats["mean"])
    return np.expm1(z) if log_transform else z


# ---------------------------------------------------------------- reconstruction
def reconstruction_metrics(serie, out, split="teste", stats=None, alpha=0.05) -> pd.Series:
    """Errors on hidden points (escondido_aval = 1) of one split.

    With ``stats`` the errors are reported in ft3/s; otherwise in the ``y`` scale.
    interval_score is the Winkler score of the (1 - alpha) interval: width plus a
    penalty when the true value falls outside (lower is better).
    """
    d = _join(serie, out)
    d = d[(d["split"] == split) & (d["escondido_aval"] == 1)].dropna(subset=["media"])
    if d.empty:
        raise ValueError(f"Não há pontos escondidos com previsão no split {split!r}.")
    if stats is None:
        y, mu, lo, hi = d["y"], d["media"], d["q025"], d["q975"]
    else:
        y = d["y_bruto"]
        mu, lo, hi = (to_cfs(d[c], d["sensor_id"], stats) for c in ("media", "q025", "q975"))
    err = y - mu
    width = hi - lo
    penalty = (2 / alpha) * ((lo - y).clip(lower=0) + (y - hi).clip(lower=0))
    res = {
        "n": len(d),
        "rmse": float(np.sqrt((err ** 2).mean())),
        "mae": float(err.abs().mean()),
        "cobertura_95": float(((y >= lo) & (y <= hi)).mean()),
        "largura_media": float(width.mean()),
        "interval_score": float((width + penalty).mean()),
    }
    if "logp" in d:  # optional column: log predictive density of the true value
        res["nlpd"] = float(-d["logp"].mean())
    return pd.Series(res)


def conformal_factor(serie, out, alpha=0.05) -> float:
    """Split-conformal factor from hidden points of 'calibracao'.

    Score = |y - media| / half-width of the model interval. Multiplying the half-widths by
    this factor gives (1 - alpha) coverage if calibration and test are exchangeable.
    """
    d = _join(serie, out)
    d = d[(d["split"] == "calibracao") & (d["escondido_aval"] == 1)].dropna(subset=["media"])
    half = np.where(d["y"] >= d["media"], d["q975"] - d["media"], d["media"] - d["q025"])
    s = np.sort(np.abs(d["y"] - d["media"]) / np.maximum(half, 1e-12))
    k = int(np.ceil((len(s) + 1) * (1 - alpha))) - 1
    return float(s[min(k, len(s) - 1)])


def apply_conformal(out: pd.DataFrame, factor: float) -> pd.DataFrame:
    """Stretch (or shrink) the intervals around the mean by the conformal factor."""
    out = out.copy()
    out["q025"] = out["media"] - factor * (out["media"] - out["q025"])
    out["q975"] = out["media"] + factor * (out["q975"] - out["media"])
    return out


# ---------------------------------------------------------------- detection
def threshold_from_calibration(serie, out, quantile=0.99) -> float:
    """Alert threshold = quantile of the scores of visible days in 'calibracao' (never 'teste')."""
    d = _join(serie, out)
    s = d.loc[(d["split"] == "calibracao") & (d["visivel"] == 1), "escore"].dropna()
    return float(s.quantile(quantile))


def _auc(y_true, score):
    """ROC AUC through ranks (Mann-Whitney): chance that an anomaly scores above a normal day."""
    r = pd.Series(score).rank().to_numpy()
    pos = np.asarray(y_true) == 1
    n_pos, n_neg = pos.sum(), (~pos).sum()
    if n_pos == 0 or n_neg == 0:
        return np.nan
    return float((r[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _average_precision(y_true, score):
    order = np.argsort(-np.asarray(score), kind="mergesort")
    y = np.asarray(y_true)[order]
    if y.sum() == 0:
        return np.nan
    hits = np.cumsum(y)
    return float((hits / np.arange(1, len(y) + 1))[y == 1].mean())


def detection_metrics(serie, out, threshold, split="teste", top=0.01) -> pd.Series:
    """Compare scores with the 'anomalia' column on visible days of one split."""
    d = _join(serie, out)
    d = d[(d["split"] == split) & (d["visivel"] == 1)].dropna(subset=["escore"])
    y, s = d["anomalia"].to_numpy(), d["escore"].to_numpy()
    alert = s > threshold
    tp, fp, fn = int((alert & (y == 1)).sum()), int((alert & (y == 0)).sum()), int((~alert & (y == 1)).sum())
    k = max(int(np.ceil(top * len(s))), 1)
    top_idx = np.argsort(-s)[:k]
    precision = tp / (tp + fp) if tp + fp else np.nan
    recall = tp / (tp + fn) if tp + fn else np.nan
    return pd.Series({
        "dias": len(d), "anomalias": int(y.sum()), "taxa_base": float(y.mean()),
        "auc": _auc(y, s), "average_precision": _average_precision(y, s),
        f"recall_top{top:.0%}": float(y[top_idx].sum() / max(y.sum(), 1)),
        "limiar": threshold, "alertas": int(alert.sum()),
        "precisao": precision, "recall": recall,
        "f1": (2 * precision * recall / (precision + recall)
               if np.isfinite([precision, recall]).all() and precision + recall > 0 else np.nan),
    })


def detection_by_group(serie, out, threshold, split="teste") -> pd.DataFrame:
    """Recall per quality code, and AUC separately for Approved and Provisional days."""
    d = _join(serie, out)
    d = d[(d["split"] == split) & (d["visivel"] == 1)].dropna(subset=["escore"])
    d = d.assign(alerta=(d["escore"] > threshold).astype(int))
    rows = []
    groups = {  # short USGS code or the spelled-out form returned by the OGC API
        "Eqp": r"\b(?:eqp|equip\w*)\b", "Ice": r"\bice\b", "Bkw": r"\b(?:bkw|backwater)\b",
        "Mnt": r"\b(?:mnt|maint\w*)\b", "Fld": r"\b(?:fld|flood\w*)\b",
    }
    for code, pattern in groups.items():
        m = d["qualificador"].str.contains(pattern, case=False, regex=True)
        if m.any():
            rows.append({"grupo": f"qualificador {code}", "dias": int(m.sum()), "recall": d.loc[m, "alerta"].mean()})
    for status in ("Approved", "Provisional"):
        m = d["aprovacao"].str.contains(status, case=False, regex=False)
        if m.any():
            rows.append({"grupo": status, "dias": int(m.sum()),
                         "auc": _auc(d.loc[m, "anomalia"], d.loc[m, "escore"])})
    return pd.DataFrame(rows)
