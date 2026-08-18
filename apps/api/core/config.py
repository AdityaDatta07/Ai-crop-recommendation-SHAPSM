"""Configuration, read from the environment exactly once.

Names mirror .env.example at the repo root. Nothing here has a secret default;
anything sensitive defaults to empty and the feature that needs it degrades.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

# Load .env into the PROCESS environment, not just into Settings.
#
# pydantic-settings reads .env straight into the model and leaves os.environ
# untouched. That is fine for anything reading Settings, but services/geo and
# services/ml are plain packages with no web dependency — they read os.getenv.
# The result was a server whose Settings said use_mock_geo=False while
# services/geo, seeing an empty os.environ, defaulted to True and served mock
# data. /health reported "mock" with a correct .env sitting right there.
#
# Loading here, in the module every entry point already imports, keeps the two
# halves of the app agreed on what the configuration actually is.
try:
    from dotenv import load_dotenv

    _ENV_FILE = REPO_ROOT / ".env"
    if _ENV_FILE.exists():
        # override=False so a real environment variable still wins over the
        # file, which is what deployment platforms expect.
        load_dotenv(_ENV_FILE, override=False)
except ImportError:  # pragma: no cover
    logger.warning("python-dotenv not installed; .env will not be read")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    log_level: str = "info"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_allowed_origins: str = "http://localhost:3000"

    # Skip Earth Engine and serve mock conditions. Defaults true so the project
    # runs on a fresh clone with no credentials at all.
    use_mock_geo: bool = True

    supabase_url: str = ""
    supabase_service_role_key: str = ""

    market_price_api_key: str = ""
    data_gov_in_api_key: str = ""

    # Earth Engine. The base64 form is preferred on hosts with no filesystem
    # you would want to leave a private key on.
    gee_project_id: str = ""
    gee_private_key_path: str = ""
    gee_service_account_key_b64: str = ""

    @property
    def earth_engine_configured(self) -> bool:
        return bool(self.gee_project_id) and bool(
            self.gee_service_account_key_b64 or self.gee_private_key_path
        )

    @property
    def agmarknet_configured(self) -> bool:
        return bool(self.market_price_api_key or self.data_gov_in_api_key)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
