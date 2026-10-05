# Muestra el chat_id de quien le haya escrito al bot.
# Antes: abre tu bot en Telegram, pulsa "Iniciar" y mándale "hola".
import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_TOKEN")
url = f"https://api.telegram.org/bot{token}"

yo = requests.get(f"{url}/getMe", timeout=30).json()
if not yo.get("ok"):
    raise SystemExit(f"El token no es válido: {yo}")
print(f"Bot: @{yo['result']['username']}")

# Si el bot tuviera un webhook, getUpdates sale vacío; lo quitamos
requests.get(f"{url}/deleteWebhook", timeout=30)

datos = requests.get(f"{url}/getUpdates", timeout=30).json()
chats = {}
for u in datos.get("result", []):
    msg = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
    chat = msg.get("chat")
    if chat:
        chats[chat["id"]] = chat.get("title") or chat.get("first_name") or chat.get("username")

if not chats:
    print("No hay mensajes. Escríbele 'hola' al bot en Telegram y vuelve a ejecutar esto.")
for cid, nombre in chats.items():
    print(f"TELEGRAM_CHAT_ID={cid}   ({nombre})")
