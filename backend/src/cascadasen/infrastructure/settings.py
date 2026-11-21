"""Runtime configuration (env prefix CASCADASEN_)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CASCADASEN_", env_file=".env", extra="ignore")

    data_dir: Path = REPO_ROOT / "data"
    http_timeout_s: float = 120.0
    user_agent: str = "cascadasen/0.1 (Platanus Hack 26; datos abiertos)"

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

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def snapshot_path(self) -> Path:
        return self.processed_dir / "grid_snapshot.json"


def get_settings() -> Settings:
    return Settings()
