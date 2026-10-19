"""Orchestration for analysis-ready tables built from local USGS Parquets."""

import pandas as pd

from .catalog import (
    build_dataset_index,
    export_dataset,
    load_cached_daily_observations,
    load_dataset,
    load_station_selection,
)
from .model_data import SelectionConfig, SplitConfig, prepare_model_dataset
from .processing import (
    complete_daily_calendar,
    make_station_observation_table,
    summarize_station_observations,
)


def build_observation_table() -> pd.DataFrame:
    """Build the selected-station table using only existing local Parquet caches."""
    stations = load_station_selection()
    observations = load_cached_daily_observations(stations["time_series_id"])
    return make_station_observation_table(observations, stations)


def build_analysis_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the observation table and station-level coverage summary."""
    table = build_observation_table()
    return table, summarize_station_observations(table)


def build_model_dataset(
    selection: SelectionConfig = SelectionConfig(),
    splits: SplitConfig = SplitConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the shared modeling table (see README) and per-station normalization stats."""
    full = complete_daily_calendar(build_observation_table())
    return prepare_model_dataset(full, selection, splits)


__all__ = [
    "SelectionConfig",
    "SplitConfig",
    "build_analysis_dataset",
    "build_model_dataset",
    "build_dataset_index",
    "build_observation_table",
    "export_dataset",
    "load_dataset",
    "load_station_selection",
    "summarize_station_observations",
]
