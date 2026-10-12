"""Интерактивный CLI для генерации изображений/инфографик через OpenAI
и текстов о ЗОЖ/питании через GigaChat с последующей инфографикой."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config, ConfigError, load_config
from .gigachat_client import ArticleGenerationError, build_gigachat_client, generate_article
from .notifier import notify_error, notify_ready, notify_text_ready
from .openai_client import ImageGenerationError, build_client, generate_images
from .utils import build_filename, unique_path

EXIT_WORDS = {"exit", "quit", "q", "выход", "стоп", "stop"}
ARTICLE_PREFIXES = ("статья:", "текст:", "article:", "пост:")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "CLI-генератор изображений, инфографик и текстов на основе OpenAI и GigaChat. "
            "Запустите без аргументов для интерактивного режима."
        )
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help=(
            "Текст запроса (изображение) или тема (при --article). "
            "Если не указан — запустится диалоговый режим."
        ),
    )
    parser.add_argument(
        "--article",
        action="store_true",
        help=(
            "Режим статьи: сначала GigaChat пишет короткий текст на заданную тему "
            "(ЗОЖ/питание/нутриенты/витамины), сохраняет его, а затем OpenAI создаёт "
            "инфографику на основе этого текста."
        ),
    )
    parser.add_argument(
        "--size",
        default=None,
        help="Размер изображения, например 1024x1024, 1024x1536, 1536x1024.",
    )
    parser.add_argument(
        "--quality",
        default=None,
        help="Качество изображения: low, medium, high, auto (зависит от модели).",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Сколько изображений сгенерировать за один запрос (по умолчанию 1).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Папка для сохранения результатов (по умолчанию ./output).",
    )
    return parser.parse_args(argv)


def process_prompt(
    openai_client,
    config: Config,
    prompt: str,
    *,
    size: str | None,
    quality: str | None,
    count: int,
    output_dir: Path,
) -> None:
    """Генерирует изображение напрямую по текстовому запросу пользователя."""
    prompt = prompt.strip()
    if not prompt:
        return

    print(f"⏳ Генерирую изображение по запросу: \"{prompt}\" ...")
    try:
        images = generate_images(
            openai_client, config, prompt, size=size, quality=quality, n=count
        )
    except ImageGenerationError as exc:
        print(f"❌ {exc}")
        notify_error(prompt, str(exc))
        return

    saved_paths: list[Path] = []
    for index, image in enumerate(images):
        filename = build_filename(prompt, index=index)
        path = unique_path(output_dir, filename)
        path.write_bytes(image.data)
        saved_paths.append(path)
        print(f"✅ Сохранено: {path}")
        if image.revised_prompt and image.revised_prompt != prompt:
            print(f"   (уточнённый запрос модели: {image.revised_prompt})")

    if saved_paths:
        notify_ready(saved_paths[0], prompt)


def process_article(
    get_gigachat_client,
    openai_client,
    config: Config,
    topic: str,
    *,
    size: str | None,
    quality: str | None,
    count: int,
    output_dir: Path,
) -> None:
    """Пишет короткий текст на тему через GigaChat, сохраняет его,
    а затем создаёт инфографику на основе этого текста через OpenAI."""
    topic = topic.strip()
    if not topic:
        return

    try:
        gigachat_client = get_gigachat_client()
    except ConfigError as exc:
        print(f"❌ {exc}")
        return

    print(f"✍️  Пишу текст по теме: \"{topic}\" (GigaChat) ...")
    try:
        article_text = generate_article(gigachat_client, topic)
    except ArticleGenerationError as exc:
        print(f"❌ {exc}")
        notify_error(topic, str(exc))
        return

    text_path = unique_path(output_dir, build_filename(topic, extension="txt"))
    text_path.write_text(article_text, encoding="utf-8")
    print(f"✅ Текст сохранён: {text_path}")
    print("-" * 40)
    print(article_text)
    print("-" * 40)
    notify_text_ready(text_path, topic)

    image_prompt = (
        "Создай аккуратную инфографику на русском языке о здоровье, питании, "
        f"полезных нутриентах и витаминах на тему «{topic}». Используй следующий текст "
        "как основу для заголовка и ключевых пунктов (не обязательно копировать дословно, "
        f"выдели главное):\n\n{article_text}\n\n"
        "Стиль: чистый современный дизайн, дружелюбная цветовая палитра, иконки, "
        "крупный заголовок, разбивка на понятные блоки, подходит для соцсетей."
    )

    print("🎨 Генерирую инфографику на основе текста (OpenAI) ...")
    try:
        images = generate_images(
            openai_client, config, image_prompt, size=size, quality=quality, n=count
        )
    except ImageGenerationError as exc:
        print(f"❌ {exc}")
        notify_error(topic, str(exc))
        return

    saved_paths: list[Path] = []
    for index, image in enumerate(images):
        path = unique_path(output_dir, build_filename(topic, index=index))
        path.write_bytes(image.data)
        saved_paths.append(path)
        print(f"✅ Инфографика сохранена: {path}")

    if saved_paths:
        notify_ready(saved_paths[0], topic)


def _split_article_prefix(raw: str) -> tuple[bool, str]:
    """Проверяет, начинается ли ввод с префикса режима статьи (например 'статья: ...')."""
    lower = raw.lower()
    for prefix in ARTICLE_PREFIXES:
        if lower.startswith(prefix):
            return True, raw[len(prefix):].strip()
    return False, raw


def run_interactive(
    openai_client,
    get_gigachat_client,
    config: Config,
    args: argparse.Namespace,
    output_dir: Path,
) -> None:
    print("=" * 60)
    print("🎨 Генератор изображений, инфографик и текстов (OpenAI + GigaChat)")
    print(f"Модель изображений: {config.model}")
    print(f"Модель текста: {config.gigachat_model}")
    print(f"Папка сохранения: {output_dir}")
    print()
    print("Обычный запрос           → инфографика/изображение по запросу (OpenAI).")
    print("'статья: <тема>'         → GigaChat напишет текст о ЗОЖ/питании на тему,")
    print("                            сохранит его и создаст инфографику по тексту.")
    if args.article:
        print("(Включён флаг --article: все запросы обрабатываются как темы статей.)")
    print("Для выхода введите: exit / выход")
    print("=" * 60)

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nЗавершение работы.")
            break

        if not raw:
            continue
        if raw.lower() in EXIT_WORDS:
            print("До встречи!")
            break

        is_article, text = _split_article_prefix(raw)
        is_article = is_article or args.article

        if is_article:
            process_article(
                get_gigachat_client,
                openai_client,
                config,
                text,
                size=args.size,
                quality=args.quality,
                count=max(1, args.count),
                output_dir=output_dir,
            )
        else:
            process_prompt(
                openai_client,
                config,
                text,
                size=args.size,
                quality=args.quality,
                count=max(1, args.count),
                output_dir=output_dir,
            )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"❌ {exc}")
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    openai_client = build_client(config)

    gigachat_client_cache: dict[str, object] = {}

    def get_gigachat_client():
        if "client" not in gigachat_client_cache:
            gigachat_client_cache["client"] = build_gigachat_client(config)
        return gigachat_client_cache["client"]

    prompt_text = " ".join(args.prompt).strip()
    if prompt_text:
        if args.article:
            process_article(
                get_gigachat_client,
                openai_client,
                config,
                prompt_text,
                size=args.size,
                quality=args.quality,
                count=max(1, args.count),
                output_dir=output_dir,
            )
        else:
            process_prompt(
                openai_client,
                config,
                prompt_text,
                size=args.size,
                quality=args.quality,
                count=max(1, args.count),
                output_dir=output_dir,
            )
    else:
        run_interactive(openai_client, get_gigachat_client, config, args, output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
