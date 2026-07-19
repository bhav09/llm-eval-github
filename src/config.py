"""Application configuration from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    do_api: str = Field(default="", alias="DO_API")
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    concurrency: int = Field(default=8, alias="CONCURRENCY")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    request_timeout_sec: int = Field(default=60, alias="REQUEST_TIMEOUT_SEC")
    body_truncate_chars: int = Field(default=8000, alias="BODY_TRUNCATE_CHARS")
    model_context_tokens: int = Field(default=32768, alias="MODEL_CONTEXT_TOKENS")
    completion_budget: int = Field(default=256, alias="COMPLETION_BUDGET")
    checkpoint_every_n: int = Field(default=50, alias="CHECKPOINT_EVERY_N")
    corpus_path: Path = Field(default=Path("data/corpus"), alias="CORPUS_PATH")
    ground_truth_path: Path = Field(default=Path("data/ground_truth"), alias="GROUND_TRUTH_PATH")
    prompt_version: str = Field(default="", alias="PROMPT_VERSION")
    adjudicator_model: str = Field(
        default="deepseek-v4-pro",
        alias="ADJUDICATOR_MODEL",
    )
    github_repo: str = Field(default="digitalocean/doctl", alias="GITHUB_REPO")
    github_api_base: str = Field(
        default="https://api.github.com",
        alias="GITHUB_API_BASE",
    )
    si_api_base: str = Field(
        default="https://inference.do-ai.run/v1",
        alias="SI_API_BASE",
    )

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return ROOT_DIR / path


def get_settings() -> Settings:
    return Settings()
