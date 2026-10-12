"""Вспомогательные функции: безопасные имена файлов и т.п."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_FORBIDDEN_CHARS = r'<>:"/\\|?*\n\r\t'
_FORBIDDEN_RE = re.compile(f"[{re.escape(_FORBIDDEN_CHARS)}]")
_WHITESPACE_RE = re.compile(r"\s+")


def slugify_prompt(prompt: str, max_length: int = 60) -> str:
    """Превращает произвольный текст запроса в безопасное имя файла (без расширения)."""
    cleaned = _FORBIDDEN_RE.sub(" ", prompt).strip()
    cleaned = _WHITESPACE_RE.sub("_", cleaned)
    cleaned = cleaned.strip("._")
    if not cleaned:
        cleaned = "image"
    return cleaned[:max_length].rstrip("._")


def build_filename(prompt: str, index: int = 0, extension: str = "png") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify_prompt(prompt)
    suffix = f"_{index + 1}" if index > 0 else ""
    return f"{timestamp}_{slug}{suffix}.{extension}"


def unique_path(directory: Path, filename: str) -> Path:
    """Гарантирует, что путь не перезапишет существующий файл."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem, dot, ext = filename.rpartition(".")
    counter = 1
    while True:
        new_name = f"{stem}_{counter}.{ext}" if dot else f"{filename}_{counter}"
        candidate = directory / new_name
        if not candidate.exists():
            return candidate
        counter += 1
