"""Находит твой TELEGRAM_CHAT_ID.

1. Отправь любое сообщение своему боту в Telegram (например, «привет»).
2. Запусти:  TELEGRAM_BOT_TOKEN=твой_токен python telegram_chat_id.py
"""

import os
import sys

import requests

jeton = os.environ.get("TELEGRAM_BOT_TOKEN")
if not jeton:
    sys.exit("Сначала задай переменную TELEGRAM_BOT_TOKEN.")

r = requests.get(f"https://api.telegram.org/bot{jeton}/getUpdates", timeout=30)
if not r.ok:
    sys.exit(f"Telegram отклонил запрос ({r.status_code}). Проверь токен.")

chats = {}
for maj in r.json().get("result", []):
    msg = maj.get("message") or maj.get("channel_post") or {}
    chat = msg.get("chat") or {}
    if "id" in chat:
        chats[chat["id"]] = chat.get("title") or chat.get("first_name") or chat.get("username") or ""

if not chats:
    sys.exit("Сообщений не найдено. Сначала напиши своему боту, потом запусти снова.")
for cid, nom in chats.items():
    print(f"TELEGRAM_CHAT_ID = {cid}   ({nom})")
