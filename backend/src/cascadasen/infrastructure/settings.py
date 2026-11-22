"""Runtime configuration (env prefix CASCADASEN_)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CASCADASEN_", env_file=".env", extra="ignore")

    data_dir: Path = REPO_ROOT / "data"
    http_timeout_s: float = 120.0
    user_agent: str = "cascadasen/0.1 (Platanus Hack 26; datos abiertos)"

    # optional LLM commander and interpreter (docs/strategy.md 10); needs `uv sync --extra llm`
    llm_enabled: bool = False
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "low"  # one call per C2 decision cycle: keep it fast
    llm_timeout_s: float = 30.0
    # provider: "anthropic" (Claude API, ANTHROPIC_API_KEY or an `ant auth login` profile), "bedrock"
    # (Claude in Amazon Bedrock) or "bedrock-converse" (any Bedrock text model, model id as is). AWS
    # credentials come from the environment or a profile, never from .env
    llm_provider: Literal["anthropic", "bedrock", "bedrock-converse"] = "anthropic"
    aws_region: str | None = None
    aws_profile: str | None = None

    # in-app natural-language assistant (docs/assistant.md); needs llm_enabled and bedrock-converse
    assistant_max_steps: int = 8  # tool-use rounds per message
    assistant_deadline_s: float = 25.0  # CloudFront cuts a request at 30 s
    assistant_call_timeout_s: float = 20.0  # one Bedrock call
    assistant_history_messages: int = 30
    rate_assistant_per_minute: int = 10

    # shared sessions and persisted runs (docs/stack.md 7.1): "memory" (one process), "file"
    # (`sessions_dir`, one machine) or "s3" (`session_bucket`, several instances)
    session_store: Literal["memory", "file", "s3"] = "memory"
    session_bucket: str | None = None
    session_dir: Path | None = None  # default data_dir / "sessions"
    session_ttl_hours: float = 24
    run_cache_size: int = 20  # strategic runs kept in memory per process; evicted runs are rebuilt
    admin_enabled: bool = False  # POST /api/v1/admin/reload; off in production
    version: str = "dev"  # code version recorded in each run record
    rate_create_per_hour: int = 10
    trusted_proxy_hops: int = 0  # proxies that append to X-Forwarded-For; 2 behind CloudFront + ALB
    rate_writes_per_minute: int = 60
    rate_cuts_per_minute: int = 30
    sse_per_session_ip: int = 5
    sse_heartbeat_s: float = 15.0
    sse_poll_s: float = 1.0
    sse_head_s: float = 5.0
    sse_max_s: float = 55.0
    session_lock_timeout_s: float = 10.0  # wait for the request before it on the same session, then 409
    session_lock_max_waiters: int = 10  # requests queued behind the one in progress; more get 409 at once
    # grid documents (docs/grids.md): "local" reads `grids_dir`, "s3" reads `grids_prefix` of `grids_bucket`
    # (default: the session bucket). The prod task role cannot read grids/* until its IAM policy allows it
    grids_store: Literal["local", "s3"] = "local"
    grids_bucket: str | None = None
    grids_prefix: str = "grids/v2"
    ide_energia_url: str = (
        "https://ide-energia.minenergia.cl/server/rest/services/IDE_Energia/Visor_IDE_Energ%C3%ADa/MapServer"
    )
    infotecnica_url: str = "https://api-infotecnica.coordinador.cl/v1"
    census_url: str = (
        "https://services5.arcgis.com/hUyD8u3TeZLKPe4T/arcgis/rest/services/Censo2024_v2/FeatureServer"
    )
    pypsa_share_url: str = (
        "https://minenergia-my.sharepoint.com/:f:/g/personal/mparedes_minenergia_cl/"
        "IgCWD1vzVNdFSZGLq9yAvae7AWiPl3JViAfaI602hsQZTQ0?e=SH5uDd"
    )
    pypsa_file_url: str = (
        "https://minenergia-my.sharepoint.com/personal/mparedes_minenergia_cl/_api/web/GetFileByServerRelativeUrl("
        "'/personal/mparedes_minenergia_cl/Documents/PyPSA-CL/1.%20Datos%20de%20entrada%20a%20modelo/Topology.xlsx')/$value"
    )

    epe_webmap_url: str = "https://gisepeprd2.epe.gov.br/arcgis/rest/services/WMS_Webmap_EPE_Data/MapServer"
    osinergmin_url: str = (
        "https://gisem.osinergmin.gob.pe/serverosih/rest/services/Electricidad/MapaSEIN_Operacion/MapServer"
    )
    energia_ar_url: str = "http://datos.energia.gob.ar/dataset"
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def regional_dir(self) -> Path:
        return self.processed_dir / "latam"

    @property
    def snapshot_path(self) -> Path:
        return self.processed_dir / "grid_snapshot.json"

    @property
    def grids_dir(self) -> Path:
        return self.data_dir / "grids"

    @property
    def sessions_dir(self) -> Path:
        return self.session_dir or self.data_dir / "sessions"


def get_settings() -> Settings:
    return Settings()
