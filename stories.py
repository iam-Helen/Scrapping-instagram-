"""Сторис и закрепы (highlights) аккаунтов из config.yaml через Apify.

Аккаунт Instagram не используется. Результат: sorties/stories/ —
JSON со всеми кадрами, превью-картинки и «листы» по каждому аккаунту.

    python stories.py            # нужен APIFY_TOKEN
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from veille import charger_config

ACTOR = "memo23/instagram-stories-highlights-scraper"
OUT = Path("sorties/stories")
THUMB_W = 240


def _slug(s: str) -> str:
    return re.sub(r"[^\w-]+", "_", s or "sans_titre", flags=re.UNICODE).strip("_")[:40] or "x"


def recuperer(comptes: list[str], token: str) -> list[dict]:
    from apify_client import ApifyClient

    client = ApifyClient(token)
    run = client.actor(ACTOR).call(
        run_input={
            "usernames": comptes,
            "dataToScrape": "both",
            "maxHighlightsPerUser": 15,
            "downloadMedia": False,
        },
        max_total_charge_usd=Decimal("1.0"),
    )
    statut = str(getattr(run.status, "value", run.status))
    if statut != "SUCCEEDED":
        raise RuntimeError(f"Apify: статус {statut}: {run.status_message}")
    return list(client.dataset(run.default_dataset_id).iterate_items())


def telecharger_vignettes(items: list[dict]) -> None:
    """Скачивает превью сразу: ссылки Instagram живут всего несколько часов."""
    groupes: dict[tuple[str, str], list[Image.Image]] = {}
    for it in items:
        url = it.get("imageUrl")
        if not url:
            continue
        user = it.get("sourceUsername") or "?"
        titre = it.get("highlightTitle") if it.get("type") == "highlight" else "СТОРИС_сейчас"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception as e:  # noqa: BLE001
            print(f"не скачано: {user} / {titre}: {e}")
            continue
        im.thumbnail((THUMB_W, THUMB_W * 2))
        groupes.setdefault((user, titre or "без_названия"), []).append(im)

    for (user, titre), ims in groupes.items():
        d = OUT / _slug(user)
        d.mkdir(parents=True, exist_ok=True)
        cols = min(6, len(ims))
        rows = (len(ims) + cols - 1) // cols
        h = max(i.height for i in ims)
        sheet = Image.new("RGB", (cols * THUMB_W, rows * h + 36), "white")
        ImageDraw.Draw(sheet).text((8, 10), f"@{user} — {titre} ({len(ims)})", fill="black")
        for k, im in enumerate(ims):
            sheet.paste(im, ((k % cols) * THUMB_W, 36 + (k // cols) * h))
        sheet.save(d / f"{_slug(titre)}.jpg", quality=80)


def main() -> int:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("Ошибка: переменная APIFY_TOKEN не задана.", file=sys.stderr)
        return 1
    cfg = charger_config("config.yaml")
    items = recuperer(cfg.comptes, token)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stories.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    telecharger_vignettes(items)
    trays = {(i.get("sourceUsername"), i.get("highlightTitle")) for i in items if i.get("type") == "highlight"}
    stories = sum(1 for i in items if i.get("type") == "story")
    print(f"Кадров: {len(items)} · закрепов: {len(trays)} · активных сторис: {stories}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
