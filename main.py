#!/usr/bin/env python3
"""Точка входа: `python main.py` — CLI-генератор изображений/инфографик через OpenAI."""

import os
import sys

if sys.platform == "win32":
    # Переключаем кодовую страницу консоли на UTF-8, чтобы корректно
    # отображались кириллица и эмодзи в PowerShell/cmd.
    os.system("chcp 65001 >NUL")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

from imagegen.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
