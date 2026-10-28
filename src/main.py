"""Orchestration for analysis-ready tables built from the files written by src/download.py."""

import pandas as pd

from .catalog import (
    build_dataset_index,
    export_dataset,
    load_dataset,
    load_station_selection,
)
from .config import USGS
from .download import DownloadConfig, load_daily, load_selected
from .model_data import SelectionConfig, SplitConfig, prepare_model_dataset
from .processing import (
    complete_daily_calendar,
    make_station_observation_table,
    summarize_station_observations,
)


def default_download_config() -> DownloadConfig:
    """Download settings matching src/config.py (.env); they define which files are read."""
    return DownloadConfig(
        date_start=USGS.date_start,
        date_end=USGS.date_end,
        parameter_code=USGS.parameter_code,
        statistic_id=USGS.statistic_id,
        api_version=USGS.api_version,
    )


def build_observation_table(config: DownloadConfig | None = None) -> pd.DataFrame:
    """Build the selected-station table from the local per-series Parquets, without API requests."""
    cfg = config or default_download_config()
    stations = load_selected(cfg)
    observations = load_daily(cfg, stations["time_series_id"])
    if observations.empty:
        raise FileNotFoundError(f"Nenhuma série baixada em {cfg.series_dir}. Rode o 01_download.ipynb.")
    return make_station_observation_table(observations, stations)


def build_analysis_dataset(config: DownloadConfig | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the observation table and station-level coverage summary."""
    table = build_observation_table(config)
    return table, summarize_station_observations(table)


def build_model_dataset(
    selection: SelectionConfig = SelectionConfig(),
    splits: SplitConfig = SplitConfig(),
    config: DownloadConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the shared modeling table (see README) and per-station normalization stats."""
    cfg = config or default_download_config()
    full = complete_daily_calendar(build_observation_table(cfg), start=cfg.date_start, end=cfg.date_end)
    return prepare_model_dataset(full, selection, splits)


__all__ = [
    "SelectionConfig",
    "SplitConfig",
    "build_analysis_dataset",
    "build_model_dataset",
    "build_dataset_index",
    "build_observation_table",
    "default_download_config",
    "export_dataset",
    "load_dataset",
    "load_station_selection",
    "summarize_station_observations",
]
