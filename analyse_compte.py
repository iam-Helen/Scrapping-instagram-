"""Разовый разбор одного аккаунта: что у него залетело сильнее всего.

    python analyse_compte.py <имя_аккаунта> [кол-во_публикаций]

Результат в sorties/compte/: JSON, CSV (по убыванию реакций) и листы
с обложками самых успешных публикаций. Нужен APIFY_TOKEN.
"""

from __future__ import annotations

import io
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from veille import ACTOR_ID, calculer_ratios, convertir, normaliser_compte, sauvegarder

OUT = Path("sorties/compte")
TOP = 24
TW = 300


def recuperer(compte: str, limite: int, token: str) -> list[dict]:
    from apify_client import ApifyClient

    client = ApifyClient(token)
    run = client.actor(ACTOR_ID).call(
        run_input={
            "resultsType": "posts",
            "directUrls": [
                c.split("?")[0] if c.startswith("http") and ("/p/" in c or "/reel/" in c)
                else f"https://www.instagram.com/explore/tags/{c.lstrip('#')}/" if c.startswith("#")
                else f"https://www.instagram.com/{normaliser_compte(c)}/"
                for c in compte.split(",") if c.strip()
            ],
            "resultsLimit": limite,
        },
        max_total_charge_usd=Decimal("0.5"),
    )
    statut = str(getattr(run.status, "value", run.status))
    if statut != "SUCCEEDED":
        raise RuntimeError(f"Apify: статус {statut}: {run.status_message}")
    return list(client.dataset(run.default_dataset_id).iterate_items())


def planches(items: list[dict]) -> None:
    """Обложки топ-публикаций: ссылки Instagram живут несколько часов, качаем сразу."""
    par_url = {it.get("url"): it for it in items}
    pubs = sorted(convertir(items), key=lambda p: p.interactions, reverse=True)[:TOP]
    tuiles = []
    for rang, p in enumerate(pubs, 1):
        it = par_url.get(p.url, {})
        url = it.get("displayUrl") or (it.get("images") or [None])[0]
        if not url:
            continue
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception as e:  # noqa: BLE001
            print(f"обложка не скачана: {p.url}: {e}")
            continue
        im.thumbnail((TW, int(TW * 1.8)))
        tuile = Image.new("RGB", (TW, im.height + 54), "white")
        tuile.paste(im, (0, 54))
        d = ImageDraw.Draw(tuile)
        vues = f" views {p.vues}" if p.vues else ""
        d.text((6, 4), f"#{rang} {p.format}", fill="black")
        d.text((6, 20), f"likes {p.likes} com {p.commentaires}{vues}", fill="black")
        d.text((6, 36), p.url.rstrip('/').split('/')[-1], fill="gray")
        tuiles.append(tuile)
    for k in range(0, len(tuiles), 6):
        lot = tuiles[k:k + 6]
        h = max(t.height for t in lot)
        sheet = Image.new("RGB", (TW * len(lot), h), "white")
        for i, t in enumerate(lot):
            sheet.paste(t, (i * TW, 0))
        sheet.save(OUT / f"top_{k // 6 + 1}.jpg", quality=85)


def derniers_complets(items: list[dict], n: int = 6) -> None:
    """Все слайды n последних публикаций: чтобы разобрать их целиком."""
    recents = sorted(items, key=lambda i: i.get("timestamp") or "", reverse=True)[:n]
    for k, it in enumerate(recents, 1):
        urls = [c.get("displayUrl") for c in (it.get("childPosts") or []) if c.get("displayUrl")]
        if not urls:
            urls = [it.get("displayUrl")] if it.get("displayUrl") else []
        ims = []
        for u in urls[:10]:
            try:
                r = requests.get(u, timeout=30)
                r.raise_for_status()
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                im.thumbnail((360, 640))
                ims.append(im)
            except Exception as e:  # noqa: BLE001
                print(f"слайд не скачан: {e}")
        if not ims:
            continue
        cols = min(5, len(ims))
        rows = (len(ims) + cols - 1) // cols
        h = max(i.height for i in ims)
        sheet = Image.new("RGB", (cols * 360, rows * h), "white")
        for j, im in enumerate(ims):
            sheet.paste(im, ((j % cols) * 360, (j // cols) * h))
        date = (it.get("timestamp") or "")[:10]
        sheet.save(OUT / f"recent_{k}_{date}.jpg", quality=85)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("Ошибка: переменная APIFY_TOKEN не задана.", file=sys.stderr)
        return 1
    compte = ",".join(c.strip() for c in sys.argv[1].split(",") if c.strip())
    limite = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    items = recuperer(compte, limite, token)
    OUT.mkdir(parents=True, exist_ok=True)
    pubs = convertir(items)
    calculer_ratios(pubs)
    sauvegarder(items, pubs, OUT)
    planches(items)
    derniers_complets(items)
    print(f"{compte}: публикаций {len(pubs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
