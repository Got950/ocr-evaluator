from __future__ import annotations

from pathlib import Path
from typing import FrozenSet, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")

    environment: str = Field(default="dev", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    ai_grading_enabled: bool = Field(default=True, alias="AI_GRADING_ENABLED")
    max_concurrent_evaluations: int = Field(default=4, alias="MAX_CONCURRENT_EVALUATIONS")
    enable_rate_limiting: bool = Field(default=True, alias="ENABLE_RATE_LIMITING")

    trusted_hosts: str = Field(default="*", alias="TRUSTED_HOSTS")
    cors_origins: Optional[str] = Field(default=None, alias="CORS_ORIGINS")
    enable_security_headers: bool = Field(default=True, alias="ENABLE_SECURITY_HEADERS")
    gzip_minimum_size: int = Field(default=1000, alias="GZIP_MINIMUM_SIZE")

    upload_dir: Path = Field(default=Path("uploads"), alias="UPLOAD_DIR")
    max_upload_size_bytes: int = Field(default=8 * 1024 * 1024, alias="MAX_UPLOAD_SIZE_BYTES")
    allowed_image_mime_types: FrozenSet[str] = Field(
        default=frozenset({"image/png", "image/jpeg"}), alias="ALLOWED_IMAGE_MIME_TYPES"
    )

    hard_rubric_evaluator: Optional[str] = Field(default=None, alias="HARD_RUBRIC_EVALUATOR")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    secret_key: str = Field(default="change-me-in-production-min-32-chars!!", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    s3_bucket: Optional[str] = Field(default=None, alias="S3_BUCKET")
    s3_endpoint_url: Optional[str] = Field(default=None, alias="S3_ENDPOINT_URL")
    aws_access_key_id: Optional[str] = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")


def get_settings() -> Settings:
    return Settings()

