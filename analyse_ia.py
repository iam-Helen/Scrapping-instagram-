"""ИИ-анализ лучших публикаций недели через Claude API.

Необязательный шаг: если переменная ANTHROPIC_API_KEY не задана,
анализ просто пропускается, а обычный отчёт всё равно отправляется.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from veille import Publication

MODELE = "claude-opus-5-5"
LONGUEUR_LEGENDE_MAX = 1500  # символов подписи на публикацию, чтобы держать стоимость низкой

SYSTEME = """Ты помогаешь психологу, который ведёт блог в Instagram, разбирать, \
какой контент работает в его нише. Тебе дают лучшие публикации недели других \
психологов: формат, цифры и подпись.

Напиши разбор на русском языке, обращаясь к автору на «ты». Структура:

1. Для каждой публикации (по номеру и @аккаунту): почему она сработала — тема, \
боль аудитории, хук в первой строке, формат, призыв к действию. 2–3 предложения, \
конкретно, со ссылкой на детали подписи.
2. «Общие закономерности»: 3–5 пунктов о том, что объединяет успешный контент этой недели.
3. «Идеи для тебя»: 5 конкретных идей публикаций на основе этих закономерностей. \
Для каждой — формат и готовая первая строка (хук). Идеи должны быть самостоятельными, \
а не пересказом чужих публикаций.

Пиши обычным текстом без Markdown (без **, #, таблиц). Можно эмодзи в начале \
разделов. Будь краток: весь разбор — не длиннее 3500 символов. Не придумывай \
факты, которых нет в данных; если подписи нет, опирайся на формат и цифры."""


def _decrire(pubs: list[Publication]) -> str:
    blocs = []
    for i, p in enumerate(pubs, 1):
        chiffres = f"лайки {p.likes}, комментарии {p.commentaires}"
        if p.vues:
            chiffres += f", просмотры {p.vues}"
        if p.ratio:
            chiffres += f", в {p.ratio:.1f} раза больше реакций, чем обычно у аккаунта"
        legende = p.legende[:LONGUEUR_LEGENDE_MAX] or "(без подписи)"
        blocs.append(
            f"<publication numero=\"{i}\">\n"
            f"Аккаунт: @{p.compte}\nФормат: {p.format}\nЦифры: {chiffres}\n"
            f"Подпись:\n{legende}\n</publication>"
        )
    return "\n\n".join(blocs)


def analyser_avec_ia(pubs: list[Publication]) -> str | None:
    """Возвращает текст разбора или None, если анализ недоступен."""
    if not pubs or not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    import anthropic

    client = anthropic.Anthropic()
    try:
        reponse = client.beta.messages.create(
            model=MODELE,
            max_tokens=16000,
            output_config={"effort": "high"},
            # При отказе модели запрос автоматически повторяется на резервной модели.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEME,
            messages=[{
                "role": "user",
                "content": "Лучшие публикации недели:\n\n" + _decrire(pubs),
            }],
        )
    except anthropic.AuthenticationError:
        print("ИИ-анализ пропущен: неверный ANTHROPIC_API_KEY.")
        return None
    except anthropic.PermissionDeniedError:
        print("ИИ-анализ пропущен: у ключа нет доступа (проверь баланс в консоли Anthropic).")
        return None
    except anthropic.BadRequestError as e:
        print(f"ИИ-анализ пропущен: ошибка запроса ({e.message}).")
        return None
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        print(f"ИИ-анализ пропущен: {type(e).__name__}: {e}")
        return None

    if reponse.stop_reason == "refusal":
        print("ИИ-анализ пропущен: модель отказалась отвечать.")
        return None

    texte = "".join(b.text for b in reponse.content if b.type == "text").strip()
    u = reponse.usage
    print(f"ИИ-анализ готов ({u.input_tokens} токенов на входе, {u.output_tokens} на выходе).")
    return texte or None
