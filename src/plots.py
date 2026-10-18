"""Plots for station-level streamflow observations."""

import matplotlib.pyplot as plt
import pandas as pd


def plot_station_series(
    table: pd.DataFrame,
    station_id: str,
    value_column: str = "value_cfs",
) -> tuple[plt.Figure, plt.Axes]:
    """Plot one station's existing observations; missing calendar days stay gaps."""
    required = {"date", "monitoring_location_id", value_column}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"Tabela sem colunas necessárias: {sorted(missing)}")
    station = table.loc[
        table["monitoring_location_id"].astype("string") == str(station_id)
    ].copy()
    if station.empty:
        raise ValueError(f"Estação {station_id!r} não encontrada na tabela.")
    station["date"] = pd.to_datetime(station["date"], errors="coerce")
    station[value_column] = pd.to_numeric(station[value_column], errors="coerce")
    station = station.sort_values("date")

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(station["date"], station[value_column], linewidth=0.8)
    ax.set(
        title=f"Vazão diária — {station_id}",
        xlabel="Data",
        ylabel=f"Vazão ({value_column})",
    )
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig, ax
