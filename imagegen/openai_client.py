"""Обёртка над OpenAI Images API для генерации изображений/инфографик."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from openai import OpenAI

from .config import Config


class ImageGenerationError(RuntimeError):
    """Ошибка при обращении к OpenAI API генерации изображений."""


@dataclass
class GeneratedImage:
    data: bytes
    revised_prompt: str | None = None


def build_client(config: Config) -> OpenAI:
    kwargs = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return OpenAI(**kwargs)


def generate_images(
    client: OpenAI,
    config: Config,
    prompt: str,
    *,
    size: str | None = None,
    quality: str | None = None,
    n: int = 1,
) -> list[GeneratedImage]:
    """Генерирует одно или несколько изображений по текстовому запросу.

    Возвращает список GeneratedImage с сырыми байтами PNG.
    """
    request_kwargs = {
        "model": config.model,
        "prompt": prompt,
        "size": size or config.default_size,
        "n": n,
    }

    # Параметр quality поддерживается не всеми моделями одинаково,
    # но большинство современных моделей изображений его принимают.
    if quality or config.default_quality:
        request_kwargs["quality"] = quality or config.default_quality

    try:
        response = client.images.generate(**request_kwargs)
    except TypeError:
        # На случай, если конкретная версия SDK/модель не знает параметр quality
        request_kwargs.pop("quality", None)
        response = client.images.generate(**request_kwargs)
    except Exception as exc:  # noqa: BLE001 - хотим показать пользователю понятную ошибку
        raise ImageGenerationError(_format_api_error(exc)) from exc

    if not getattr(response, "data", None):
        raise ImageGenerationError("OpenAI вернул пустой ответ без изображений.")

    results: list[GeneratedImage] = []
    for item in response.data:
        image_bytes = _extract_bytes(item)
        results.append(
            GeneratedImage(
                data=image_bytes,
                revised_prompt=getattr(item, "revised_prompt", None),
            )
        )
    return results


def _extract_bytes(item) -> bytes:
    b64 = getattr(item, "b64_json", None)
    if b64:
        return base64.b64decode(b64)

    url = getattr(item, "url", None)
    if url:
        import urllib.request

        with urllib.request.urlopen(url) as response:  # noqa: S310 - доверенный URL от OpenAI
            return response.read()

    raise ImageGenerationError("Не удалось извлечь изображение из ответа OpenAI.")


def _format_api_error(exc: Exception) -> str:
    message = str(exc)
    return f"Ошибка обращения к OpenAI Images API: {message}"
