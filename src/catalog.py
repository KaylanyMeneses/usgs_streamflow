"""Load the station selection and local daily USGS Parquet caches."""

from pathlib import Path
from collections.abc import Iterable

import pandas as pd

from .config import DATA_ROOT, EXPORT_ROOT, PROCESSED_ROOT, PROJECT_ROOT, RAW_ROOT, USGS, USGSConfig


DAILY_CACHE_COLUMNS = ("time_series_id", "date", "value_cfs")


def build_dataset_index(data_root: Path = DATA_ROOT) -> pd.DataFrame:
    """List CSV and Parquet files below the project's data directory."""
    root = data_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Diretório de dados não encontrado: {root}")
    entries = [
        {
            "arquivo": path.relative_to(PROJECT_ROOT).as_posix(),
            "formato": path.suffix.lower().lstrip("."),
            "tamanho_mb": round(path.stat().st_size / (1024**2), 3),
        }
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".csv", ".parquet"}
    ]
    return pd.DataFrame(
        entries, columns=["arquivo", "formato", "tamanho_mb"]
    ).sort_values("arquivo").reset_index(drop=True)


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Load a CSV or Parquet file inside the project's data directory."""
    source = Path(path)
    if not source.is_absolute():
        source = PROJECT_ROOT / source
    source = source.resolve()
    try:
        source.relative_to(DATA_ROOT.resolve())
    except ValueError as error:
        raise ValueError("O arquivo deve estar dentro da pasta data/ do projeto.") from error
    if not source.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {source}")
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    if source.suffix.lower() == ".parquet":
        return pd.read_parquet(source)
    raise ValueError(f"Formato não suportado: {source.suffix}. Use CSV ou Parquet.")


def load_station_selection(path: Path | None = None) -> pd.DataFrame:
    """Load and validate the processed table that defines selected stations."""
    source = path or PROCESSED_ROOT / "stations_full.parquet"
    stations = load_dataset(source)
    required = {"time_series_id", "monitoring_location_id"}
    missing = required.difference(stations.columns)
    if missing:
        raise ValueError(f"Catálogo de estações sem colunas necessárias: {sorted(missing)}")
    if "parameter_code" in stations.columns:
        stations = stations.loc[stations["parameter_code"].astype(str) == USGS.parameter_code]
    if "statistic_id" in stations.columns:
        stations = stations.loc[stations["statistic_id"].astype(str) == USGS.statistic_id]
    stations = stations.dropna(subset=["time_series_id", "monitoring_location_id"]).copy()
    stations["time_series_id"] = stations["time_series_id"].astype("string")
    stations["monitoring_location_id"] = stations["monitoring_location_id"].astype("string")
    if stations["time_series_id"].duplicated().any():
        raise ValueError("Catálogo contém time_series_id duplicados.")
    if stations["monitoring_location_id"].duplicated().any():
        raise ValueError(
            "O catálogo selecionado contém mais de uma série por estação; "
            "é necessário escolher a série antes de reduzir a tabela a um ID de estação."
        )
    return stations.reset_index(drop=True)


def daily_cache_pattern(config: USGSConfig = USGS) -> str:
    """Build the filename pattern used by the streamflow notebook's daily caches."""
    return (
        f"daily_{config.parameter_code}_{config.statistic_id}_"
        f"{config.date_start}_{config.date_end}_*.parquet"
    )


def load_cached_daily_observations(
    series_ids: Iterable[str],
    config: USGSConfig = USGS,
) -> pd.DataFrame:
    """Read matching daily cache rows for the chosen series, without API requests."""
    requested = {str(series_id) for series_id in series_ids}
    if not requested:
        raise ValueError("A seleção de time_series_id está vazia.")
    cache_files = sorted(RAW_ROOT.glob(daily_cache_pattern(config)))
    if not cache_files:
        raise FileNotFoundError(
            f"Nenhum Parquet diário encontrado em {RAW_ROOT} para "
            f"{config.parameter_code}/{config.statistic_id}, "
            f"{config.date_start} a {config.date_end}."
        )

    parts: list[pd.DataFrame] = []
    required = set(DAILY_CACHE_COLUMNS)
    for path in cache_files:
        frame = pd.read_parquet(path)
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Cache {path.name} sem colunas necessárias: {sorted(missing)}")
        frame = frame.loc[:, list(DAILY_CACHE_COLUMNS)].copy()
        frame["time_series_id"] = frame["time_series_id"].astype("string")
        frame = frame.loc[frame["time_series_id"].isin(requested)].copy()
        if frame.empty:
            continue
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
        if frame["date"].isna().any():
            raise ValueError(f"Cache {path.name} contém datas inválidas.")
        frame["value_cfs"] = pd.to_numeric(frame["value_cfs"], errors="coerce")
        parts.append(frame)

    if not parts:
        raise FileNotFoundError(
            "Os Parquets diários foram encontrados, mas nenhum contém as séries "
            "selecionadas no catálogo stations_full.parquet."
        )
    observations = pd.concat(parts, ignore_index=True)
    duplicate_mask = observations.duplicated(["time_series_id", "date"], keep=False)
    if duplicate_mask.any():
        examples = observations.loc[
            duplicate_mask, ["time_series_id", "date"]
        ].head(5)
        raise ValueError(
            "Há registros repetidos entre os Parquets para a mesma série e data: "
            f"{examples.to_dict(orient='records')}"
        )
    return observations.sort_values(
        ["time_series_id", "date"], ignore_index=True
    )


def export_dataset(frame: pd.DataFrame, filename: str) -> Path:
    """Export a table under data/exports, refusing to overwrite existing files."""
    name = Path(filename)
    if name.name != filename or name.suffix.lower() not in {".csv", ".parquet"}:
        raise ValueError("Use um nome de arquivo .csv ou .parquet, sem subpastas.")
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    destination = EXPORT_ROOT / name.name
    if destination.exists():
        raise FileExistsError(f"A exportação já existe e não será sobrescrita: {destination}")
    if name.suffix.lower() == ".csv":
        frame.to_csv(destination, index=False)
    else:
        frame.to_parquet(destination, index=False)
    return destination
