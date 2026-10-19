"""Pipeline de download das séries diárias da USGS, com um arquivo Parquet por série.

Mesmas etapas do notebook usgs_streamflow.ipynb (catálogo, locais Stream, seleção,
download em lotes), mas cada série é gravada assim que o lote dela termina. Se a
execução cair (rede, erro 429, kernel reiniciado), basta chamar de novo: as séries
que já estão em disco são puladas e só as pendentes são baixadas.

Uso típico:

    from src.download import DownloadConfig, run_pipeline, load_daily

    cfg = DownloadConfig(date_end="2025-12-31", max_sites=None)
    selected, summary = run_pipeline(cfg)
    daily = load_daily(cfg, selected["time_series_id"])
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from .api import USGSClient
from .config import RAW_ROOT, USGSConfig


MAX_ROWS = 50_000
TS_WANTED = [
    "time_series_id", "monitoring_location_id", "state_name", "hydrologic_unit_code",
    "parameter_code", "statistic_id", "unit_of_measure", "computation_period_identifier",
    "primary", "sublocation_identifier", "web_description",
]
ML_PROPS = [
    "id", "monitoring_location_name", "site_type_code", "site_type", "state_name",
    "county_name", "drainage_area", "hydrologic_unit_code", "agency_code",
]
DAILY_WANTED = ["time_series_id", "monitoring_location_id", "time", "value",
                "approval_status", "qualifier"]
DAILY_COLUMNS = ["time_series_id", "monitoring_location_id", "approval_status", "qualifier",
                 "time_api", "date", "value_cfs"]


@dataclass(frozen=True)
class DownloadConfig:
    """Argumentos da pipeline (equivalem aos PARÂMETROS do notebook)."""

    date_start: str = "2010-01-01"
    date_end: str = "2025-12-31"
    parameter_code: str = "00060"          # vazão, ft3/s
    statistic_id: str = "00003"            # média diária
    api_version: str = "v0"
    states: Sequence[str] | None = None    # None = todos; ou ex.: ("Ohio", "Texas")
    require_full_coverage: bool = False    # só séries cujo registro cobre o período inteiro
    all_columns: bool = True               # True = sem filtro "properties" na API
    use_top_state: bool = True             # True = só o estado com mais estações
    n_candidates: int = 3                  # estados consultados para achar o "top"
    max_sites: int | None = None
    seed: int = 42
    batch_size: int = 8                    # séries por requisição
    out_dir: Path = RAW_ROOT / "parquets"
    max_consecutive_failures: int = 5      # para a execução se a API cair de vez

    def __post_init__(self) -> None:
        if self.date_start > self.date_end:
            raise ValueError("date_start deve ser anterior ou igual a date_end.")
        if self.batch_size < 1:
            raise ValueError("batch_size deve ser pelo menos 1.")

    @property
    def stem(self) -> str:
        return f"daily_{self.parameter_code}_{self.statistic_id}_{self.date_start}_{self.date_end}"

    @property
    def series_dir(self) -> Path:
        """Pasta com um Parquet por série: <out_dir>/<stem>/<time_series_id>.parquet."""
        return Path(self.out_dir) / self.stem

    def series_path(self, ts_id: str) -> Path:
        return self.series_dir / f"{ts_id}.parquet"


def make_client(cfg: DownloadConfig) -> USGSClient:
    return USGSClient(USGSConfig(
        api_version=cfg.api_version, date_start=cfg.date_start, date_end=cfg.date_end,
        parameter_code=cfg.parameter_code, statistic_id=cfg.statistic_id,
    ))


def _log(msg: str) -> None:
    print(msg, flush=True)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Grava num arquivo temporário e renomeia: uma queda no meio não deixa Parquet corrompido."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp)
    os.replace(tmp, path)


# ---------------------------------------------------------------- esquema

@dataclass(frozen=True)
class Schema:
    ts_props: list[str]
    daily_props: list[str]
    begin_field: str
    end_field: str


def _pick(options: Sequence[str], props: Sequence[str], what: str) -> str:
    for option in options:
        if option in props:
            return option
    raise RuntimeError(f"Nenhum campo de {what} encontrado entre {list(options)} em {list(props)}. "
                       "Tente api_version='v1' (ou 'v0').")


def read_schema(client: USGSClient) -> Schema:
    """Lê o esquema real da API e escolhe os nomes de campo desta versão."""
    ts_props = client.get_schema_properties("time-series-metadata")
    daily_props = client.get_schema_properties("daily")
    for need in ("state_name", "monitoring_location_id", "parameter_code", "statistic_id"):
        if need not in ts_props:
            raise RuntimeError(f"Campo '{need}' ausente em time-series-metadata nesta versão da API.")
    for need in ("time_series_id", "time", "value"):
        if need not in daily_props:
            raise RuntimeError(f"Campo '{need}' ausente em daily nesta versão da API.")
    return Schema(
        ts_props=ts_props,
        daily_props=daily_props,
        begin_field=_pick(["begin_utc", "start", "begin"], ts_props, "início do período de registro"),
        end_field=_pick(["end_utc", "end"], ts_props, "fim do período de registro"),
    )


# ---------------------------------------------------------------- catálogo e seleção

def _rename_period(df: pd.DataFrame, schema: Schema) -> pd.DataFrame:
    # a versão antiga (begin/end, hora local) vira begin_local/end_local; a escolhida vira begin/end (UTC)
    legacy = {c: f"{c}_local" for c in ("begin", "end")
              if c in df.columns and c not in (schema.begin_field, schema.end_field)}
    df = df.rename(columns=legacy).rename(columns={schema.begin_field: "begin", schema.end_field: "end"})
    df["begin"] = pd.to_datetime(df["begin"], utc=True, errors="coerce")
    df["end"] = pd.to_datetime(df["end"], utc=True, errors="coerce")
    return df


def load_catalog(cfg: DownloadConfig, client: USGSClient, schema: Schema) -> pd.DataFrame:
    """Séries de vazão diária de toda a rede, com cache em catalog_timeseries.parquet."""
    path = Path(cfg.out_dir) / "catalog_timeseries.parquet"
    if path.exists():
        cat = pd.read_parquet(path)
    else:
        _log("Baixando o catálogo (time-series-metadata) ...")
        params = {"parameter_code": cfg.parameter_code, "statistic_id": cfg.statistic_id,
                  "skipGeometry": "true"}
        if not cfg.all_columns:
            wanted = TS_WANTED + [schema.begin_field, schema.end_field]
            params["properties"] = ",".join(c for c in wanted if c in schema.ts_props)
        if "computation_period_identifier" in schema.ts_props:
            params["computation_period_identifier"] = "Daily"
        cat = client.fetch_items("time-series-metadata", params)
        if cat.empty:
            raise RuntimeError("Catálogo vazio. Verifique parameter_code/statistic_id e o valor de "
                               "'computation_period_identifier' (esperado: 'Daily').")
        if "time_series_id" not in cat or cat["time_series_id"].isna().all():
            cat["time_series_id"] = cat["_feature_id"]
        _write_parquet(cat, path)

    cat = _rename_period(cat, schema).drop_duplicates("time_series_id")
    if cfg.states:
        cat = cat[cat["state_name"].isin(cfg.states)]

    t0, t1 = pd.Timestamp(cfg.date_start, tz="UTC"), pd.Timestamp(cfg.date_end, tz="UTC")
    tol = pd.Timedelta(days=1)   # tolerância: início/fim vêm em UTC e o dia civil é local
    cat = cat.copy()
    cat["overlaps"] = (cat["begin"] <= t1) & (cat["end"] >= t0)
    cat["full_coverage"] = (cat["begin"] <= t0 + tol) & (cat["end"] >= t1 - tol)
    _log(f"Catálogo: {len(cat):,} séries; {cat['monitoring_location_id'].nunique():,} estações")
    return cat


def _eligible(cfg: DownloadConfig, df: pd.DataFrame) -> pd.DataFrame:
    return df[df["full_coverage"]] if cfg.require_full_coverage else df[df["overlaps"]]


def fetch_stream_sites(cfg: DownloadConfig, client: USGSClient, state: str) -> pd.DataFrame:
    """Locais ST de um estado, com cache. Estado sem locais gera um arquivo .empty."""
    tag = "all" if cfg.all_columns else "lean"
    stem = f"sites_ST_{state.replace(' ', '_')}_{tag}"
    path = Path(cfg.out_dir) / f"{stem}.parquet"
    empty_flag = Path(cfg.out_dir) / f"{stem}.empty"
    if path.exists():
        return pd.read_parquet(path)
    if empty_flag.exists():
        return pd.DataFrame()
    params = {"state_name": state, "site_type_code": "ST"}
    if not cfg.all_columns:
        params["properties"] = ",".join(ML_PROPS)
    df = client.fetch_items("monitoring-locations", params)
    if df.empty:
        empty_flag.parent.mkdir(parents=True, exist_ok=True)
        empty_flag.touch()
    else:
        _write_parquet(df, path)
    return df


def stream_series(cfg: DownloadConfig, client: USGSClient, cat: pd.DataFrame) -> pd.DataFrame:
    """Junta o catálogo com os locais do tipo Stream dos estados pedidos."""
    ranking = (_eligible(cfg, cat).groupby("state_name")["monitoring_location_id"]
               .nunique().sort_values(ascending=False))
    if cfg.use_top_state and not cfg.states:
        states = ranking.head(cfg.n_candidates).index.tolist()
    else:
        states = sorted(cat["state_name"].dropna().unique())

    _log(f"Locais do tipo Stream em {len(states)} estado(s)")
    sites = []
    for state in states:
        df = fetch_stream_sites(cfg, client, state)
        _log(f"  {state}: {len(df):,} locais ST")
        if len(df):
            sites.append(df)
    if not sites:
        raise RuntimeError("Nenhum local ST encontrado nos estados pedidos.")

    sites = pd.concat(sites, ignore_index=True)
    if "id" not in sites or sites["id"].isna().all():
        sites["id"] = sites["_feature_id"]
    sites = sites.drop_duplicates("id").rename(columns={"id": "monitoring_location_id",
                                                        "state_name": "site_state_name",
                                                        "hydrologic_unit_code": "site_huc"})
    return cat.merge(sites, on="monitoring_location_id", how="inner")


def select_series(cfg: DownloadConfig, cat_streams: pd.DataFrame) -> pd.DataFrame:
    """Uma série por estação (primary e, no empate, a mais antiga); amostra até max_sites."""
    pool = _eligible(cfg, cat_streams)
    if cfg.use_top_state:
        counts = pool.groupby("state_name")["monitoring_location_id"].nunique().sort_values(ascending=False)
        top_state = counts.index[0]
        pool = pool[pool["state_name"] == top_state]
        _log(f"Estado escolhido: {top_state} ({counts.iloc[0]} estações)")

    df = pool.copy()
    df["_prim"] = df["primary"].astype(str).str.lower().eq("primary") if "primary" in df else False
    df = (df.sort_values(["monitoring_location_id", "_prim", "begin"], ascending=[True, False, True])
            .drop_duplicates("monitoring_location_id"))
    if cfg.max_sites is not None and len(df) > cfg.max_sites:
        rng = np.random.default_rng(cfg.seed)
        groups = {s: g.sample(frac=1, random_state=int(rng.integers(1_000_000_000)))
                  for s, g in df.groupby("state_name")}
        picked, i = [], 0
        while len(picked) < cfg.max_sites and any(i < len(g) for g in groups.values()):
            for g in groups.values():
                if i < len(g) and len(picked) < cfg.max_sites:
                    picked.append(g.iloc[i])
            i += 1
        df = pd.DataFrame(picked)

    df = df.reset_index(drop=True)
    _log(f"{len(df)} estações selecionadas em {df['state_name'].nunique()} estado(s)")
    return df


# ---------------------------------------------------------------- download por série

class _Truncated(RuntimeError):
    pass


def _clean_daily(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)
    for col in ("approval_status", "qualifier"):
        if col in df:
            df[col] = df[col].apply(lambda v: ";".join(map(str, v)) if isinstance(v, (list, tuple)) else v)
    df["time_api"] = df["time"]
    df["date"] = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None).dt.normalize()
    df["value_cfs"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.drop(columns=[c for c in ("time", "value", "_feature_id", "lon", "lat") if c in df])
    return df.drop_duplicates(["time_series_id", "date"], keep="last")


def _fetch_batch(cfg: DownloadConfig, client: USGSClient, schema: Schema,
                 ts_ids: list[str]) -> pd.DataFrame:
    params = {"time_series_id": ",".join(ts_ids), "datetime": f"{cfg.date_start}/{cfg.date_end}",
              "skipGeometry": "true"}
    if not cfg.all_columns:
        params["properties"] = ",".join(c for c in DAILY_WANTED if c in schema.daily_props)
    df = _clean_daily(client.fetch_items("daily", params))
    if len(df):
        stray = set(df["time_series_id"]) - set(ts_ids)
        if stray:
            raise RuntimeError(f"Linhas de séries não pedidas: {list(stray)[:3]}")
        if df["date"].min() < pd.Timestamp(cfg.date_start) or df["date"].max() > pd.Timestamp(cfg.date_end):
            raise RuntimeError("O servidor ignorou o filtro de datas (faixa devolvida fora de "
                               f"{cfg.date_start}..{cfg.date_end}).")
        if len(df) >= MAX_ROWS:
            raise _Truncated(f"Lote com {len(ts_ids)} séries atingiu {MAX_ROWS:,} linhas.")
    return df


def _fetch_splitting(cfg: DownloadConfig, client: USGSClient, schema: Schema,
                     ts_ids: list[str]) -> pd.DataFrame:
    """Baixa o lote; se ele bater o teto de linhas, divide ao meio e tenta de novo."""
    try:
        return _fetch_batch(cfg, client, schema, ts_ids)
    except _Truncated:
        if len(ts_ids) == 1:
            raise
        half = len(ts_ids) // 2
        _log(f"    lote grande demais; dividindo em {half} + {len(ts_ids) - half}")
        return pd.concat([_fetch_splitting(cfg, client, schema, ts_ids[:half]),
                          _fetch_splitting(cfg, client, schema, ts_ids[half:])], ignore_index=True)


def _save_per_series(cfg: DownloadConfig, df: pd.DataFrame, ts_ids: Iterable[str]) -> int:
    """Grava um Parquet por série. Série sem linhas vira um Parquet vazio (já consultada)."""
    groups = dict(tuple(df.groupby("time_series_id", observed=True))) if len(df) else {}
    empty = df.iloc[0:0] if len(df.columns) else pd.DataFrame(columns=DAILY_COLUMNS)
    rows = 0
    for ts_id in ts_ids:
        part = groups.get(ts_id, empty)
        _write_parquet(part.reset_index(drop=True), cfg.series_path(ts_id))
        rows += len(part)
    return rows


def import_legacy_batches(cfg: DownloadConfig) -> int:
    """Reaproveita os arquivos por lote do notebook (daily_..._<hash>.parquet) do mesmo período,
    separando-os em um arquivo por série. Devolve quantas séries foram importadas."""
    imported = 0
    for path in sorted(Path(cfg.out_dir).glob(f"{cfg.stem}_*.parquet")):
        df = pd.read_parquet(path)
        if df.empty or "time_series_id" not in df:
            continue
        missing = [s for s in df["time_series_id"].dropna().unique() if not cfg.series_path(s).exists()]
        if missing:
            _save_per_series(cfg, df, missing)
            imported += len(missing)
    if imported:
        _log(f"{imported} séries importadas dos arquivos por lote antigos")
    return imported


def pending_series(cfg: DownloadConfig, ts_ids: Iterable[str]) -> list[str]:
    """Séries que ainda não têm arquivo em disco."""
    return [s for s in dict.fromkeys(ts_ids) if not cfg.series_path(s).exists()]


def download_daily(cfg: DownloadConfig, ts_ids: Iterable[str], client: USGSClient | None = None,
                   schema: Schema | None = None) -> dict:
    """Baixa só as séries pendentes, em lotes de batch_size, salvando cada série ao terminar o lote.

    Um lote que falha é registrado e pulado; a próxima chamada tenta de novo só o que faltou.
    """
    client = client or make_client(cfg)
    schema = schema or read_schema(client)
    ts_ids = list(dict.fromkeys(ts_ids))
    todo = pending_series(cfg, ts_ids)
    _log(f"Séries: {len(ts_ids)} no total, {len(ts_ids) - len(todo)} já em disco, {len(todo)} a baixar")
    _log(f"Destino: {cfg.series_dir}")

    batches = [todo[i:i + cfg.batch_size] for i in range(0, len(todo), cfg.batch_size)]
    saved, failures, consecutive = 0, [], 0
    start = time.monotonic()
    for n, batch in enumerate(batches, 1):
        try:
            df = _fetch_splitting(cfg, client, schema, batch)
            rows = _save_per_series(cfg, df, batch)
        except Exception as exc:   # KeyboardInterrupt passa direto: o que já foi salvo fica salvo
            consecutive += 1
            failures.append({"batch": n, "time_series_ids": batch, "error": repr(exc)})
            _log(f"  lote {n}/{len(batches)} FALHOU: {exc!r}")
            if consecutive >= cfg.max_consecutive_failures:
                _log(f"{consecutive} falhas seguidas; parando. Rode de novo para continuar.")
                break
            continue
        consecutive = 0
        saved += len(batch)
        elapsed = time.monotonic() - start
        _log(f"  lote {n}/{len(batches)}: {len(batch)} séries, {rows:,} linhas | "
             f"{saved}/{len(todo)} salvas | {elapsed / 60:.1f} min")

    remaining = pending_series(cfg, ts_ids)
    _log(f"Concluído: {saved} séries salvas nesta execução, {len(failures)} lote(s) com falha, "
         f"{len(remaining)} série(s) pendente(s)")
    return {"saved": saved, "failures": failures, "pending": remaining}


def load_selected(cfg: DownloadConfig) -> pd.DataFrame:
    """Lista de séries escolhidas pelo run_pipeline (<stem>_selected.csv)."""
    path = Path(cfg.out_dir) / f"{cfg.stem}_selected.csv"
    if not path.exists():
        raise FileNotFoundError(f"Seleção não encontrada: {path}. Rode o download.ipynb (run_pipeline) "
                                "com o mesmo período, parâmetro e estatística.")
    return pd.read_csv(path, dtype={"time_series_id": str, "monitoring_location_id": str})


def load_daily(cfg: DownloadConfig, ts_ids: Iterable[str]) -> pd.DataFrame:
    """Junta os arquivos por série que já estão em disco (equivale ao `daily` do notebook)."""
    parts = [pd.read_parquet(p) for s in dict.fromkeys(ts_ids) if (p := cfg.series_path(s)).exists()]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=DAILY_COLUMNS)
    return pd.concat(parts, ignore_index=True)


def run_pipeline(cfg: DownloadConfig = DownloadConfig(), import_legacy: bool = True
                 ) -> tuple[pd.DataFrame, dict]:
    """Catálogo -> locais Stream -> seleção -> download por série. Pode ser chamada de novo
    quantas vezes for preciso: catálogo, locais e séries já baixadas vêm do disco."""
    Path(cfg.out_dir).mkdir(parents=True, exist_ok=True)
    client = make_client(cfg)
    if not client.config.api_key:
        _log("AVISO: USGS_API_KEY não definida. Sem chave o limite por hora é baixo (erro 429 é provável).")
    schema = read_schema(client)
    cat = load_catalog(cfg, client, schema)
    cat_streams = stream_series(cfg, client, cat)
    selected = select_series(cfg, cat_streams)
    selected.to_csv(Path(cfg.out_dir) / f"{cfg.stem}_selected.csv", index=False)

    if import_legacy:
        import_legacy_batches(cfg)
    summary = download_daily(cfg, selected["time_series_id"].dropna(), client, schema)
    return selected, summary
