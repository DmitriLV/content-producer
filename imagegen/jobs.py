"""Хранилище и обработчик задач для веб-интерфейса.

Задачи (запросы пользователя из веб-формы) обрабатываются последовательно
в одном фоновом потоке (очередь), чтобы не перегружать API и не тратить
лишние деньги на параллельные запросы. Прогресс отображается по этапам
и плавно "симулируется" по времени, так как ни OpenAI, ни GigaChat не
отдают реальный процент готовности.
"""

from __future__ import annotations

import concurrent.futures
import json
import queue
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import Config, ConfigError
from .gigachat_client import ArticleGenerationError, build_gigachat_client, generate_article
from .openai_client import ImageGenerationError, build_client, generate_images
from .utils import build_filename, unique_path

HISTORY_FILE_NAME = "history.json"

# Ориентировочное время каждого этапа в секундах — используется только
# для того, чтобы прогресс-бар плавно двигался, пока идёт ожидание ответа API.
ESTIMATED_TEXT_SECONDS = 10
ESTIMATED_IMAGE_SECONDS = 110

STAGE_LABELS = {
    "queued": "В очереди",
    "writing_text": "Пишу текст (GigaChat)",
    "generating_image": "Генерирую изображение (OpenAI)",
    "done": "Готово",
    "error": "Ошибка",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class JobStore:
    """Потокобезопасное хранилище задач с фоновой последовательной обработкой."""

    def __init__(self, config: Config, output_dir: Path, data_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.data_dir / HISTORY_FILE_NAME

        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._queue: "queue.Queue[str]" = queue.Queue()

        self._openai_client = build_client(config)
        self._gigachat_client = None  # создаётся лениво, только если нужен режим статьи

        self._load_history()

        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    # ------------------------------------------------------------------
    # Персистентность
    # ------------------------------------------------------------------

    def _load_history(self) -> None:
        if not self.history_path.exists():
            return
        try:
            data = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        for job in data:
            # Задачи, которые не успели доработать до перезапуска сервера,
            # помечаем как прерванные, чтобы не "зависали" в интерфейсе.
            if job.get("status") in ("queued", "running"):
                job["status"] = "error"
                job["stage"] = "error"
                job["error"] = "Обработка была прервана перезапуском сервера."
            self._jobs[job["id"]] = job

    def _save_history_locked(self) -> None:
        jobs_sorted = sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)
        tmp_path = self.history_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(jobs_sorted, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp_path.replace(self.history_path)

    # ------------------------------------------------------------------
    # Публичное API
    # ------------------------------------------------------------------

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                (dict(job) for job in self._jobs.values()),
                key=lambda j: j["created_at"],
                reverse=True,
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def create_job(self, prompt: str, mode: str) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        now = _now()
        job = {
            "id": job_id,
            "mode": mode,  # "image" | "article"
            "prompt": prompt,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "text": None,
            "text_file": None,
            "image_files": [],
            "error": None,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._save_history_locked()
        self._queue.put(job_id)
        return dict(job)

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is None:
                return False
            filenames = list(job.get("image_files") or [])
            if job.get("text_file"):
                filenames.append(job["text_file"])
            for filename in filenames:
                path = self.output_dir / filename
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
            self._save_history_locked()
            return True

    # ------------------------------------------------------------------
    # Обработка задач
    # ------------------------------------------------------------------

    def _update_job(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(fields)
            job["updated_at"] = _now()
            self._save_history_locked()

    def _get_gigachat_client(self):
        if self._gigachat_client is None:
            self._gigachat_client = build_gigachat_client(self.config)
        return self._gigachat_client

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._process_job(job_id)
            except Exception as exc:  # noqa: BLE001 - не даём воркеру упасть насовсем
                self._update_job(job_id, status="error", stage="error", error=str(exc))
            finally:
                self._queue.task_done()

    def _run_with_progress(
        self,
        func: Callable[[], Any],
        *,
        start_pct: float,
        end_pct: float,
        estimated_seconds: float,
        on_tick: Callable[[int], None],
    ) -> Any:
        """Выполняет func() в отдельном потоке, эмулируя плавный прогресс
        между start_pct и end_pct, пока ждём реальный результат."""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(func)
            start_time = time.monotonic()
            span = end_pct - start_pct
            cap = start_pct + span * 0.92  # не доходим до конца, пока нет реального результата

            while not future.done():
                elapsed = time.monotonic() - start_time
                ratio = min(0.95, elapsed / max(estimated_seconds, 1))
                pct = min(start_pct + span * ratio, cap)
                on_tick(int(pct))
                time.sleep(0.4)

            return future.result()
        finally:
            executor.shutdown(wait=False)

    def _process_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return

        prompt = job["prompt"]
        mode = job["mode"]
        self._update_job(job_id, status="running")

        image_prompt = prompt

        if mode == "article":
            self._update_job(job_id, stage="writing_text", progress=2)
            try:
                gigachat_client = self._get_gigachat_client()
            except ConfigError as exc:
                self._update_job(job_id, status="error", stage="error", error=str(exc))
                return

            try:
                article_text = self._run_with_progress(
                    lambda: generate_article(gigachat_client, prompt),
                    start_pct=2,
                    end_pct=40,
                    estimated_seconds=ESTIMATED_TEXT_SECONDS,
                    on_tick=lambda pct: self._update_job(job_id, progress=pct),
                )
            except ArticleGenerationError as exc:
                self._update_job(job_id, status="error", stage="error", error=str(exc))
                return

            text_path = unique_path(self.output_dir, build_filename(prompt, extension="txt"))
            text_path.write_text(article_text, encoding="utf-8")
            self._update_job(
                job_id,
                text=article_text,
                text_file=text_path.name,
                stage="generating_image",
                progress=42,
            )

            image_prompt = (
                "Создай аккуратную инфографику на русском языке о здоровье, питании, "
                f"полезных нутриентах и витаминах на тему «{prompt}». Используй следующий текст "
                "как основу для заголовка и ключевых пунктов (не обязательно копировать дословно, "
                f"выдели главное):\n\n{article_text}\n\n"
                "Стиль: чистый современный дизайн, дружелюбная цветовая палитра, иконки, "
                "крупный заголовок, разбивка на понятные блоки, подходит для соцсетей."
            )
            image_start_pct = 42
        else:
            self._update_job(job_id, stage="generating_image", progress=5)
            image_start_pct = 5

        try:
            images = self._run_with_progress(
                lambda: generate_images(self._openai_client, self.config, image_prompt, n=1),
                start_pct=image_start_pct,
                end_pct=98,
                estimated_seconds=ESTIMATED_IMAGE_SECONDS,
                on_tick=lambda pct: self._update_job(job_id, progress=pct),
            )
        except ImageGenerationError as exc:
            self._update_job(job_id, status="error", stage="error", error=str(exc))
            return

        image_files = []
        for index, image in enumerate(images):
            path = unique_path(self.output_dir, build_filename(prompt, index=index))
            path.write_bytes(image.data)
            image_files.append(path.name)

        self._update_job(
            job_id,
            status="done",
            stage="done",
            progress=100,
            image_files=image_files,
        )
