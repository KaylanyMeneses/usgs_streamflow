"""Turn the shared modeling table into the input format of each model.

All functions read the table returned by ``build_model_dataset`` and never pass NaN to a
model: values that are not visible (real gaps or hidden evaluation points) are removed
(GP) or replaced by 0 together with a mask that tells the model to ignore them (RGP, GPLVM).
"""

import numpy as np
import pandas as pd


def gp_inputs(serie: pd.DataFrame, sensor_id: str, fit_split: str = "treino") -> dict:
    """Model 1 (GP Student-t): (t, y) pairs of one station, without NaN.

    - t_train, y_train: visible points of ``fit_split``, used to fit the model.
    - t_context, y_context: visible points of every split, used to condition predictions
      with frozen hyperparameters (hidden points are never included).
    - t_all: every day of the station, where predictions are made (gaps included).
    - splits[name]: for each block, ``t_all`` (days to predict and score), ``t_visible`` /
      ``y_visible`` (days the model may read), ``t_hidden`` / ``y_hidden`` (hidden days and their
      true values; ``y_hidden`` is for evaluation only, never an input).
    """
    s = serie[serie["sensor_id"] == sensor_id].sort_values("t")
    if s.empty:
        raise ValueError(f"Estação {sensor_id!r} não está na tabela.")
    vis = s[s["visivel"] == 1]
    fit = vis[vis["split"] == fit_split]
    return {
        "t_train": fit["t"].to_numpy(float), "y_train": fit["y"].to_numpy(float),
        "t_context": vis["t"].to_numpy(float), "y_context": vis["y"].to_numpy(float),
        "t_all": s["t"].to_numpy(float),
        "splits": {
            name: {
                "t_all": g["t"].to_numpy(float),
                "t_visible": g.loc[g["visivel"] == 1, "t"].to_numpy(float),
                "y_visible": g.loc[g["visivel"] == 1, "y"].to_numpy(float),
                "t_hidden": g.loc[g["escondido_aval"] == 1, "t"].to_numpy(float),
                "y_hidden": g.loc[g["escondido_aval"] == 1, "y"].to_numpy(float),
            }
            for name, g in s.groupby("split", sort=False)
        },
    }


def rgp_inputs(serie: pd.DataFrame) -> dict:
    """Model 2 (RGP-t): ordered sequences of all stations as a batch.

    - y: (S, T) values, 0 where not visible;  mask: (S, T) 1 where visible.
    - split: (T,) split label of each day;  fit_mask = mask restricted to training days.
    - rnn_in: (S, T, 2) = [y, mask], input of the recognition RNN.
    - y_true: (S, T) real values with NaN where there is no value (evaluation only).
    - split_masks[name]: visible days of each block (scoring);
      eval_masks[name]: hidden days of each block (reconstruction).
    The sequence is always read whole (the past is allowed as input); the masks only
    decide which days enter the ELBO (training) or each metric.
    """
    y = serie.assign(y=serie["y"].where(serie["visivel"] == 1, 0.0)).pivot(
        index="sensor_id", columns="t", values="y").fillna(0.0)
    mask = serie.pivot(index="sensor_id", columns="t", values="visivel").fillna(0).astype(int)
    hidden = serie.pivot(index="sensor_id", columns="t", values="escondido_aval").fillna(0).astype(int)
    split = serie.drop_duplicates("t").set_index("t").sort_index()["split"].to_numpy()
    y_arr, m_arr, h_arr = y.to_numpy(float), mask.to_numpy(float), hidden.to_numpy(float)
    names = pd.unique(split)
    return {
        "sensors": y.index.to_list(), "y": y_arr, "mask": m_arr, "split": split,
        "y_true": serie.pivot(index="sensor_id", columns="t", values="y").to_numpy(float),
        "fit_mask": m_arr * (split == "treino")[None, :],
        "split_masks": {n: m_arr * (split == n)[None, :] for n in names},
        "eval_masks": {n: h_arr * (split == n)[None, :] for n in names},
        "rnn_in": np.stack([y_arr, m_arr], axis=-1),
    }


def gplvm_inputs(serie: pd.DataFrame, window: int = 7, max_missing: float = 0.5) -> dict:
    """Model 3 (Bayesian GPLVM): non-overlapping windows built inside each split.

    - Y: (N, window) values, 0 where not visible;  mask: (N, window).
    - Y_true: (N, window) real values, NaN where there is no value (evaluation only).
    - hidden: (N, window) 1 on hidden cells (reconstruction is measured there).
    - t_idx: (N, window) day index of each cell;  meta: station and split of each window.
    Windows never cross two splits; windows with more than ``max_missing`` invisible cells
    are dropped. The remainder at the end of each block (< window days) is dropped too.
    """
    Ys, Ms, Ts, Trues, Hs, meta = [], [], [], [], [], []
    for (sid, split), g in serie.sort_values("t").groupby(["sensor_id", "split"], sort=False):
        n = len(g) // window
        if n == 0:
            continue
        g = g.iloc[: n * window]
        vis = g["visivel"].to_numpy(int).reshape(n, window)
        vals = np.where(vis == 1, g["y"].to_numpy(float).reshape(n, window), 0.0)
        tt = g["t"].to_numpy(int).reshape(n, window)
        true = g["y"].to_numpy(float).reshape(n, window)
        hid = g["escondido_aval"].to_numpy(int).reshape(n, window)
        keep = vis.mean(axis=1) >= 1 - max_missing
        Ys.append(vals[keep]); Ms.append(vis[keep]); Ts.append(tt[keep])
        Trues.append(true[keep]); Hs.append(hid[keep])
        meta += [(sid, split)] * int(keep.sum())
    meta = pd.DataFrame(meta, columns=["sensor_id", "split"])
    return {
        "Y": np.concatenate(Ys), "mask": np.concatenate(Ms).astype(float),
        "t_idx": np.concatenate(Ts), "meta": meta,
        "Y_true": np.concatenate(Trues), "hidden": np.concatenate(Hs).astype(float),
    }


def select_split(inputs: dict, split: str) -> dict:
    """GPLVM windows of one block: treino (fit), validacao/calibracao/teste (score)."""
    keep = inputs["meta"]["split"].eq(split).to_numpy()
    return {
        "Y": inputs["Y"][keep], "mask": inputs["mask"][keep],
        "Y_true": inputs["Y_true"][keep], "hidden": inputs["hidden"][keep],
        "t_idx": inputs["t_idx"][keep], "meta": inputs["meta"][keep].reset_index(drop=True),
    }


def windows_to_days(inputs: dict, window_values: np.ndarray, name: str = "escore") -> pd.DataFrame:
    """Repeat one value per window (e.g. -ELBO) on every day of that window."""
    n, w = inputs["t_idx"].shape
    return pd.DataFrame({
        "sensor_id": np.repeat(inputs["meta"]["sensor_id"].to_numpy(), w),
        "t": inputs["t_idx"].ravel(),
        name: np.repeat(np.asarray(window_values, float), w),
    })
