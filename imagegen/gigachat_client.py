"""Обёртка над GigaChat API для генерации коротких текстов о ЗОЖ и питании."""

from __future__ import annotations

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from .config import Config, ConfigError

SYSTEM_PROMPT = (
    "Ты — редактор блога о здоровом образе жизни, питании, полезных нутриентах и витаминах. "
    "Пиши короткие, дружелюбные и достоверные тексты на русском языке для социальных сетей "
    "и инфографики. Объём — 80-150 слов. Текст должен быть структурирован (короткие абзацы "
    "или пункты), без markdown-разметки (без **, #, списков со звёздочками), без вступлений "
    "вроде «Конечно!» и без хэштегов/подписей в конце. Пиши по существу и по делу."
)


class ArticleGenerationError(RuntimeError):
    """Ошибка при обращении к GigaChat API."""


def build_gigachat_client(config: Config) -> GigaChat:
    if not config.gigachat_credentials:
        raise ConfigError(
            "Не найден GIGACHAT_CREDENTIALS в .env. Добавьте его, чтобы использовать режим статей."
        )
    return GigaChat(
        credentials=config.gigachat_credentials,
        scope=config.gigachat_scope,
        model=config.gigachat_model,
        verify_ssl_certs=False,
    )


def generate_article(client: GigaChat, topic: str) -> str:
    """Генерирует короткий текст на заданную тему (ЗОЖ/питание/нутриенты)."""
    topic = topic.strip()
    if not topic:
        raise ArticleGenerationError("Пустая тема для статьи.")

    chat = Chat(
        messages=[
            Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
            Messages(
                role=MessagesRole.USER,
                content=f'Напиши короткий текст на тему: "{topic}".',
            ),
        ],
        temperature=0.7,
    )

    try:
        response = client.chat(chat)
    except Exception as exc:  # noqa: BLE001 - хотим показать пользователю понятную ошибку
        raise ArticleGenerationError(f"Ошибка обращения к GigaChat API: {exc}") from exc

    if not response.choices:
        raise ArticleGenerationError("GigaChat вернул пустой ответ.")

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise ArticleGenerationError("GigaChat вернул пустой текст.")
    return text
