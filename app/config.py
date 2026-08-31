"""Configuración de la app, leída de variables de entorno / archivo .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = "dev-inseguro-cambiar-en-produccion"
    database_url: str = "sqlite:///./phantomfish.db"
    storage_dir: Path = BASE_DIR / "storage" / "uploads"
    default_rate_type: str = "blue"
    seed_password: str = "phantomfish"

    # Socios que se crean la primera vez que arranca la app.
    # (nombre, porcentaje de reparto, usuario)
    seed_partners: list[tuple[str, str, str]] = [
        ("Jairo", "35.00", "jairo"),
        ("Sebastián", "65.00", "sebastian"),
    ]

    app_name: str = "Phantom Fish"

    # En producción (HTTPS) la cookie de sesión debe viajar solo por HTTPS.
    cookie_secure: bool = False

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_dir)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    return settings
