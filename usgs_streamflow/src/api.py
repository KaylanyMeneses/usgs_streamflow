"""Optional client for the USGS Water Data OGC API."""

from collections.abc import Mapping
import time
from typing import Any

import pandas as pd
import requests

from .config import USGS, USGSConfig


class USGSClient:
    """Paginated API client. Local-Parquet workflows do not call it implicitly."""

    def __init__(
        self,
        config: USGSConfig = USGS,
        session: requests.Session | None = None,
        timeout: float = 180,
        retries: int = 6,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout deve ser positivo.")
        if retries < 1:
            raise ValueError("retries deve ser pelo menos 1.")
        self.config = config
        self.session = session or requests.Session()
        self.timeout = timeout
        self.retries = retries
        if config.api_key:
            self.session.headers["X-Api-Key"] = config.api_key

    def get_json(
        self, url: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Request JSON and retry rate-limit or transient server errors."""
        for attempt in range(self.retries):
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 429:
                try:
                    delay = float(response.headers.get("Retry-After", 15 * 2**attempt))
                except ValueError:
                    delay = 15 * 2**attempt
                time.sleep(max(0.0, min(delay, 3700)))
                continue
            if response.status_code in {500, 502, 503, 504} and attempt + 1 < self.retries:
                time.sleep(3 * 2**attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"A resposta da API não é um objeto JSON: {url}")
            return payload
        raise requests.HTTPError(f"USGS API não respondeu após {self.retries} tentativas: {url}")

    def fetch_items(
        self,
        collection: str,
        params: Mapping[str, Any] | None = None,
        limit: int = 50_000,
    ) -> pd.DataFrame:
        """Fetch all pages of one USGS collection."""
        if not collection or "/" in collection:
            raise ValueError("collection deve ser um identificador simples.")
        if limit < 1:
            raise ValueError("limit deve ser positivo.")
        url = f"{self.config.base_url}/collections/{collection}/items"
        query = {"f": "json", "limit": limit, **(params or {})}
        rows: list[dict[str, Any]] = []
        first_page = True
        while url:
            payload = self.get_json(url, query if first_page else None)
            first_page = False
            for feature in payload.get("features", []):
                row = dict(feature.get("properties") or {})
                row["_feature_id"] = feature.get("id")
                geometry = feature.get("geometry")
                if geometry and geometry.get("type") == "Point":
                    row["lon"], row["lat"] = geometry["coordinates"][:2]
                rows.append(row)
            url = next(
                (
                    link["href"]
                    for link in payload.get("links", [])
                    if link.get("rel") == "next" and link.get("href")
                ),
                None,
            )
        return pd.DataFrame(rows)

    def get_schema_properties(self, collection: str) -> list[str]:
        """Return property names advertised by a collection's schema."""
        schema_url = f"{self.config.base_url}/collections/{collection}/schema"
        schema = self.get_json(schema_url, {"f": "json"})
        return list(schema.get("properties", {}))


client = USGSClient()
