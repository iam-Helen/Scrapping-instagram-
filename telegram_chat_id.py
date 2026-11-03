"""Trouve ton TELEGRAM_CHAT_ID.

1. Envoie n'importe quel message à ton bot sur Telegram (ex. « salut »).
2. Lance :  TELEGRAM_BOT_TOKEN=ton_jeton python telegram_chat_id.py
"""

import os
import sys

import requests

jeton = os.environ.get("TELEGRAM_BOT_TOKEN")
if not jeton:
    sys.exit("Définis d'abord la variable TELEGRAM_BOT_TOKEN.")

r = requests.get(f"https://api.telegram.org/bot{jeton}/getUpdates", timeout=30)
if not r.ok:
    sys.exit(f"Telegram a refusé la requête ({r.status_code}). Vérifie le jeton.")

chats = {}
for maj in r.json().get("result", []):
    msg = maj.get("message") or maj.get("channel_post") or {}
    chat = msg.get("chat") or {}
    if "id" in chat:
        chats[chat["id"]] = chat.get("title") or chat.get("first_name") or chat.get("username") or ""

if not chats:
    sys.exit("Aucun message trouvé. Envoie d'abord un message à ton bot, puis relance.")
for cid, nom in chats.items():
    print(f"TELEGRAM_CHAT_ID = {cid}   ({nom})")
