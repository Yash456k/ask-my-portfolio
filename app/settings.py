import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    groq_api_key: str = Field(min_length=20)
    openrouter_api_key: str | None = Field(default=None, min_length=20)
    database_url: str = Field(min_length=20)
    database_bootstrap_schema: bool = True
    frontend_origins: Annotated[list[str], NoDecode]
    frontend_origin_regex: str | None = None
    public_api_url: str
    allowed_hosts: Annotated[list[str], NoDecode]
    trusted_proxy_cidrs: Annotated[list[str], NoDecode] = [
        "127.0.0.1/32",
        "172.16.0.0/12",
    ]
    ip_hash_salt: str = Field(min_length=24)
    verify_fallback_token: str = Field(min_length=24)
    per_ip_daily_limit: int = Field(default=15, ge=1, le=1000)
    global_daily_limit: int = Field(default=120, ge=10, le=100000)
    global_monthly_budget_micro_usd: int = Field(
        default=1_800_000,
        ge=100_000,
        le=100_000_000,
    )
    budget_input_token_reserve: int = Field(default=32_000, ge=1_000, le=100_000)
    # Process-local guardrails ahead of body parsing and durable database quotas.
    admission_window_seconds: int = Field(default=10, ge=1, le=60)
    admission_global_burst: int = Field(default=120, ge=1, le=10000)
    admission_per_ip_burst: int = Field(default=30, ge=1, le=1000)
    admission_max_clients: int = Field(default=4096, ge=1, le=65536)
    admission_max_concurrent: int = Field(default=64, ge=1, le=256)
    chat_global_burst: int = Field(default=12, ge=1, le=1000)
    chat_per_ip_burst: int = Field(default=4, ge=1, le=100)
    chat_max_concurrent: int = Field(default=4, ge=1, le=32)
    chat_per_ip_concurrent: int = Field(default=2, ge=1, le=8)
    health_cache_seconds: float = Field(default=3.0, ge=1, le=30)
    activity_cache_path: Path = Path("var/activity/activity.json")
    log_level: str = "INFO"

    @field_validator("frontend_origins", "allowed_hosts", "trusted_proxy_cidrs", mode="before")
    @classmethod
    def split_csv(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("frontend_origins")
    @classmethod
    def validate_origins(cls, value: list[str]) -> list[str]:
        if not value or "*" in value:
            raise ValueError("FRONTEND_ORIGINS must be an explicit non-wildcard list")
        if any(not origin.startswith("https://") for origin in value):
            raise ValueError("all production frontend origins must use HTTPS")
        return value

    @field_validator("frontend_origin_regex")
    @classmethod
    def validate_origin_regex(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not value.startswith("^https://") or not value.endswith("$") or "*" == value:
            raise ValueError("FRONTEND_ORIGIN_REGEX must be an anchored HTTPS pattern")
        try:
            re.compile(value)
        except re.error as error:
            raise ValueError("FRONTEND_ORIGIN_REGEX must be a valid regular expression") from error
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
