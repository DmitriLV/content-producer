"""Загрузка конфигурации приложения из переменных окружения / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта — папка, где лежит .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# Загружаем .env один раз при импорте модуля
load_dotenv(dotenv_path=ENV_PATH)

DEFAULT_MODEL = "gpt-image-1"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "high"
DEFAULT_OUTPUT_DIR_NAME = "output"
DEFAULT_GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_GIGACHAT_MODEL = "GigaChat-2"


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str | None
    model: str
    output_dir: Path
    default_size: str
    default_quality: str
    gigachat_credentials: str | None
    gigachat_scope: str
    gigachat_model: str


class ConfigError(RuntimeError):
    """Ошибка конфигурации (например, не найден ключ API)."""


def load_config() -> Config:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "Не найден OPENAI_API_KEY. Добавьте его в файл .env "
            f"по пути: {ENV_PATH}"
        )

    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    model = os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_MODEL

    output_dir_name = os.getenv("OUTPUT_DIR", "").strip() or DEFAULT_OUTPUT_DIR_NAME
    output_dir = Path(output_dir_name)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    default_size = os.getenv("OPENAI_IMAGE_SIZE", "").strip() or DEFAULT_SIZE
    default_quality = os.getenv("OPENAI_IMAGE_QUALITY", "").strip() or DEFAULT_QUALITY

    # GigaChat не обязателен для базового режима генерации изображений,
    # поэтому отсутствие credentials здесь не приводит к ошибке.
    gigachat_credentials = os.getenv("GIGACHAT_CREDENTIALS", "").strip() or None
    gigachat_scope = os.getenv("GIGACHAT_SCOPE", "").strip() or DEFAULT_GIGACHAT_SCOPE
    gigachat_model = os.getenv("GIGACHAT_MODEL", "").strip() or DEFAULT_GIGACHAT_MODEL

    return Config(
        api_key=api_key,
        base_url=base_url,
        model=model,
        output_dir=output_dir,
        default_size=default_size,
        default_quality=default_quality,
        gigachat_credentials=gigachat_credentials,
        gigachat_scope=gigachat_scope,
        gigachat_model=gigachat_model,
    )
