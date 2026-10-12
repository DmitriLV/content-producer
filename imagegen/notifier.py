"""Системные уведомления о готовности визуализации."""

from __future__ import annotations

from pathlib import Path


def notify(title: str, message: str, *, timeout: int = 8) -> None:
    """Показывает системное уведомление. Если это невозможно — просто печатает в консоль."""
    try:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name="Image Generator",
            timeout=timeout,
        )
    except Exception:
        # Уведомления не критичны для работы приложения — не должны его ронять
        print(f"[Уведомление] {title}: {message}")


def notify_ready(path: Path, prompt: str) -> None:
    short_prompt = prompt if len(prompt) <= 80 else prompt[:77] + "..."
    notify(
        title="Изображение готово ✅",
        message=f"{short_prompt}\nСохранено: {path.name}",
    )


def notify_text_ready(path: Path, topic: str) -> None:
    short_topic = topic if len(topic) <= 80 else topic[:77] + "..."
    notify(
        title="Текст готов ✅",
        message=f"{short_topic}\nСохранено: {path.name}",
    )


def notify_error(prompt: str, error_message: str) -> None:
    short_prompt = prompt if len(prompt) <= 80 else prompt[:77] + "..."
    notify(
        title="Ошибка генерации ❌",
        message=f"{short_prompt}\n{error_message}",
    )
