"""Локальный веб-интерфейс (Flask) для генерации изображений/статей.

Запускается через `python webapp.py` (см. корень проекта).
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from .config import load_config
from .jobs import JobStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in ("1", "true", "on", "yes", "да")


def create_app() -> Flask:
    """Фабрика Flask-приложения. Может выбросить ConfigError, если не найден OPENAI_API_KEY."""
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )

    config = load_config()
    output_dir = config.output_dir
    data_dir = PROJECT_ROOT / "data"
    job_store = JobStore(config, output_dir, data_dir)

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            image_model=config.model,
            text_model=config.gigachat_model,
        )

    @app.get("/api/jobs")
    def api_list_jobs():
        return jsonify(job_store.list_jobs())

    @app.get("/api/jobs/<job_id>")
    def api_get_job(job_id: str):
        job = job_store.get_job(job_id)
        if job is None:
            abort(404)
        return jsonify(job)

    @app.post("/api/generate")
    def api_generate():
        payload = request.get_json(silent=True) or request.form
        prompt = str((payload or {}).get("prompt") or "").strip()
        if not prompt:
            return jsonify({"error": "Введите запрос."}), 400

        mode = "article" if _truthy((payload or {}).get("article")) else "image"
        job = job_store.create_job(prompt, mode)
        return jsonify(job), 201

    @app.delete("/api/jobs/<job_id>")
    def api_delete_job(job_id: str):
        deleted = job_store.delete_job(job_id)
        if not deleted:
            abort(404)
        return "", 204

    @app.get("/media/<path:filename>")
    def media(filename: str):
        return send_from_directory(output_dir, filename)

    return app
