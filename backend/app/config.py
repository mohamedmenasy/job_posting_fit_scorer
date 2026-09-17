from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    typesafe_api_key: SecretStr | None = None
    typesafe_model: str | None = None
    typesafe_max_concurrency: int = 4
    typesafe_token_budget: int = 24000
    typesafe_log_level: str = "warning"
    evaluator: Literal["typesafe", "fake"] = "typesafe"
    evaluation_workers: int = 4
    database_url: str = "sqlite:///./data/jobfit.db"
    log_level: str = "info"

    @property
    def model_name(self) -> str:
        return "fake" if self.evaluator == "fake" else (self.typesafe_model or "")

    def validate_for_startup(self) -> None:
        if self.evaluator != "typesafe":
            return
        if not self.typesafe_api_key or not self.typesafe_api_key.get_secret_value().strip():
            raise RuntimeError("TYPESAFE_API_KEY is required when EVALUATOR=typesafe (or set EVALUATOR=fake)")
        if not self.typesafe_model or self.typesafe_model == "jev-latest":
            raise RuntimeError("TYPESAFE_MODEL must be set to a pinned model name (not jev-latest) when EVALUATOR=typesafe")
