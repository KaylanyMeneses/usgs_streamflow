"""Transform cached USGS measurements into analysis-ready tables."""

import pandas as pd


def make_station_observation_table(
    observations: pd.DataFrame,
    stations: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row per observed daily measurement and selected station.

    Dates without a row in the source Parquets are not synthesized. Existing rows
    whose discharge is missing remain present with NaN discharge values.
    """
    observation_columns = {"time_series_id", "date", "value_cfs"}
    station_columns = {"time_series_id", "monitoring_location_id"}
    missing_observations = observation_columns.difference(observations.columns)
    missing_stations = station_columns.difference(stations.columns)
    if missing_observations:
        raise ValueError(f"Observações sem colunas necessárias: {sorted(missing_observations)}")
    if missing_stations:
        raise ValueError(f"Catálogo sem colunas necessárias: {sorted(missing_stations)}")

    station_map = stations.loc[
        :, ["time_series_id", "monitoring_location_id"]
    ].drop_duplicates()
    if station_map["time_series_id"].duplicated().any():
        raise ValueError("O catálogo associa uma série a mais de uma estação.")
    if station_map["monitoring_location_id"].duplicated().any():
        raise ValueError(
            "Há mais de uma série selecionada para uma estação; "
            "a tabela de três colunas ficaria ambígua."
        )

    data = observations.loc[:, ["time_series_id", "date", "value_cfs"]].copy()
    data["time_series_id"] = data["time_series_id"].astype("string")
    station_map["time_series_id"] = station_map["time_series_id"].astype("string")
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.normalize()
    if data["date"].isna().any():
        raise ValueError("As observações contêm datas inválidas.")
    data["value_cfs"] = pd.to_numeric(data["value_cfs"], errors="coerce")

    data = data.merge(
        station_map,
        how="inner",
        on="time_series_id",
        validate="many_to_one",
    )
    data = data.rename(columns={"monitoring_location_id": "monitoring_location_id"})
    data = data.loc[
        :, ["date", "value_cfs", "monitoring_location_id"]
    ].sort_values(["monitoring_location_id", "date"], ignore_index=True)

    if data.duplicated(["monitoring_location_id", "date"]).any():
        raise ValueError("Há mais de uma observação por estação e data.")
    data["monitoring_location_id"] = data["monitoring_location_id"].astype("category")
    return data


def summarize_station_observations(table: pd.DataFrame) -> pd.DataFrame:
    """Summarize record counts, missing discharges and zeros per station."""
    required = {"monitoring_location_id", "date", "value_cfs"}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"Tabela analítica sem colunas necessárias: {sorted(missing)}")
    return (
        table.groupby("monitoring_location_id", observed=True)
        .agg(
            registros=("date", "size"),
            primeira_data=("date", "min"),
            ultima_data=("date", "max"),
            vazoes_ausentes=("value_cfs", lambda values: values.isna().sum()),
            vazoes_zero=("value_cfs", lambda values: values.eq(0).sum()),
            vazoes_validas=("value_cfs", "count"),
        )
        .reset_index()
    )
### Imputando valores "Nan"
def complete_daily_calendar(
    table: pd.DataFrame,
    start: str = "2010-01-01",
    end: str = "2024-12-31",
) -> pd.DataFrame:
    """Return one row per station and calendar day; missing days get NaN discharge."""
    required = {"monitoring_location_id", "date", "value_cfs"}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"Tabela sem colunas necessárias: {sorted(missing)}")

    calendar = pd.date_range(start, end, freq="D", name="date")
    stations = table["monitoring_location_id"].unique()
    full_index = pd.MultiIndex.from_product(
        [stations, calendar], names=["monitoring_location_id", "date"]
    )
    out = (
        table.set_index(["monitoring_location_id", "date"])
        .reindex(full_index)
        .reset_index()
        .loc[:, ["date", "value_cfs", "monitoring_location_id"]]
    )
    out["monitoring_location_id"] = out["monitoring_location_id"].astype("category")
    
    return out
