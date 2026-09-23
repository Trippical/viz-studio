"""Settings shared by the server and the CLI. All from VIZ_* environment variables."""
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ids import normalize_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIZ_", extra="ignore")

    storage: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None
    root_prefix: str = "viz/"
    local_dir: Path = Path("./sample-bucket")
    tree_ttl_seconds: int = 60
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    auth_header: str = "X-Forwarded-Email"
    max_document_bytes: int = 1_048_576
    web_dist: Path = Path("./web/dist")
    host: str = "127.0.0.1"
    port: int = 8000

    @field_validator("root_prefix")
    @classmethod
    def _normalize_root(cls, value: str) -> str:
        return normalize_root(value)

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
