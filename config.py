import json
import os

CONFIG_FILE = "config.json"

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        ROOM_ID = data.get("ROOM_ID", "")
        HOSTER_OWNER_ID = data.get("HOSTER_OWNER_ID", "")
        BOT_API_TOKEN = data.get("BOT_API_TOKEN", "")
else:
    raise FileNotFoundError("❌ No se encontró el archivo config.json.")

# Rutas globales
DB_NAME = "bot_hoster.db"
TEMPLATES_DIR = "templates"
HOSTED_INSTANCES_DIR = "hosted_instances"

os.makedirs(HOSTED_INSTANCES_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
