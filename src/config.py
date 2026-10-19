"""Project paths and USGS dataset configuration."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data"
USGS_ROOT = DATA_ROOT / "usgs"
RAW_ROOT = USGS_ROOT / "raw"
PROCESSED_ROOT = USGS_ROOT / "processed"
EXPORT_ROOT = DATA_ROOT / "exports"

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class USGSConfig:
    """Settings identifying the USGS API and cached daily dataset."""

    api_version: str = os.getenv("USGS_API_VERSION", "v0")
    date_start: str = os.getenv("USGS_DATE_START", "2010-01-01")
    date_end: str = os.getenv("USGS_DATE_END", "2025-12-31")
    parameter_code: str = os.getenv("USGS_PARAMETER_CODE", "00060")
    statistic_id: str = os.getenv("USGS_STATISTIC_ID", "00003")
    api_key: str | None = os.getenv("USGS_API_KEY")

    def __post_init__(self) -> None:
        if not self.api_version.strip():
            raise ValueError("USGS_API_VERSION não pode ser vazio.")
        if self.date_start > self.date_end:
            raise ValueError("USGS_DATE_START deve ser anterior ou igual a USGS_DATE_END.")

    @property
    def base_url(self) -> str:
        return f"https://api.waterdata.usgs.gov/ogcapi/{self.api_version}"


USGS = USGSConfig()
