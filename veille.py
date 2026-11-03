"""Мониторинг Instagram: собирает публикации ниши через Apify,
находит самые успешные и отправляет отчёт в Telegram.

Аккаунт Instagram не используется: публичные данные собирает Apify
на своей инфраструктуре.

Использование:
    python veille.py                     # обычный запуск (Apify + Telegram)
    python veille.py --dry-run           # показать отчёт вместо отправки
    python veille.py --fichier data.json # анализ локальных данных (бесплатно)

Переменные окружения:
    APIFY_TOKEN         API-ключ Apify
    TELEGRAM_BOT_TOKEN  токен бота (выдаёт @BotFather)
    TELEGRAM_CHAT_ID    номер чата (см. telegram_chat_id.py)
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests
import yaml

ACTOR_ID = "apify/instagram-scraper"
PRIX_PAR_RESULTAT_USD = 0.0027  # tarif du plan gratuit Apify (nov. 2026)
SEUIL_SURPERFORMANCE = 1.5  # x fois la médiane du compte
LIMITE_MESSAGE_TELEGRAM = 4000  # Telegram coupe à 4096 caractères

FORMATS = {"Video": "Reels", "Sidecar": "Карусель", "Image": "Фото"}

_RESERVES = {"p", "reel", "reels", "explore", "stories", "tv"}


# ─── Configuration ────────────────────────────────────────────────────────────


@dataclass
class Config:
    comptes: list[str]
    hashtags: list[str]
    jours: int = 7
    posts_par_source: int = 12
    top_n: int = 8
    budget_max_usd: float = 1.0


def normaliser_compte(valeur: str) -> str:
    """Transforme '@nom', 'nom' ou un lien de profil en nom d'utilisateur."""
    v = valeur.strip()
    m = re.match(r"^(?:https?://)?(?:www\.)?instagram\.com/([^/?#]+)", v)
    if m:
        nom = m.group(1)
        if nom.lower() in _RESERVES:
            raise ValueError(
                f"«{valeur}» — это ссылка на публикацию, а не на профиль. "
                "Укажи вместо неё имя аккаунта, который её опубликовал."
            )
        return nom.lower()
    nom = v.lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", nom):
        raise ValueError(f"Неверное имя аккаунта: «{valeur}»")
    return nom.lower()


def charger_config(chemin: str | Path) -> Config:
    brut = yaml.safe_load(Path(chemin).read_text(encoding="utf-8")) or {}
    comptes = [normaliser_compte(str(c)) for c in (brut.get("comptes") or [])]
    hashtags = [str(h).strip().lstrip("#").lower() for h in (brut.get("hashtags") or [])]
    cfg = Config(
        comptes=list(dict.fromkeys(comptes)),
        hashtags=list(dict.fromkeys(h for h in hashtags if h)),
        jours=int(brut.get("jours", 7)),
        posts_par_source=int(brut.get("posts_par_source", 12)),
        top_n=int(brut.get("top_n", 8)),
        budget_max_usd=float(brut.get("budget_max_usd", 1.0)),
    )
    if not cfg.comptes and not cfg.hashtags:
        raise ValueError("config.yaml: добавь хотя бы один аккаунт или хештег.")
    return cfg


def urls_sources(cfg: Config) -> list[str]:
    return [f"https://www.instagram.com/{c}/" for c in cfg.comptes] + [
        f"https://www.instagram.com/explore/tags/{h}/" for h in cfg.hashtags
    ]


def estimation_cout(cfg: Config) -> float:
    nb_sources = len(cfg.comptes) + len(cfg.hashtags)
    return min(nb_sources * cfg.posts_par_source * PRIX_PAR_RESULTAT_USD, cfg.budget_max_usd)


# ─── Récupération via Apify ───────────────────────────────────────────────────


def recuperer_publications(cfg: Config, token: str) -> list[dict]:
    from apify_client import ApifyClient

    client = ApifyClient(token)
    run_input = {
        "resultsType": "posts",
        "directUrls": urls_sources(cfg),
        "resultsLimit": cfg.posts_par_source,
        "onlyPostsNewerThan": f"{cfg.jours} days",
        "addParentData": True,
    }
    run = client.actor(ACTOR_ID).call(
        run_input=run_input,
        max_total_charge_usd=Decimal(str(cfg.budget_max_usd)),
    )
    if run is None:
        raise RuntimeError("Apify не вернул ни одного запуска.")
    statut = str(getattr(run.status, "value", run.status))
    if statut != "SUCCEEDED":
        raise RuntimeError(
            f"Запуск Apify завершился ошибкой (статус {statut}): {run.status_message or 'без подробностей'}"
        )
    return list(client.dataset(run.default_dataset_id).iterate_items())


