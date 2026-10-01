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
    allowed_hosts: str = "localhost,127.0.0.1"
    auth_header: str = "X-Forwarded-Email"
    # True in deployment (Helm sets it): every request except GET and HEAD /api/health
    # needs a non-empty auth_header, or gets 401. False for local development and viz preview.
    require_identity: bool = False
    max_document_bytes: int = 1_048_576
    web_dist: Path = Path("./web/dist")
    host: str = "127.0.0.1"
    port: int = 8000

    # Publisher (viz CLI) settings. The server ignores them.
    author: str | None = None
    query_deny: str = ""
    # Column names that look like personal data. "name" matches alone, or after a person
    # word such as first_ or customer_; product_name and region_name do not (finding A21).
    pii_pattern: str = (
        r"(?i)(email|ssn|phone|address|dob|salary|\bip\b|^name$"
        r"|(?<![a-z0-9])(first|last|full|given|family|middle|maiden|nick|sur|user|customer|client|contact"
        r"|person|employee|manager|owner|member|patient|student|agent|rep|display)_?name(?![a-z0-9]))"
    )
    staging_dir: Path = Path("./.viz-staging")

    @field_validator("root_prefix")
    @classmethod
    def _normalize_root(cls, value: str) -> str:
        return normalize_root(value)

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
