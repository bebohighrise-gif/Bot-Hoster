import subprocess
import sys
import json

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

room_id = config["ROOM_ID"]
api_token = config["BOT_API_TOKEN"]

subprocess.run(
    [sys.executable, "-m", "highrise", f"main:BotHoster", room_id, api_token],
    check=True
)