# ─── Analyse ──────────────────────────────────────────────────────────────────


@dataclass
class Publication:
    url: str
    compte: str
    format: str
    legende: str
    likes: int
    commentaires: int
    vues: int | None
    date: datetime | None
    hashtags: list[str]
    ratio: float | None = None  # performance vs médiane du compte

    @property
    def interactions(self) -> int:
        return self.likes + self.commentaires


def _entier(v) -> int:
    try:
        return max(int(v), 0)  # Instagram renvoie -1 quand les likes sont masqués
    except (TypeError, ValueError):
        return 0


def _date(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def convertir(items: list[dict]) -> list[Publication]:
    pubs: dict[str, Publication] = {}
    for it in items:
        if it.get("error") or not it.get("url"):
            continue
        type_ = it.get("type") or ""
        fmt = "Reels" if it.get("productType") == "clips" else FORMATS.get(type_, type_ or "?")
        vues = it.get("videoPlayCount") or it.get("videoViewCount")
        pubs[it["url"]] = Publication(
            url=it["url"],
            compte=(it.get("ownerUsername") or "?").lower(),
            format=fmt,
            legende=(it.get("caption") or "").strip(),
            likes=_entier(it.get("likesCount")),
            commentaires=_entier(it.get("commentsCount")),
            vues=_entier(vues) if vues else None,
            date=_date(it.get("timestamp")),
            hashtags=[h.lower() for h in (it.get("hashtags") or [])],
        )
    return list(pubs.values())


def calculer_ratios(pubs: list[Publication]) -> None:
    """Compare chaque publication à la médiane de son propre compte.
    Un ratio de 3 = trois fois plus d'interactions que d'habitude."""
    par_compte: dict[str, list[Publication]] = defaultdict(list)
    for p in pubs:
        par_compte[p.compte].append(p)
    for liste in par_compte.values():
        if len(liste) < 3:
            continue
        mediane = statistics.median(p.interactions for p in liste)
        if mediane <= 0:
            continue
        for p in liste:
            p.ratio = p.interactions / mediane


@dataclass
class Analyse:
    total: int
    nb_comptes: int
    surperformances: list[Publication]
    top: list[Publication]
    formats: list[tuple[str, int, float]]  # (format, nombre, interactions moyennes)
    hashtags_gagnants: list[tuple[str, int]]


def analyser(pubs: list[Publication], top_n: int) -> Analyse:
    calculer_ratios(pubs)
    surperf = sorted(
        (p for p in pubs if p.ratio is not None and p.ratio >= SEUIL_SURPERFORMANCE),
        key=lambda p: p.ratio,
        reverse=True,
    )[:top_n]
    deja = {p.url for p in surperf}
    top = [p for p in sorted(pubs, key=lambda p: p.interactions, reverse=True) if p.url not in deja][
        :top_n
    ]

    par_format: dict[str, list[int]] = defaultdict(list)
    for p in pubs:
        par_format[p.format].append(p.interactions)
    formats = sorted(
        ((f, len(v), statistics.mean(v)) for f, v in par_format.items()),
        key=lambda t: t[2],
        reverse=True,
    )

    meilleurs = sorted(pubs, key=lambda p: p.interactions, reverse=True)[: max(top_n * 2, 10)]
    tags = Counter(h for p in meilleurs for h in set(p.hashtags))

    return Analyse(
        total=len(pubs),
        nb_comptes=len({p.compte for p in pubs}),
        surperformances=surperf,
        top=top,
        formats=formats,
        hashtags_gagnants=tags.most_common(8),
    )


# ─── Rapport Telegram ─────────────────────────────────────────────────────────


def _nombre(n: int | float) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(n)


def _accroche(legende: str, longueur: int = 140) -> str:
    premiere = legende.split("\n", 1)[0].strip() or legende.strip()
    if len(premiere) > longueur:
        premiere = premiere[: longueur - 1].rstrip() + "…"
    return html.escape(premiere, quote=False) if premiere else "<i>(без подписи)</i>"


def _bloc(p: Publication, rang: int) -> str:
    stats = f"❤️ {_nombre(p.likes)} · 💬 {_nombre(p.commentaires)}"
    if p.vues:
        stats += f" · ▶️ {_nombre(p.vues)}"
    if p.ratio and p.ratio >= SEUIL_SURPERFORMANCE:
        stats += f" · <b>x{p.ratio:.1f}</b> от обычного"
    date = f" · {p.date:%d.%m}" if p.date else ""
    return (
        f"{rang}. <b>@{html.escape(p.compte)}</b> · {p.format}{date}\n"
        f"   {stats}\n"
        f"   « {_accroche(p.legende)} »\n"
        f"   <a href=\"{html.escape(p.url, quote=True)}\">Открыть публикацию</a>"
    )


def construire_rapport(a: Analyse, cfg: Config) -> list[str]:
    """Renvoie le rapport découpé en messages de moins de 4000 caractères."""
    sections: list[str] = [
        f"📊 <b>Мониторинг Instagram</b> — {datetime.now(timezone.utc):%d.%m.%Y}\n"
        f"Публикаций: {a.total} · аккаунтов: {a.nb_comptes} · за последние {cfg.jours} дн."
    ]
    if a.total == 0:
        sections.append("За этот период новых публикаций нет.")
        return sections

    if a.surperformances:
        sections.append(
            "🔥 <b>Публикации, которые «выстреливают»</b>\n<i>Намного лучше обычных результатов аккаунта</i>"
        )
        sections += [_bloc(p, i) for i, p in enumerate(a.surperformances, 1)]

    if a.top:
        sections.append("🏆 <b>Больше всего реакций</b>")
        sections += [_bloc(p, i) for i, p in enumerate(a.top, 1)]

    if a.formats:
        lignes = [
            f"• {html.escape(f)}: в среднем {_nombre(moy)} реакций (публикаций: {n})"
            for f, n, moy in a.formats
        ]
        sections.append("🎬 <b>Форматы</b>\n" + "\n".join(lignes))

    if a.hashtags_gagnants:
        tags = " ".join(f"#{html.escape(t)}" for t, _ in a.hashtags_gagnants)
        sections.append("🏷️ <b>Хештеги лучших публикаций</b>\n" + tags)

    messages, courant = [], ""
    for s in sections:
        if courant and len(courant) + len(s) + 2 > LIMITE_MESSAGE_TELEGRAM:
            messages.append(courant)
            courant = s
        else:
            courant = f"{courant}\n\n{s}" if courant else s
    if courant:
        messages.append(courant)
    return messages


def envoyer_telegram(messages: list[str], bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for m in messages:
        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": m,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        if not r.ok:
            # On n'affiche pas l'URL : elle contient le jeton du bot.
            raise RuntimeError(f"Telegram отклонил сообщение ({r.status_code}): {r.text[:300]}")


# ─── Sauvegarde ───────────────────────────────────────────────────────────────


def sauvegarder(items: list[dict], pubs: list[Publication], dossier: Path) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    (dossier / f"brut_{horodatage}.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    with open(dossier / f"publications_{horodatage}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["аккаунт", "формат", "дата", "лайки", "комментарии", "просмотры", "x от обычного", "ссылка", "подпись"])
        for p in sorted(pubs, key=lambda p: p.interactions, reverse=True):
            w.writerow([
                p.compte, p.format, p.date.isoformat() if p.date else "", p.likes,
                p.commentaires, p.vues or "", f"{p.ratio:.2f}" if p.ratio else "", p.url, p.legende,
            ])


# ─── Point d'entrée ───────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="показать отчёт, не отправляя его")
    ap.add_argument("--fichier", help="JSON-файл с результатами Apify для анализа (без запроса к Apify)")
    ap.add_argument("--sorties", default="sorties", help="папка для выгрузок JSON/CSV")
    args = ap.parse_args(argv)

    cfg = charger_config(args.config)

    if args.fichier:
        items = json.loads(Path(args.fichier).read_text(encoding="utf-8"))
    else:
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            print("Ошибка: переменная APIFY_TOKEN не задана.", file=sys.stderr)
            return 1
        print(
            f"Источники: аккаунтов {len(cfg.comptes)}, хештегов {len(cfg.hashtags)}. "
            f"Максимальная оценка стоимости: {estimation_cout(cfg):.2f} $ (лимит {cfg.budget_max_usd:.2f} $)."
        )
        items = recuperer_publications(cfg, token)
        print(f"Получено результатов от Apify: {len(items)}.")

    pubs = convertir(items)
    sauvegarder(items, pubs, Path(args.sorties))
    messages = construire_rapport(analyser(pubs, cfg.top_n), cfg)

    if args.dry_run:
        print("\n\n──────── следующее сообщение ────────\n\n".join(messages))
        return 0

    bot, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not bot or not chat:
        print("Ошибка: нужно задать TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.", file=sys.stderr)
        return 1
    envoyer_telegram(messages, bot, chat)
    print(f"Отчёт отправлен в Telegram (сообщений: {len(messages)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
