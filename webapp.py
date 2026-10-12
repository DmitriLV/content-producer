#!/usr/bin/env python3
"""Точка входа: `python webapp.py` — локальный веб-интерфейс генератора
изображений/инфографик (OpenAI) и текстов (GigaChat).

Открой http://127.0.0.1:5000 в браузере после запуска.
"""

import os
import sys

if sys.platform == "win32":
    os.system("chcp 65001 >NUL")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

from imagegen.config import ConfigError  # noqa: E402
from imagegen.web import create_app  # noqa: E402

HOST = os.getenv("WEB_HOST", "127.0.0.1")
PORT = int(os.getenv("WEB_PORT", "5000"))


def main() -> int:
    try:
        app = create_app()
    except ConfigError as exc:
        print(f"❌ {exc}")
        return 1

    print("=" * 60)
    print("🌐 Веб-интерфейс запущен")
    print(f"   Откройте в браузере: http://{HOST}:{PORT}")
    print("   Для остановки нажмите Ctrl+C")
    print("=" * 60)

    app.run(host=HOST, port=PORT, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
