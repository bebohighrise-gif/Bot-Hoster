import asyncio
import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Union

from highrise import BaseBot, User, Reaction, AnchorPosition
from highrise.models import SessionMetadata, CurrencyItem, Item, Error, Position, GetMessagesRequest

# ============================================================================
# CONFIGURACIÓN Y CONSTANTES
# ============================================================================

def load_config():
    """Carga la configuración desde config.json"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return {}

config = load_config()
ADMIN_IDS = config.get("admin_ids", [])
OWNER_ID = config.get("owner_id", "")
MODERATOR_IDS = config.get("moderator_ids", [])
VIP_ZONE = config.get("vip_zone", {"x": 0, "y": 0, "z": 0})
DJ_ZONE = config.get("dj_zone", {"x": 0, "y": 0, "z": 0})
DIRECTIVO_ZONE = config.get("directivo_zone", {"x": 0, "y": 0, "z": 0})
FORBIDDEN_ZONES = config.get("forbidden_zones", [])
BOT_WALLET = config.get("bot_wallet", 0)
BOT_ID = config.get("bot_id", "")

# Variables globales
VIP_USERS = set()
BANNED_USERS = {}
MUTED_USERS = {}
USER_HEARTS = {}
USER_ACTIVITY = {}
USER_INFO = {}
USER_NAMES = {}
TELEPORT_POINTS = {}
IS_ANCHORED = False
ANCHOR_POSITION = None
ACTIVE_EMOTES = {}
USER_JOIN_TIMES = {}
SAVED_OUTFITS = {}
JAIL_USERS = set()  # Usuarios que fueron enviados a la cárcel por admin/owner
FOLLOW_TARGET = None  # Usuario que el bot está siguiendo
SUBSCRIBERS = set()  # Usuarios suscritos para recibir invitaciones
SUBSCRIBER_HISTORY = set() # Usuarios que alguna vez se suscribieron
ACTIVE_CONVERSATIONS = {}  # {user_id: conversation_id}

ALTURAS_PROHIBIDAS = {}

# Constantes de reintentos
MAX_RETRIES = 3
RETRY_DELAY = 5

# ============================================================================
# SISTEMA DE LOGGING
# ============================================================================

def log_event(event_type: str, message: str):
    """Sistema de logging de eventos"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{event_type}] {message}\n"

        with open("bot_log.txt", "a", encoding="utf-8") as f:
            f.write(log_message)

        if event_type in ["ERROR", "WARNING", "ADMIN", "MOD"]:
            print(log_message.strip())
    except Exception as e:
        print(f"Error logging event: {e}")

def log_bot_response(message: str):
    """Registra las respuestas del bot para el panel web"""
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        with open("bot_responses.txt", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
        
        # Mantener solo las últimas 100 líneas
        try:
            with open("bot_responses.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > 100:
                with open("bot_responses.txt", "w", encoding="utf-8") as f:
                    f.writelines(lines[-100:])
        except:
            pass
    except Exception as e:
        print(f"Error logging bot response: {e}")

def safe_print(message: str):
    """Imprime mensaje de forma segura en Windows, manejando errores de encoding"""
    try:
        print(message)
    except UnicodeEncodeError:
        # Si falla con emojis, imprimir sin ellos
        try:
            print(message.encode('ascii', 'ignore').decode('ascii'))
        except:
            # Si todo falla, usar repr
            print(repr(message))

# ============================================================================
# SISTEMA DE PERSISTENCIA DE DATOS
# ============================================================================

def save_user_info():
    """Guarda información de usuarios"""
    try:
        os.makedirs("data", exist_ok=True)
        serializable_data = {}
        for user_id, data in USER_INFO.items():
            serializable_data[user_id] = {}
            for key, value in data.items():
                if isinstance(value, datetime):
                    serializable_data[user_id][key] = value.isoformat()
                else:
                    serializable_data[user_id][key] = value

        with open("data/user_info.json", "w", encoding="utf-8") as f:
            json.dump(serializable_data, f, indent=2, ensure_ascii=False)
        print(f"Información de usuarios guardada: {len(USER_INFO)} usuarios")
    except Exception as e:
        print(f"Error guardando información de usuarios: {e}")

def save_leaderboard_data():
    """Guarda datos del leaderboard"""
    try:
        os.makedirs("data", exist_ok=True)

        # Guardar corazones
        with open("data/hearts.txt", "w", encoding="utf-8") as f:
            f.write("# Corazones de usuarios (user_id:hearts:username)\n")
            for user_id, hearts in USER_HEARTS.items():
                username = USER_NAMES.get(user_id, f"User_{user_id[:8]}")
                f.write(f"{user_id}:{hearts}:{username}\n")

        # Guardar actividad
        with open("data/activity.txt", "w", encoding="utf-8") as f:
            f.write("# Actividad de usuarios (user_id:messages:last_activity:username)\n")
            for user_id, data in USER_ACTIVITY.items():
                username = USER_NAMES.get(user_id, f"User_{user_id[:8]}")
                last_activity = data["last_activity"].isoformat() if isinstance(data["last_activity"], datetime) else str(data["last_activity"])
                f.write(f"{user_id}:{data['messages']}:{last_activity}:{username}\n")

        print(f"Datos del leaderboard guardados: {len(USER_HEARTS)} corazones, {len(USER_ACTIVITY)} actividad")
    except Exception as e:
        print(f"Error guardando datos del leaderboard: {e}")

def load_subscribers():
    """Carga la lista de suscriptores"""
    global SUBSCRIBERS, SUBSCRIBER_HISTORY
    try:
        if os.path.exists("data/subscribers.json"):
            with open("data/subscribers.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                SUBSCRIBERS = set(data)
            print(f"Suscriptores cargados: {len(SUBSCRIBERS)}")
        
        if os.path.exists("data/subscriber_history.json"):
            with open("data/subscriber_history.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                SUBSCRIBER_HISTORY = set(data)
            print(f"Historial de suscriptores cargado: {len(SUBSCRIBER_HISTORY)}")
    except Exception as e:
        print(f"Error cargando suscriptores: {e}")

def save_subscribers():
    """Guarda la lista de suscriptores"""
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/subscribers.json", "w", encoding="utf-8") as f:
            json.dump(list(SUBSCRIBERS), f)
        with open("data/subscriber_history.json", "w", encoding="utf-8") as f:
            json.dump(list(SUBSCRIBER_HISTORY), f)
    except Exception as e:
        print(f"Error guardando suscriptores: {e}")

def load_user_conversations():
    """Carga las conversaciones de usuarios desde user_conversations.json"""
    global ACTIVE_CONVERSATIONS
    try:
        if os.path.exists("data/user_conversations.json"):
            with open("data/user_conversations.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    ACTIVE_CONVERSATIONS = data
                    print(f"Conversaciones cargadas: {len(ACTIVE_CONVERSATIONS)}")
    except Exception as e:
        print(f"Error cargando conversaciones: {e}")

def save_user_conversations():
    """Guarda las conversaciones de usuarios en user_conversations.json"""
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/user_conversations.json", "w", encoding="utf-8") as f:
            json.dump(ACTIVE_CONVERSATIONS, f, indent=2)
    except Exception as e:
        print(f"Error guardando conversaciones: {e}")

async def save_bot_inventory(bot_instance):
    """Guarda el inventario del bot"""
    try:
        # Verificar si la conexión está activa
        if not bot_instance.highrise:
            return
            
        inventory_response = await bot_instance.highrise.get_inventory()
        if not isinstance(inventory_response, Error):
            inventory = inventory_response.items
            inventory_data = [
                {
                    "type": item.type,
                    "id": item.id,
                    "amount": item.amount
                }
                for item in inventory
            ]

            os.makedirs("data", exist_ok=True)
            with open("data/bot_inventory.json", "w", encoding="utf-8") as f:
                json.dump(inventory_data, f, indent=2, ensure_ascii=False)

            safe_print(f"✅ Inventario del bot guardado: {len(inventory_data)} items")
    except Exception as e:
        # No imprimir el error si es un problema de transporte cerrado, ya que el bot se reiniciará
        if "closing transport" not in str(e).lower():
            safe_print(f"❌ Error guardando inventario del bot: {e}")

# ============================================================================
# CATÁLOGO DE EMOTES
# ============================================================================

# Emotes deshabilitados (no gratuitos)
DISABLED_EMOTE_IDS = {
}

emotes = {
    "1": {"id": "emote-looping", "name": "fairytwirl", "duration": 9.89, "is_free": True},
    "2": {"id": "idle-floating", "name": "fairyfloat", "duration": 27.60, "is_free": True},
    "3": {"id": "emote-launch", "name": "launch", "duration": 10.88, "is_free": True},
    "4": {"id": "emote-cutesalute", "name": "cutesalute", "duration": 4.29, "is_free": True},
    "5": {"id": "emote-salute", "name": "atattention", "duration": 4.79, "is_free": True},
    "6": {"id": "dance-tiktok11", "name": "tiktok", "duration": 11.37, "is_free": True},
    "7": {"id": "emote-kissing", "name": "smooch", "duration": 7.59, "is_free": True},
    "8": {"id": "dance-employee", "name": "pushit", "duration": 8.55, "is_free": True},
    "9": {"id": "emote-gift", "name": "foryou", "duration": 6.09, "is_free": True},
    "10": {"id": "dance-touch", "name": "touch", "duration": 13.15, "is_free": True},
    "11": {"id": "dance-kawai", "name": "kawaii", "duration": 10.85, "is_free": True},
    "12": {"id": "sit-relaxed", "name": "repose", "duration": 31.21, "is_free": True},
    "13": {"id": "emote-sleigh", "name": "sleigh", "duration": 12.51, "is_free": True},
    "14": {"id": "emote-hyped", "name": "hyped", "duration": 7.62, "is_free": True},
    "15": {"id": "dance-jinglebell", "name": "jingle", "duration": 12.09, "is_free": True},
    "16": {"id": "idle-toilet", "name": "gottago", "duration": 33.48, "is_free": True},
    "17": {"id": "emote-timejump", "name": "timejump", "duration": 5.51, "is_free": True},
    "18": {"id": "idle-wild", "name": "scritchy", "duration": 27.35, "is_free": True},
    "19": {"id": "idle-nervous", "name": "bitnervous", "duration": 22.81, "is_free": True},
    "20": {"id": "emote-iceskating", "name": "iceskating", "duration": 8.41, "is_free": True},
    "21": {"id": "emote-celebrate", "name": "partytime", "duration": 4.35, "is_free": True},
    "22": {"id": "emote-pose10", "name": "arabesque", "duration": 5.00, "is_free": True},
    "23": {"id": "emote-shy2", "name": "bashful", "duration": 6.34, "is_free": True},
    "24": {"id": "emote-headblowup", "name": "revelations", "duration": 13.66, "is_free": True},
    "25": {"id": "emote-creepycute", "name": "watchyourback", "duration": 9.01, "is_free": True},
    "26": {"id": "dance-creepypuppet", "name": "creepypuppet", "duration": 7.79, "is_free": True},
    "27": {"id": "dance-anime", "name": "saunter", "duration": 9.60, "is_free": True},
    "28": {"id": "emote-pose6", "name": "surprise", "duration": 6.46, "is_free": True},
    "29": {"id": "emote-celebrationstep", "name": "celebration", "duration": 5.18, "is_free": True},
    "30": {"id": "dance-pinguin", "name": "penguin", "duration": 12.81, "is_free": True},
    "31": {"id": "emote-boxer", "name": "boxer", "duration": 6.75, "is_free": True},
    "32": {"id": "idle-guitar", "name": "airguitar", "duration": 14.15, "is_free": True},
    "33": {"id": "emote-stargazer", "name": "stargaze", "duration": 7.93, "is_free": True},
    "34": {"id": "emote-pose9", "name": "ditzy", "duration": 6.00, "is_free": True},
    "35": {"id": "idle-uwu", "name": "uwu", "duration": 25.50, "is_free": True},
    "36": {"id": "dance-wrong", "name": "wrong", "duration": 13.60, "is_free": True},
    "37": {"id": "emote-fashionista", "name": "fashion", "duration": 6.33, "is_free": True},
    "38": {"id": "dance-icecream", "name": "icecream", "duration": 16.58, "is_free": True},
    "39": {"id": "idle-dance-tiktok4", "name": "sayso", "duration": 16.55, "is_free": True},
    "40": {"id": "idle_zombie", "name": "zombie", "duration": 31.39, "is_free": True},
    "41": {"id": "emote-astronaut", "name": "astronaut", "duration": 13.93, "is_free": True},
    "42": {"id": "emote-punkguitar", "name": "punk", "duration": 10.59, "is_free": True},
    "43": {"id": "emote-gravity", "name": "zerogravity", "duration": 9.02, "is_free": True},
    "44": {"id": "emote-pose5", "name": "beautiful", "duration": 5.49, "is_free": True},
    "46": {"id": "idle-dance-casual", "name": "casual", "duration": 9.57, "is_free": True},
    "47": {"id": "emote-pose1", "name": "wink", "duration": 4.71, "is_free": True},
    "48": {"id": "emote-pose3", "name": "fightme", "duration": 5.57, "is_free": True},
    "50": {"id": "emote-cute", "name": "cute", "duration": 7.20, "is_free": True},
    "51": {"id": "emote-cutey", "name": "cutey", "duration": 4.07, "is_free": True},
    "52": {"id": "emote-greedy", "name": "greedy", "duration": 5.72, "is_free": True},
    "53": {"id": "dance-tiktok9", "name": "viralgroove", "duration": 13.04, "is_free": True},
    "54": {"id": "dance-weird", "name": "weird", "duration": 22.87, "is_free": True},
    "55": {"id": "dance-tiktok10", "name": "shuffle", "duration": 9.41, "is_free": True},
    "56": {"id": "emoji-gagging", "name": "gagging", "duration": 6.84, "is_free": True},
    "57": {"id": "emoji-celebrate", "name": "raise", "duration": 4.78, "is_free": True},
    "58": {"id": "dance-tiktok8", "name": "savage", "duration": 13.10, "is_free": True},
    "59": {"id": "dance-blackpink", "name": "blackpink", "duration": 7.97, "is_free": True},
    "60": {"id": "emote-model", "name": "model", "duration": 7.43, "is_free": True},
    "61": {"id": "dance-tiktok2", "name": "dontstartnow", "duration": 11.37, "is_free": True},
    "62": {"id": "dance-pennywise", "name": "pennywise", "duration": 4.16, "is_free": True},
    "63": {"id": "emote-bow", "name": "bow", "duration": 5.10, "is_free": True},
    "64": {"id": "dance-russian", "name": "russian", "duration": 11.39, "is_free": True},
    "65": {"id": "emote-curtsy", "name": "curtsy", "duration": 3.99, "is_free": True},
    "66": {"id": "emote-snowball", "name": "snowball", "duration": 6.32, "is_free": True},
    "67": {"id": "emote-hot", "name": "hot", "duration": 5.57, "is_free": True},
    "68": {"id": "emote-snowangel", "name": "snowangel", "duration": 7.33, "is_free": True},
    "69": {"id": "emote-charging", "name": "charging", "duration": 9.53, "is_free": True},
    "70": {"id": "dance-shoppingcart", "name": "letsgoshopping", "duration": 5.56, "is_free": True},
    "71": {"id": "emote-confused", "name": "confused", "duration": 9.58, "is_free": True},
    "72": {"id": "idle-enthusiastic", "name": "enthused", "duration": 17.53, "is_free": True},
    "73": {"id": "emote-telekinesis", "name": "telekinesis", "duration": 11.01, "is_free": True},
    "74": {"id": "emote-float", "name": "float", "duration": 9.26, "is_free": True},
    "75": {"id": "emote-teleporting", "name": "teleporting", "duration": 12.89, "is_free": True},
    "76": {"id": "emote-swordfight", "name": "swordfight", "duration": 7.71, "is_free": True},
    "77": {"id": "emote-maniac", "name": "maniac", "duration": 5.94, "is_free": True},
    "78": {"id": "emote-energyball", "name": "energyball", "duration": 8.28, "is_free": True},
    "79": {"id": "emote-snake", "name": "worm", "duration": 6.63, "is_free": True},
    "80": {"id": "idle_singing", "name": "singalong", "duration": 11.31, "is_free": True},
    "81": {"id": "emote-frog", "name": "frog", "duration": 16.14, "is_free": True},
    "82": {"id": "dance-macarena", "name": "macarena", "duration": 15.0, "is_free": True},
    "83": {"id": "emote-kissing-passionate", "name": "kiss", "duration": 9.5, "is_free": True},
    "84": {"id": "emoji-shake-head", "name": "shakehead", "duration": 3.5, "is_free": True},
    "85": {"id": "idle-sad", "name": "sad", "duration": 25.24, "is_free": True},
    "86": {"id": "emoji-nod", "name": "nod", "duration": 2.5, "is_free": True},
    "87": {"id": "emote-laughing2", "name": "laughing", "duration": 6.60, "is_free": True},
    "88": {"id": "emoji-hello", "name": "hello", "duration": 3.0, "is_free": True},
    "89": {"id": "emoji-thumbsup", "name": "thumbsup", "duration": 2.5, "is_free": True},
    "90": {"id": "mining-fail", "name": "miningfail", "duration": 3.41, "is_free": True},
    "91": {"id": "emote-shy", "name": "shy", "duration": 5.15, "is_free": True},
    "92": {"id": "fishing-pull", "name": "fishingpull", "duration": 2.81, "is_free": True},
    "93": {"id": "dance-thewave", "name": "thewave", "duration": 8.0, "is_free": True},
    "94": {"id": "idle-angry", "name": "angry", "duration": 26.07, "is_free": True},
    "95": {"id": "emote-rough", "name": "rough", "duration": 6.0, "is_free": True},
    "96": {"id": "fishing-idle", "name": "fishingidle", "duration": 17.87, "is_free": True},
    "97": {"id": "emote-dropped", "name": "dropped", "duration": 4.5, "is_free": True},
    "98": {"id": "mining-success", "name": "miningsuccess", "duration": 3.11, "is_free": True},
    "99": {"id": "emote-receive-happy", "name": "receivehappy", "duration": 5.0, "is_free": True},
    "100": {"id": "emote-cold", "name": "cold", "duration": 5.17, "is_free": True},
    "101": {"id": "fishing-cast", "name": "fishingcast", "duration": 2.82, "is_free": True},
    "102": {"id": "emote-sit", "name": "sit", "duration": 20.0, "is_free": True},
    "103": {"id": "dance-shuffle", "name": "shuffledance", "duration": 9.0, "is_free": True},
    "104": {"id": "emote-receive-sad", "name": "receivesad", "duration": 5.0, "is_free": True},
    "105": {"id": "idle-loop-tired", "name": "tired", "duration": 11.23, "is_free": True},
    "106": {"id": "dance-hipshake", "name": "hipshake", "duration": 13.38, "is_free": True},
    "107": {"id": "dance-fruity", "name": "fruity", "duration": 18.25, "is_free": True},
    "108": {"id": "dance-cheerleader", "name": "cheerleader", "duration": 17.93, "is_free": True},
    "109": {"id": "dance-tiktok14", "name": "magnetic", "duration": 11.20, "is_free": True},
    "110": {"id": "emote-howl", "name": "nocturnal", "duration": 8.10, "is_free": True},
    "111": {"id": "idle-howl", "name": "moonlit", "duration": 48.62, "is_free": True},
    "112": {"id": "emote-trampoline", "name": "trampoline", "duration": 6.11, "is_free": True},
    "113": {"id": "emote-attention", "name": "attention", "duration": 5.65, "is_free": True},
    "114": {"id": "sit-open", "name": "laidback", "duration": 27.28, "is_free": True},
    "115": {"id": "emote-shrink", "name": "shrink", "duration": 9.99, "is_free": True},
    "116": {"id": "emote-puppet", "name": "puppet", "duration": 17.89, "is_free": True},
    "117": {"id": "dance-aerobics", "name": "pushups", "duration": 9.89, "is_free": True},
    "118": {"id": "dance-duckwalk", "name": "duckwalk", "duration": 12.48, "is_free": True},
    "119": {"id": "dance-handsup", "name": "handsintheair", "duration": 23.18, "is_free": True},
    "120": {"id": "dance-metal", "name": "rockout", "duration": 15.78, "is_free": True},
    "121": {"id": "dance-orangejustice", "name": "orangejuice", "duration": 7.17, "is_free": True},
    "122": {"id": "dance-singleladies", "name": "ringonit", "duration": 22.33, "is_free": True},
    "123": {"id": "dance-smoothwalk", "name": "smoothwalk", "duration": 7.58, "is_free": True},
    "124": {"id": "dance-voguehands", "name": "voguehands", "duration": 10.57, "is_free": True},
    "125": {"id": "emoji-arrogance", "name": "arrogance", "duration": 8.16, "is_free": True},
    "126": {"id": "emoji-give-up", "name": "giveup", "duration": 6.04, "is_free": True},
    "127": {"id": "emoji-hadoken", "name": "fireball", "duration": 4.29, "is_free": True},
    "128": {"id": "emoji-halo", "name": "levitate", "duration": 6.52, "is_free": True},
    "129": {"id": "emoji-lying", "name": "lying", "duration": 7.39, "is_free": True},
    "130": {"id": "emoji-naughty", "name": "naughty", "duration": 5.73, "is_free": True},
    "131": {"id": "emoji-poop", "name": "stinky", "duration": 5.86, "is_free": True},
    "132": {"id": "emoji-pray", "name": "pray", "duration": 6.00, "is_free": True},
    "133": {"id": "emoji-punch", "name": "punch", "duration": 3.36, "is_free": True},
    "134": {"id": "emoji-sick", "name": "sick", "duration": 6.22, "is_free": True},
    "135": {"id": "emoji-smirking", "name": "smirk", "duration": 5.74, "is_free": True},
    "136": {"id": "emoji-sneeze", "name": "sneeze", "duration": 4.33, "is_free": True},
    "137": {"id": "emoji-there", "name": "point", "duration": 3.09, "is_free": True},
    "138": {"id": "emote-death2", "name": "collapse", "duration": 5.54, "is_free": True},
    "139": {"id": "emote-disco", "name": "disco", "duration": 6.14, "is_free": True},
    "140": {"id": "emote-ghost-idle", "name": "ghostfloat", "duration": 20.43, "is_free": True},
    "141": {"id": "emote-handstand", "name": "handstand", "duration": 5.89, "is_free": True},
    "142": {"id": "emote-kicking", "name": "superkick", "duration": 6.21, "is_free": True},
    "143": {"id": "emote-panic", "name": "panic", "duration": 4.5, "is_free": True},
    "144": {"id": "emote-splitsdrop", "name": "splits", "duration": 5.31, "is_free": True},
    "145": {"id": "idle_layingdown", "name": "attentive", "duration": 26.11, "is_free": True},
    "146": {"id": "idle_layingdown2", "name": "relaxed", "duration": 22.59, "is_free": True},
    "147": {"id": "emote-apart", "name": "fallingapart", "duration": 5.98, "is_free": True},
    "148": {"id": "emote-baseball", "name": "homerun", "duration": 8.47, "is_free": True},
    "149": {"id": "emote-boo", "name": "boo", "duration": 5.58, "is_free": True},
    "150": {"id": "emote-bunnyhop", "name": "bunnyhop", "duration": 13.63, "is_free": True},
    "151": {"id": "emote-death", "name": "revival", "duration": 8.00, "is_free": True},
    "152": {"id": "emote-deathdrop", "name": "faintdrop", "duration": 4.18, "is_free": True},
    "153": {"id": "emote-elbowbump", "name": "elbowbump", "duration": 6.44, "is_free": True},
    "154": {"id": "emote-fail1", "name": "fall", "duration": 6.90, "is_free": True},
    "155": {"id": "emote-fail2", "name": "clumsy", "duration": 7.74, "is_free": True},
    "156": {"id": "emote-fainting", "name": "faint", "duration": 18.55, "is_free": True},
    "157": {"id": "emote-hugyourself", "name": "hugyourself", "duration": 6.03, "is_free": True},
    "158": {"id": "emote-jetpack", "name": "jetpack", "duration": 17.77, "is_free": True},
    "159": {"id": "emote-judochop", "name": "judochop", "duration": 5.0, "is_free": True},
    "160": {"id": "emote-jumpb", "name": "jump", "duration": 4.87, "is_free": True},
    "161": {"id": "emote-laughing2", "name": "amused", "duration": 6.60, "is_free": True},
    "162": {"id": "emote-levelup", "name": "levelup", "duration": 7.27, "is_free": True},
    "163": {"id": "emote-monster_fail", "name": "monsterfail", "duration": 5.42, "is_free": True},
    "164": {"id": "idle-dance-headbobbing", "name": "nightfever", "duration": 23.65, "is_free": True},
    "165": {"id": "emote-ninjarun", "name": "ninjarun", "duration": 6.50, "is_free": True},
    "166": {"id": "emoji-peace", "name": "peace", "duration": 3.5, "is_free": True},
    "167": {"id": "emote-peekaboo", "name": "peekaboo", "duration": 4.52, "is_free": True},
    "168": {"id": "emote-proposing", "name": "proposing", "duration": 5.91, "is_free": True},
    "169": {"id": "emote-rainbow", "name": "rainbow", "duration": 8.0, "is_free": True},
    "170": {"id": "emote-robot", "name": "robot", "duration": 10.0, "is_free": True},
    "171": {"id": "emote-rofl", "name": "rofl", "duration": 7.65, "is_free": True},
    "172": {"id": "emote-roll", "name": "roll", "duration": 4.31, "is_free": True},
    "173": {"id": "emote-ropepull", "name": "ropepull", "duration": 10.69, "is_free": True},
    "174": {"id": "emote-secrethandshake", "name": "secrethandshake", "duration": 6.28, "is_free": True},
    "175": {"id": "emote-sumo", "name": "sumofight", "duration": 11.64, "is_free": True},
    "176": {"id": "emote-superpunch", "name": "superpunch", "duration": 5.75, "is_free": True},
    "177": {"id": "emote-superrun", "name": "superrun", "duration": 7.16, "is_free": True},
    "178": {"id": "emote-theatrical", "name": "theatrical", "duration": 11.00, "is_free": True},
    "179": {"id": "emote-wings", "name": "ibelieve", "duration": 14.21, "is_free": True},
    "180": {"id": "emote-frustrated", "name": "irritated", "duration": 6.41, "is_free": True},
    "181": {"id": "idle-floorsleeping", "name": "cozynap", "duration": 14.61, "is_free": True},
    "182": {"id": "idle-floorsleeping2", "name": "relaxing", "duration": 18.83, "is_free": True},
    "183": {"id": "idle-hero", "name": "heropose", "duration": 22.33, "is_free": True},
    "184": {"id": "idle-lookup", "name": "ponder", "duration": 8.75, "is_free": True},
    "185": {"id": "idle-posh", "name": "posh", "duration": 23.29, "is_free": True},
    "186": {"id": "idle-sad", "name": "poutyface", "duration": 25.24, "is_free": True},
    "187": {"id": "emote-dab", "name": "dab", "duration": 3.75, "is_free": True},
    "188": {"id": "dance-gangnamstyle", "name": "gangnamstyle", "duration": 15.0, "is_free": True},
    "189": {"id": "emoji-crying", "name": "sob", "duration": 4.91, "is_free": True},
    "190": {"id": "idle-loop-tapdance", "name": "taploop", "duration": 7.81, "is_free": True},
    "191": {"id": "idle-sleep", "name": "sleepy", "duration": 3.35, "is_free": True},
    "192": {"id": "dance-sexy", "name": "wiggledance", "duration": 13.70, "is_free": True},
    "193": {"id": "emoji-eyeroll", "name": "eyeroll", "duration": 3.75, "is_free": True},
    "194": {"id": "dance-moonwalk", "name": "moonwalk", "duration": 12.0, "is_free": True},
    "195": {"id": "idle-fighter", "name": "fighter", "duration": 18.64, "is_free": True},
    "196": {"id": "idle-dance-tiktok7", "name": "renegade", "duration": 14.05, "is_free": True},
    "197": {"id": "emote-facepalm", "name": "facepalm", "duration": 5.0, "is_free": True},
    "198": {"id": "idle-dance-headbobbing", "name": "feelthebeat", "duration": 23.65, "is_free": True},
    "199": {"id": "emote-pose8", "name": "happy", "duration": 5.62, "is_free": True},
    "200": {"id": "emote-hug", "name": "hug", "duration": 4.53, "is_free": True},
    "201": {"id": "emote-slap", "name": "slap", "duration": 4.06, "is_free": True},
    "202": {"id": "emoji-clapping", "name": "clap", "duration": 2.98, "is_free": True},
    "203": {"id": "emote-exasperated", "name": "exasperated", "duration": 4.10, "is_free": True},
    "204": {"id": "emote-kissing-passionate", "name": "sweetsmooch", "duration": 10.47, "is_free": True},
    "205": {"id": "emote-tapdance", "name": "tapdance", "duration": 6.0, "is_free": True},
    "206": {"id": "emote-suckthumb", "name": "thumbsuck", "duration": 5.23, "is_free": True},
    "207": {"id": "dance-harlemshake", "name": "harlemshake", "duration": 10.0, "is_free": True},
    "208": {"id": "emote-heartfingers", "name": "heartfingers", "duration": 5.18, "is_free": True},
    "209": {"id": "idle-loop-aerobics", "name": "aerobics", "duration": 10.08, "is_free": True},
    "210": {"id": "emote-heartshape", "name": "heartshape", "duration": 7.60, "is_free": True},
    "211": {"id": "emote-hearteyes", "name": "hearteyes", "duration": 5.99, "is_free": True},
    "212": {"id": "dance-wild", "name": "karmadance", "duration": 16.25, "is_free": True},
    "213": {"id": "emoji-scared", "name": "gasp", "duration": 4.06, "is_free": True},
    "214": {"id": "emote-think", "name": "think", "duration": 4.81, "is_free": True},
    "215": {"id": "emoji-dizzy", "name": "stunned", "duration": 5.38, "is_free": True},
    "216": {"id": "emote-embarrassed", "name": "embarrassed", "duration": 9.09, "is_free": True},
    "217": {"id": "emote-disappear", "name": "blastoff", "duration": 5.53, "is_free": True},
    "218": {"id": "idle-loop-annoyed", "name": "annoyed", "duration": 18.62, "is_free": True},
    "219": {"id": "dance-zombie", "name": "dancezombie", "duration": 13.83, "is_free": True},
    "220": {"id": "idle-loop-happy", "name": "chillin", "duration": 19.80, "is_free": True},
    "221": {"id": "emote-frustrated", "name": "frustrated", "duration": 6.41, "is_free": True},
    "222": {"id": "idle-loop-sad", "name": "bummed", "duration": 21.80, "is_free": True},
    "223": {"id": "emoji-ghost", "name": "ghost", "duration": 3.74, "is_free": True},
    "224": {"id": "emoji-mind-blown", "name": "mindblown", "duration": 3.46, "is_free": True}
}

# ============================================================================
# CLASE PRINCIPAL DEL BOT
# ============================================================================

class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.last_announcement = 0
        self.user_positions = {}
        self.connection_retries = 0
        self.bot_mode = "idle"
        self.current_emote_task = None
        self.flashmode_cooldown = {}
        self.session_active = False
        self.reconnection_in_progress = False
        self.copied_emotes = {}  # {número: {"emote_id": str, "name": str, "from_user": str}}
        self.copied_emote_mode = False
        self.current_copied_emote = None
        self.floss_loop_active = False
        self.floss_task = None
        self.auto_messages = []
        self.auto_msg_task = None
        self.restrict_p1 = None
        self.restrict_p2 = None
        self.announcement_task = None
        self.console_msg_task = None
        self.inventory_task = None
        self.bot_username = None  # Se rellena dinámicamente en on_start

    # ========================================================================
    # MÉTODOS DE INICIALIZACIÓN Y CONEXIÓN
    # ========================================================================

    async def connect_with_retry(self):
        """Conexión con reintentos"""
        safe_print("✅ Conexión establecida con High Rise")
        return True

    async def auto_reconnect_loop(self):
        """Sistema de reconexión automática optimizado"""
        while True:
            try:
                await asyncio.sleep(60)  # Verificar cada minuto para no saturar
                
                if not self.session_active:
                    continue

                try:
                    room_users = await self.highrise.get_room_users()
                    if isinstance(room_users, Error):
                        # Si hay error de transporte o timeout, intentar reconectar
                        if any(err in str(room_users.message).lower() for err in ["timeout", "transport", "network", "closed"]):
                            log_event("WARNING", f"Error de red detectado: {room_users.message}. Reconectando...")
                            await self.attempt_reconnection()
                        return
                    
                    # Verificar si el bot está en la lista de usuarios
                    users = room_users.content
                    bot_in_room = any(u.id == self.bot_id for u, _ in users)
                    
                    if not bot_in_room:
                        log_event("WARNING", "Bot no encontrado en la sala, intentando reconectar...")
                        await self.attempt_reconnection()
                        
                except Exception as e:
                    if any(err in str(e).lower() for err in ["closed", "connection", "transport"]):
                        await self.attempt_reconnection()
                    
            except Exception as e:
                log_event("ERROR", f"Error en auto_reconnect_loop: {e}")
                await asyncio.sleep(10)

    async def attempt_reconnection(self):
        """Intenta reconectar el bot"""
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                safe_print(f"🔄 Intento de reconexión {attempt}/{max_attempts}...")
                log_event("BOT", f"Intento de reconexión {attempt}/{max_attempts}")
                
                # Esperar antes de reintentar
                await asyncio.sleep(attempt * 2)
                
                # Intentar obtener usuarios de la sala como prueba de conexión
                room_users = await self.highrise.get_room_users()
                if not isinstance(room_users, Error):
                    safe_print("✅ Reconexión exitosa!")
                    log_event("BOT", "Reconexión exitosa")
                    
                    # Reiniciar tareas en segundo plano solo si no están activas
                    # Cancelar siempre antes de recrear para evitar tareas duplicadas (spam)
                    if self.announcement_task is None or self.announcement_task.done():
                        if self.announcement_task and not self.announcement_task.done():
                            self.announcement_task.cancel()
                        self.announcement_task = asyncio.create_task(self.start_announcements())
                    if self.console_msg_task is None or self.console_msg_task.done():
                        if self.console_msg_task and not self.console_msg_task.done():
                            self.console_msg_task.cancel()
                        self.console_msg_task = asyncio.create_task(self.check_console_messages())
                    if self.inventory_task is None or self.inventory_task.done():
                        if self.inventory_task and not self.inventory_task.done():
                            self.inventory_task.cancel()
                        self.inventory_task = asyncio.create_task(self.periodic_inventory_save())
                    
                    # Sistema automático de emotes desactivado
                    # if self.bot_mode == "auto":
                    #     asyncio.create_task(self.start_auto_emote_cycle())
                        
                    return True
                    
            except Exception as e:
                log_event("ERROR", f"Fallo en intento {attempt}: {e}")
                safe_print(f"❌ Fallo en intento {attempt}: {e}")
                
        safe_print("❌ No se pudo reconectar después de varios intentos")
        log_event("ERROR", "Reconexión fallida después de múltiples intentos")
        return False

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        """Inicio del bot"""
        try:
            self.bot_id = session_metadata.user_id
            self.session_active = True
            log_event("BOT", f"Bot ID almacenado: {self.bot_id}")
            load_subscribers()
            load_user_conversations()

            if await self.connect_with_retry():
                safe_print("Bot conectado exitosamente!")
                self.load_data()

                # Obtener el username del bot dinámicamente
                try:
                    room_users_resp = await self.highrise.get_room_users()
                    if not isinstance(room_users_resp, Exception):
                        for u, _ in room_users_resp.content:
                            if u.id == self.bot_id:
                                self.bot_username = u.username
                                log_event("BOT", f"Username del bot: {self.bot_username}")
                                break
                except Exception as e:
                    log_event("ERROR", f"No se pudo obtener el username del bot: {e}")

                # Iniciar tareas en segundo plano
                self.announcement_task = asyncio.create_task(self.start_announcements())
                self.console_msg_task = asyncio.create_task(self.check_console_messages())
                self.inventory_task = asyncio.create_task(self.periodic_inventory_save())
                asyncio.create_task(self.auto_reconnect_loop())

                # Cargar y restaurar anuncios automáticos personalizados si existen
                try:
                    if os.path.exists("data/auto_msg_config.json"):
                        with open("data/auto_msg_config.json", "r", encoding="utf-8") as f:
                            config_data = json.load(f)
                            if config_data.get("active") and config_data.get("message") and config_data.get("interval"):
                                self.auto_msg_task = asyncio.create_task(
                                    self.auto_msg_loop(config_data["message"], config_data["interval"])
                                )
                                log_event("BOT", "Anuncio automático restaurado desde persistencia")
                except Exception as e:
                    log_event("ERROR", f"Error restaurando anuncio automático: {e}")

                # Configurar apariencia inicial
                await self.setup_initial_bot_appearance()
                await save_bot_inventory(self)

                # Iniciar floss automático al iniciar
                self.floss_loop_active = True
                self.bot_mode = "floss"
                self.floss_task = asyncio.create_task(self.floss_loop())
                safe_print("💃 Floss infinito iniciado automáticamente")
                log_event("BOT", "Floss infinito iniciado automáticamente")
            else:
                print("No se pudo conectar al servidor")
                sys.exit(1)
        except Exception as e:
            print(f"Error en on_start: {e}")

        safe_print("🤖 ¡Bot iniciado! Usa !help para ver los comandos.")

    # ========================================================================
    # SISTEMA DE CARGA Y GUARDADO DE DATOS
    # ========================================================================

    def load_data(self):
        """Carga datos desde archivos"""
        try:
            # Crear directorio data si no existe
            os.makedirs("data", exist_ok=True)
            
            # Cargar VIP
            if os.path.exists("data/vip.txt"):
                with open("data/vip.txt", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip() and not line.startswith("#"):
                            VIP_USERS.add(line.strip())
            safe_print(f"✅ Datos VIP cargados: {len(VIP_USERS)} usuarios")

            # Cargar puntos de teletransporte
            if os.path.exists("data/teleport_points.txt"):
                with open("data/teleport_points.txt", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip() and not line.startswith("#"):
                            try:
                                parts = line.strip().split("|")
                                if len(parts) == 4:
                                    name = parts[0]
                                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                                    TELEPORT_POINTS[name] = {"x": x, "y": y, "z": z}
                            except ValueError as e:
                                safe_print(f"⚠️ Error parseando punto: {line.strip()} - {e}")
            safe_print(f"✅ Puntos de teletransporte cargados: {len(TELEPORT_POINTS)} puntos")
            
            # Cargar corazones
            if os.path.exists("data/hearts.txt"):
                with open("data/hearts.txt", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip() and not line.startswith("#"):
                            try:
                                parts = line.strip().split(":")
                                if len(parts) >= 2:
                                    user_id = parts[0]
                                    hearts = int(parts[1])
                                    USER_HEARTS[user_id] = hearts
                                    if len(parts) >= 3:
                                        USER_NAMES[user_id] = parts[2]
                            except ValueError as e:
                                safe_print(f"⚠️ Error parseando corazones: {line.strip()} - {e}")
            safe_print(f"✅ Corazones cargados: {len(USER_HEARTS)} usuarios")
            
            # Cargar actividad
            if os.path.exists("data/activity.txt"):
                with open("data/activity.txt", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip() and not line.startswith("#"):
                            try:
                                parts = line.strip().split(":")
                                if len(parts) >= 3:
                                    user_id = parts[0]
                                    messages = int(parts[1])
                                    last_activity = parts[2]
                                    USER_ACTIVITY[user_id] = {
                                        "messages": messages,
                                        "last_activity": datetime.fromisoformat(last_activity)
                                    }
                                    if len(parts) >= 4:
                                        USER_NAMES[user_id] = parts[3]
                            except (ValueError, IndexError) as e:
                                safe_print(f"⚠️ Error parseando actividad: {line.strip()} - {e}")
            safe_print(f"✅ Actividad cargada: {len(USER_ACTIVITY)} usuarios")
            
            # Cargar información de usuarios
            if os.path.exists("data/user_info.json"):
                with open("data/user_info.json", "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    for user_id, data in loaded_data.items():
                        USER_INFO[user_id] = data
                        # Convertir fechas ISO a datetime
                        for key in ["first_seen", "account_created"]:
                            if key in data and data[key]:
                                try:
                                    USER_INFO[user_id][key] = datetime.fromisoformat(data[key].replace('Z', '+00:00'))
                                except:
                                    pass
            safe_print(f"✅ Info de usuarios cargada: {len(USER_INFO)} usuarios")
            
            # Cargar outfits guardados
            if os.path.exists("data/saved_outfits.json"):
                from highrise.models import Item
                try:
                    with open("data/saved_outfits.json", "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            outfits_data = json.loads(content)
                            for num_str, items_data in outfits_data.items():
                                outfit_items = [Item(type=item["type"], id=item["id"], amount=item.get("amount", 1)) for item in items_data]
                                SAVED_OUTFITS[int(num_str)] = outfit_items
                except json.JSONDecodeError:
                    safe_print("⚠️ Archivo saved_outfits.json corrupto o vacío, inicializando...")
                    with open("data/saved_outfits.json", "w", encoding="utf-8") as f:
                        json.dump({}, f)
            safe_print(f"✅ Outfits guardados cargados: {len(SAVED_OUTFITS)} outfits")
            
        except Exception as e:
            safe_print(f"❌ Error cargando datos: {e}")
            import traceback
            traceback.print_exc()

    def save_data(self):
        """Guarda datos en archivos"""
        try:
            os.makedirs("data", exist_ok=True)

            # Guardar VIP
            with open("data/vip.txt", "w", encoding="utf-8") as f:
                f.write("# Usuarios VIP (un username por línea)\n")
                for username in sorted(VIP_USERS):
                    f.write(f"{username}\n")
            safe_print(f"✅ Datos VIP guardados: {len(VIP_USERS)} usuarios")

            # Guardar puntos de teletransporte
            with open("data/teleport_points.txt", "w", encoding="utf-8") as f:
                f.write("# Puntos de teletransporte (nombre|x|y|z)\n")
                for name, coords in sorted(TELEPORT_POINTS.items()):
                    f.write(f"{name}|{coords['x']}|{coords['y']}|{coords['z']}\n")
            safe_print(f"✅ Puntos de teletransporte guardados: {len(TELEPORT_POINTS)}")

            # Guardar outfits
            if SAVED_OUTFITS:
                outfits_data = {}
                for num, outfit in SAVED_OUTFITS.items():
                    outfits_data[str(num)] = [{"type": item.type, "id": item.id, "amount": item.amount} for item in outfit]
                
                with open("data/saved_outfits.json", "w", encoding="utf-8") as f:
                    json.dump(outfits_data, f, indent=2, ensure_ascii=False)
                safe_print(f"✅ Outfits guardados: {len(SAVED_OUTFITS)}")

            save_user_info()
            save_leaderboard_data()
            
        except Exception as e:
            safe_print(f"❌ Error guardando datos: {e}")
            import traceback
            traceback.print_exc()

    # ========================================================================
    # SISTEMA DE VERIFICACIÓN DE PERMISOS
    # ========================================================================

    def is_owner(self, user_id: str) -> bool:
        """Verifica si es el propietario"""
        return user_id == OWNER_ID

    def is_admin(self, user_id: str) -> bool:
        """Verifica si es administrador"""
        return user_id in ADMIN_IDS

    def is_moderator(self, user_id: str) -> bool:
        """Verifica si es moderador"""
        return user_id in MODERATOR_IDS or self.is_admin(user_id)

    def is_vip(self, user_id: str) -> bool:
        """Verifica si es VIP por user_id"""
        # Check if they have temporary VIP via !sub
        if user_id in USER_INFO and "vip_expires" in USER_INFO[user_id]:
            try:
                expires = datetime.fromisoformat(USER_INFO[user_id]["vip_expires"])
                if datetime.now() < expires:
                    return True
            except:
                pass

        username = USER_NAMES.get(user_id)
        if username:
            return username in VIP_USERS
        return False

    def is_vip_by_username(self, username: str) -> bool:
        """Verifica si es VIP por username"""
        # We don't have user_id here easily, but we can check if any user with this username has active VIP
        # This is less efficient but covers the requirement
        for uid, info in USER_INFO.items():
            if info.get("username") == username and "vip_expires" in info:
                try:
                    expires = datetime.fromisoformat(info["vip_expires"])
                    if datetime.now() < expires:
                        return True
                except:
                    continue

        return username in VIP_USERS

    def is_banned(self, user_id: str) -> bool:
        """Verifica si está baneado"""
        if user_id in BANNED_USERS:
            ban_data = BANNED_USERS[user_id]
            if isinstance(ban_data, dict) and "time" in ban_data:
                ban_time = ban_data["time"]
                if isinstance(ban_time, str):
                    try:
                        ban_time = datetime.fromisoformat(ban_time.replace('Z', '+00:00'))
                    except:
                        return True
                if datetime.now() > ban_time:
                    del BANNED_USERS[user_id]
                    return False
                return True
            return True
        return False

    def is_muted(self, user_id: str) -> bool:
        """Verifica si está silenciado"""
        if user_id in MUTED_USERS:
            mute_time = MUTED_USERS[user_id]
            if isinstance(mute_time, str):
                try:
                    mute_time = datetime.fromisoformat(mute_time.replace('Z', '+00:00'))
                except:
                    return True
            if datetime.now() > mute_time:
                del MUTED_USERS[user_id]
                return False
            return True
        return False

    # ========================================================================
    # SISTEMA DE GESTIÓN DE USUARIOS
    # ========================================================================

    def get_user_hearts(self, user_id: str) -> int:
        """Obtiene corazones del usuario"""
        return USER_HEARTS.get(user_id, 0)

    def add_user_hearts(self, user_id: str, hearts: int, username: str | None = None):
        """Añade corazones al usuario"""
        if user_id not in USER_HEARTS:
            USER_HEARTS[user_id] = 0
        USER_HEARTS[user_id] += hearts

        if username:
            USER_NAMES[user_id] = username

        save_leaderboard_data()

    def update_activity(self, user_id: str):
        """Actualiza actividad del usuario"""
        if user_id not in USER_ACTIVITY:
            USER_ACTIVITY[user_id] = {"messages": 0, "last_activity": datetime.now()}
        USER_ACTIVITY[user_id]["messages"] += 1
        USER_ACTIVITY[user_id]["last_activity"] = datetime.now()

        if user_id in USER_INFO:
            USER_INFO[user_id]["total_messages"] = USER_ACTIVITY[user_id]["messages"]

    def update_user_info(self, user_id: str, username: str):
        """Actualiza información del usuario"""
        if user_id not in USER_INFO:
            USER_INFO[user_id] = {
                "username": username,
                "first_seen": datetime.now().isoformat(),
                "account_created": None,
                "total_time_in_room": 0,
                "total_messages": 0,
                "time_joined": time.time()
            }
        else:
            USER_INFO[user_id]["username"] = username
            USER_INFO[user_id]["total_messages"] = USER_ACTIVITY.get(user_id, {}).get("messages", 0)

    def get_user_role_info(self, user: User) -> str:
        """Obtiene información sobre el rol del usuario"""
        user_id = user.id
        username = user.username

        if user_id == OWNER_ID:
            return "👑 Propietario del Bot"
        elif self.is_admin(user_id):
            return "🛡️ Administrador"
        elif self.is_moderator(user_id):
            return "⚖️ Moderador"
        elif self.is_vip_by_username(username):
            return "⭐ Usuario VIP"
        else:
            return "👤 Usuario Normal"

    def format_time(self, seconds: int) -> str:
        """Formatea el tiempo en formato legible"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def get_user_total_time(self, user_id: str) -> int:
        """Obtiene el tiempo total del usuario en la sala"""
        if user_id in USER_INFO:
            return USER_INFO[user_id].get("total_time_in_room", 0)
        return 0

    def get_help_for_user(self, user_id: str, username: str) -> str:
        """Retorna comandos disponibles según el rol del usuario"""
        is_owner = (user_id == OWNER_ID)
        is_admin = self.is_admin(user_id)
        is_vip = self.is_vip(user_id)

        if is_owner or is_admin:
            return ("👑 COMANDOS PROPIETARIO/ADMIN:\n"
                    "📊 INFORMACIÓN:\n"
                    "!info - Tu información\n"
                    "!role - Tu rol\n"
                    "!stats - Estadísticas sala\n"
                    "!online - Usuarios online\n"
                    "!myid - Tu ID|||"
                    "💖 CORAZONES:\n"
                    "!heart @user [cantidad] - Dar corazones\n"
                    "!heartall - Corazones a todos\n"
                    "!love @user1 @user2 - Amorómetro|||"
                    "🎭 EMOTES:\n"
                    "!emote list - Lista emotes\n"
                    "!emote @user [emote] - Emote a usuario\n"
                    "!emote all [emote] - Emote a todos\n"
                    "!stop - Detener tu emote\n"
                    "!stop @user - Detener emote usuario\n"
                    "!stopall - Detener todos emotes|||"
                    "⚡ TELETRANSPORTE:\n"
                    "!summ @user - Traer usuario a ti\n"
                    "!send @user [punto] - Enviar usuario a punto\n"
                    "!goto @user [punto] - Enviar usuario a punto (con aviso)\n"
                    "!tp [punto] - Ir a un punto\n"
                    "!tplist - Ver puntos guardados\n"
                    "!tome - Bot a ti|||"
                    "🔨 MODERACIÓN:\n"
                    "!vip @user - Dar VIP\n"
                    "!unvip @user - Quitar VIP\n"
                    "!kick @user - Expulsar\n"
                    "!ban @user - Banear\n"
                    "!unban @user - Desbanear\n"
                    "!mute @user [seg] - Silenciar\n"
                    "!unmute @user - Quitar silencio\n"
                    "!jail @user - Enviar a cárcel\n"
                    "!unjail @user - Liberar de cárcel\n"
                    "!banlist - Lista baneados\n"
                    "!mutelist - Lista silenciados|||"
                    "🤖 BOT:\n"
                    "!auto [mensaje] [seg] - Anuncio automático\n"
                    "!stopauto - Detener anuncios\n"
                    "!sub / !unsub - Suscribirse a invitaciones\n"
                    "!invite @user / !invite all - Enviar invitaciones\n"
                    "!follow @user - Bot sigue a usuario\n"
                    "!unfollow - Bot deja de seguir\n"
                    "!say [mensaje] - Bot habla\n"
                    "!mimic @user - Imitar usuario\n"
                    "!copyoutfit - Copiar tu outfit|||"
                    "💰 ECONOMÍA:\n"
                    "!tip all [1-5] - Dar oro a todos\n"
                    "!wallet - Balance bot|||"
                    "🏆 LOGROS & RANKING:\n"
                    "!leaderboard heart - Top corazones\n"
                    "!leaderboard active - Top actividad\n"
                    "!rank - Tu rango\n"
                    "!achievements - Tus logros\n"
                    "!daily - Recompensa diaria|||"
                    "⚙️ CONFIGURACIÓN:\n"
                    "!setvipzone - Establecer zona VIP\n"
                    "!setdj - Establecer zona DJ\n"
                    "!setspawn - Establecer punto inicio bot\n"
                    "!addzone [nombre] - Crear zona personalizada|||"
                    "🥊 INTERACCIONES:\n"
                    "!punch @user - Golpear\n"
                    "!slap @user - Bofetada\n"
                    "!hug @user - Abrazar\n"
                    "!laugh @user - Reír\n"
                    "!boom @user - Explotar|||"
                    "🔧 SISTEMA:\n"
                    "!restart - Reiniciar bot\n"
                    "!help - Ver esta lista")

        elif is_vip:
            return ("⭐ COMANDOS VIP:\n"
                    "📊 INFORMACIÓN:\n"
                    "!info - Tu información\n"
                    "!role - Tu rol\n"
                    "!stats - Estadísticas sala\n"
                    "!online - Usuarios online\n"
                    "!myid - Tu ID|||"
                    "💖 CORAZONES:\n"
                    "!heart @user - Dar corazón\n"
                    "!love @user1 @user2 - Amorómetro|||"
                    "🎭 EMOTES:\n"
                    "!emote list - Lista emotes\n"
                    "!stop - Detener tu emote|||"
                    "⚡ TELETRANSPORTE:\n"
                    "!tp [punto] - Ir a un punto\n"
                    "!tplist - Ver puntos guardados|||"
                    "🤖 BOT:\n"
                    "!sub / !unsub - Suscribirse a invitaciones\n"
                    "!invite @user - Enviar invitación|||"
                    "🏆 LOGROS & RANKING:\n"
                    "!leaderboard heart - Top corazones\n"
                    "!leaderboard active - Top actividad\n"
                    "!rank - Tu rango\n"
                    "!achievements - Tus logros\n"
                    "!daily - Recompensa diaria|||"
                    "🥊 INTERACCIONES:\n"
                    "!punch @user - Golpear\n"
                    "!slap @user - Bofetada\n"
                    "!hug @user - Abrazar\n"
                    "!laugh @user - Reír\n"
                    "!boom @user - Explotar|||"
                    "🔧 AYUDA:\n"
                    "!help - Ver esta lista")

        else:
            return ("👤 COMANDOS USUARIO:\n"
                    "📊 INFORMACIÓN:\n"
                    "!info - Tu información\n"
                    "!role - Tu rol\n"
                    "!stats - Estadísticas sala\n"
                    "!online - Usuarios online\n"
                    "!myid - Tu ID|||"
                    "💖 CORAZONES:\n"
                    "!heart @user - Dar corazón\n"
                    "!love @user1 @user2 - Amorómetro|||"
                    "🎭 EMOTES:\n"
                    "!emote list - Lista emotes\n"
                    "!stop - Detener tu emote|||"
                    "⚡ TELETRANSPORTE:\n"
                    "!tp [punto] - Ir a un punto\n"
                    "!tplist - Ver puntos guardados|||"
                    "🤖 BOT:\n"
                    "!sub / !unsub - Suscribirse a invitaciones\n"
                    "!invite @user - Enviar invitación|||"
                    "🏆 LOGROS & RANKING:\n"
                    "!leaderboard heart - Top corazones\n"
                    "!leaderboard active - Top actividad\n"
                    "!rank - Tu rango\n"
                    "!achievements - Tus logros\n"
                    "!daily - Recompensa diaria|||"
                    "🥊 INTERACCIONES:\n"
                    "!punch @user - Golpear\n"
                    "!slap @user - Bofetada\n"
                    "!hug @user - Abrazar\n"
                    "!laugh @user - Reír\n"
                    "!boom @user - Explotar|||"
                    "🔧 AYUDA:\n"
                    "!help - Ver esta lista")

    def is_in_forbidden_zone(self, x: float, y: float, z: float, user_id: Optional[str] = None) -> bool:
        """Verifica si el punto está en zona prohibida
        Admin y owner tienen acceso completo a todas las zonas"""
        # Admin y owner pueden acceder a cualquier zona
        if user_id and (self.is_admin(user_id) or user_id == OWNER_ID):
            return False
        
        for zone in FORBIDDEN_ZONES:
            distance = ((x - zone["x"])**2 + (y - zone["y"])**2 + (z - zone["z"])**2)**0.5
            if distance <= zone["radius"]:
                return True
        return False

    def calculate_distance(self, pos1, pos2) -> float:
        """Calcula la distancia entre dos posiciones"""
        return ((pos1.x - pos2.x)**2 + (pos1.y - pos2.y)**2 + (pos1.z - pos2.z)**2)**0.5

    async def teleport_user(self, user_id: str, x: float, y: float, z: float):
        """Teletransporta al usuario"""
        try:
            position = Position(x, y, z)
            await self.highrise.teleport(user_id, position)
            return True
        except Exception as e:
            print(f"Error en teleport_user: {e}")
            return False

    async def send_emote_loop(self, user_id: str, emote_id: str):
        """Inicia la emoción en un bucle infinito sin pausas"""
        ACTIVE_EMOTES[user_id] = emote_id

        emote_info = next((e for e in emotes.values() if e["id"] == emote_id), None)
        if not emote_info:
            if user_id in ACTIVE_EMOTES: del ACTIVE_EMOTES[user_id]
            return

        while user_id in ACTIVE_EMOTES and ACTIVE_EMOTES[user_id] == emote_id and ACTIVE_EMOTES[user_id] is not None:
            try:
                await self.highrise.send_emote(emote_id, user_id)
                duration = emote_info.get("duration", 5)
                # Reducir pausa para transición fluida (2 segundos menos para eliminar pausas)
                await asyncio.sleep(max(0.05, duration - 2))
            except Exception as e:
                print(f"Error en send_emote_loop: {e}")
                break

        if user_id in ACTIVE_EMOTES and ACTIVE_EMOTES[user_id] is None:
            del ACTIVE_EMOTES[user_id]

    async def stop_emote_loop(self, user_id: str):
        """Detiene la emoción en el bucle"""
        if user_id in ACTIVE_EMOTES:
            ACTIVE_EMOTES[user_id] = None
            try:
                stop_animations = ["idle", "idle-loop-happy", "idle-loop-sad", "idle-loop-tired"]
                for stop_anim in stop_animations:
                    try:
                        await self.highrise.send_emote(stop_anim, user_id)
                        await asyncio.sleep(0.1)
                    except Exception:
                        continue
            except Exception as e:
                print(f"Error general en stop_animations: {e}")

            await asyncio.sleep(1.0)
            if user_id in ACTIVE_EMOTES:
                del ACTIVE_EMOTES[user_id]

    async def floss_loop(self):
        """Bucle infinito de floss para el bot"""
        floss_emote = "dance-floss"
        floss_duration = 21.0
        
        while self.floss_loop_active and self.bot_mode == "floss":
            try:
                await self.highrise.send_emote(floss_emote)
                await asyncio.sleep(floss_duration)
            except Exception as e:
                safe_print(f"Error en floss_loop: {e}")
                await asyncio.sleep(1)
        
        # Asegurar limpieza
        if self.floss_loop_active:
            self.floss_loop_active = False

    async def follow_user_loop(self, target_user_id: str):
        """El bot sigue a un usuario continuamente"""
        global FOLLOW_TARGET
        while FOLLOW_TARGET == target_user_id:
            try:
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await asyncio.sleep(2)
                    continue
                users = response.content
                target_pos = None
                bot_user = None
                for u, pos in users:
                    if u.id == target_user_id:
                        target_pos = pos
                    if hasattr(self, 'bot_id') and u.id == self.bot_id:
                        bot_user = u
                if not target_pos or not bot_user:
                    await asyncio.sleep(2)
                    continue
                if isinstance(target_pos, Position):
                    new_position = Position(target_pos.x + 1.0, target_pos.y, target_pos.z)
                elif isinstance(target_pos, AnchorPosition) and target_pos.offset:
                    new_position = Position(target_pos.offset.x + 1.0, target_pos.offset.y, target_pos.offset.z)
                else:
                    await asyncio.sleep(2)
                    continue
                await self.highrise.teleport(bot_user.id, new_position)
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"Error en follow_user_loop: {e}")
                await asyncio.sleep(2)

    async def handle_command(self, user: User, message: str, is_whisper: bool, is_dm: bool = False, conversation_id: str = None) -> None:
        """Procesa comandos del usuario"""
        global VIP_ZONE, FOLLOW_TARGET
        msg = message.strip()
        user_id = user.id
        username = user.username

        public_commands = [
            "!love", "!stats", "!online", "!info", "!role"
        ]
        force_public = any(msg.startswith(cmd) for cmd in public_commands)

        context_dependent_commands = [
            "!heart", "!heartall", "!thumbs", "!clap", "!wave",
            "!punch", "!slap", "!flirt", "!scare", "!electro", 
            "!hug", "!ninja", "!laugh", "!boom"
        ]
        is_context_dependent = any(msg.startswith(cmd) for cmd in context_dependent_commands)

        async def send_response(text: str):
            # Registrar comando y respuesta en formato claro
            if msg.startswith("!"):
                log_bot_response(f"@{username}: {msg}")
                log_bot_response(f"BOT → {text}")
            
            # PRIORIDAD MÁXIMA: Si es DM, USAR SOLO SEND_MESSAGE
            # Detectamos por is_dm, conversation_id o si el mensaje no empezó con ! pero vino de on_message
            if is_dm or conversation_id:
                safe_print(f"🎯 [DM RESPONSE] Forzando respuesta privada para @{username}")
                effective_id = conversation_id
                if not effective_id:
                    # Recuperación de emergencia
                    try:
                        convs = await self.highrise.get_conversations()
                        if not isinstance(convs, Error):
                            for c in convs.conversations:
                                if any(user.id in p.id for p in c.participants):
                                    effective_id = c.id
                                    break
                    except: pass

                if effective_id:
                    try:
                        await self.highrise.send_message(effective_id, text, type="text")
                        safe_print(f"✅ [DM SENT] conversation_id: {effective_id}")
                        return
                    except Exception as e:
                        safe_print(f"❌ [DM FAILED] {e}")

                # Si falla el mensaje directo, intentar susurro como último recurso privado
                try:
                    await self.highrise.send_whisper(user.id, text)
                    safe_print(f"✅ [DM FALLBACK WHISPER] Enviado a @{username}")
                except:
                    safe_print(f"❌ [DM TOTAL FAILURE] No se pudo contactar a @{username}")
                return

            # Solo si NO es DM llegamos aquí
            if force_public:
                await self.highrise.chat(text)
            elif is_context_dependent:
                if is_whisper:
                    await self.highrise.send_whisper(user.id, text)
                else:
                    await self.highrise.chat(text)
            else:
                await self.highrise.send_whisper(user.id, text)

        # Comando !room (room_id)
        if msg == "!room" or msg.startswith("!room "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ Solo el Propietario o Administradores pueden cambiar de sala.")
                return
            
            parts = msg.split()
            if len(parts) < 2:
                await send_response("❌ Uso: !room (room_id)")
                return
            
            new_room_id = parts[1]
            await send_response(f"🔄 Cambiando a la sala {new_room_id}... Me desconectaré por 10 segundos.")
            await asyncio.sleep(2)
            
            # Registrar el evento
            log_event("ROOM_CHANGE", f"Cambiando a sala {new_room_id} solicitado por {username}")
            
            # Actualizar config.json con el nuevo room_id
            try:
                import json
                with open("config.json", "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                config_data["room_id"] = new_room_id
                with open("config.json", "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4)
                # Forzar escritura a disco
                f.flush()
                os.fsync(f.fileno())
            except Exception as e:
                log_event("ERROR", f"Error actualizando config.json: {e}")

            # Salir inmediatamente. El reinicio de 10 segundos se maneja en run.py
            import os
            os._exit(0) 
            return

        # Comando !help
        if msg == "!help":
            help_text = self.get_help_for_user(user_id, username)
            help_groups = help_text.split('|||')
            
            # Enviar cada grupo de comandos por separado con delay
            for group in help_groups:
                if group.strip():
                    # Dividir grupos muy largos en sub-mensajes si exceden ~250 caracteres
                    group_text = group.strip()
                    if len(group_text) > 250:
                        lines = group_text.split('\n')
                        current_msg = ""
                        for line in lines:
                            if len(current_msg) + len(line) + 1 > 250:
                                if current_msg:
                                    await send_response(current_msg)
                                    await asyncio.sleep(0.5)
                                current_msg = line
                            else:
                                current_msg += ("\n" if current_msg else "") + line
                        if current_msg:
                            await send_response(current_msg)
                            await asyncio.sleep(0.5)
                    else:
                        await send_response(group_text)
                        await asyncio.sleep(0.5)
            return

        # Comando !info
        if msg == "!info":
            await self.show_user_info(user, public_response=(not is_dm))
            return

        # Comando !botid (Admin/Owner)
        if msg == "!botid":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ No tienes permisos para este comando.")
                return
            await send_response(f"🤖 Mi ID de Highrise es: {self.bot_id}")
            return

        # Comando !test
        if msg == "!test":
            # Obtenemos el nombre de usuario de forma segura
            user_to_rate = username if username else f"User_{user_id[:5]}"
            rating = random.randint(1, 10)
            comments = [
                "¡Ese outfit es espectacular! 🔥",
                "Se nota el estilo, ¡muy bien! ✨",
                "Interesante combinación, me gusta. 😎",
                "Un clásico que nunca falla. 👍",
                "¡Tienes mucha personalidad vistiendo! 💎",
                "¡Vaya flow llevas hoy! 🌊",
                "Me gusta mucho ese toque único. 🎨",
                "¡Elegancia pura! 🎩",
                "Un poco arriesgado, ¡pero funciona! ⚡",
                "¡Definitivamente eres el alma de la sala! 🌟"
            ]
            comment = random.choice(comments)
            await send_response(f"⭐ Calificando el outfit de @{user_to_rate}...\n📊 Puntuación: {rating}/10\n💬 {comment}")
            return
        if msg.startswith("!info @"):
            target_username = msg[7:].strip()
            await self.show_user_info_by_username(target_username)
            return

        # Comando !role
        if msg == "!role":
            role_info = self.get_user_role_info(user)
            await send_response(f"🎭 {role_info}")
            return
        if msg.startswith("!role @"):
            target_username = msg[7:].strip()
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            if not target_user:
                await send_response(f"❌ Usuario {target_username} no encontrado!")
                return
            role_info = self.get_user_role_info(target_user)
            await send_response(f"🎭 {role_info}")
            return
        if msg == "!role list":
            await send_response("🎭 LISTA DE ROLES:\n👑 Propietario\n🛡️ Administrador\n⚖️ Moderador\n⭐ VIP\n👤 Usuario Normal")
            return

        # Ayuda para secciones
        if msg == "!help interaction": await send_response("🥊 COMANDOS DE INTERACCIÓN:\n!punch @user — golpear\n!slap @user — bofetada\n!flirt @user — coquetear\n!scare @user — asustar\n!electro @user — electricidad\n!hug @user — abrazar\n!ninja @user — ninja\n!laugh @user — reír\n!boom @user — explosión")
        if msg == "!help teleport": await send_response("📍 COMANDOS DE TELETRANSPORTE:\n!tplist — lista de puntos\n[nombre_punto] — teletransporte al punto\n!tele zonaVIP — zona VIP")
        if msg == "!help leaderboard": await send_response("🏆 TABLA DE CLASIFICACIÓN:\n!leaderboard heart — top por corazones\n!leaderboard active — top por actividad")
        if msg == "!help heart": await send_response("❤️ COMANDO DE CORAZONES:\n!heart @usuario [cantidad] — enviar corazones\n💖 También puedes enviar corazones con reacciones!")

        # Comando !copyemote @user o !copyemote [user_id]
        if msg.startswith("!copyemote "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo propietario y administradores pueden copiar emotes!")
                return
            
            parts = msg.split()
            if len(parts) < 2:
                await send_response("❌ Usa: !copyemote @usuario o !copyemote [user_id]")
                return
            
            target_identifier = parts[1].replace("@", "")
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                return
            
            users = response.content
            # Buscar por username o user_id
            target_user = next((u for u, _ in users if u.username == target_identifier or u.id == target_identifier), None)
            
            if not target_user:
                await send_response(f"❌ Usuario/Bot {target_identifier} no encontrado en la sala!")
                return
            
            # Verificar si el usuario tiene un emote activo
            if target_user.id not in ACTIVE_EMOTES or ACTIVE_EMOTES[target_user.id] is None:
                await send_response(f"❌ {target_user.username} no está ejecutando ningún emote!")
                return
            
            emote_id = ACTIVE_EMOTES[target_user.id]
            emote_name = next((e["name"] for e in emotes.values() if e["id"] == emote_id), emote_id)
            
            # Guardar emote copiado con número incremental (SIN outfit)
            emote_number = len(self.copied_emotes) + 1
            self.copied_emotes[emote_number] = {
                "emote_id": emote_id,
                "name": emote_name,
                "from_user": target_user.username,
                "from_user_id": target_user.id
            }
            
            await send_response(f"✅ Emote '{emote_name}' copiado de @{target_user.username}\n📋 Guardado como #{emote_number}\n💡 Usa: !emotecopy {emote_number}")
            log_event("EMOTE", f"Emote '{emote_name}' copiado de {target_user.username} (ID: {target_user.id[:8]}...) como #{emote_number}")
            return

        # Comando !listemotes - listar emotes copiados
        if msg == "!listemotes":
            if not self.copied_emotes:
                await send_response("📋 No hay emotes copiados")
                return
            
            emote_list = "📋 EMOTES COPIADOS:\n"
            for num, data in self.copied_emotes.items():
                emote_list += f"#{num} - {data['name']} (de @{data['from_user']})\n"
            await send_response(emote_list)
            return

        # Comando !emote list
        if msg == "!emote list":
            total_emotes = len(emotes)
            free_emotes = sum(1 for e in emotes.values() if e["is_free"])
            emote_header = f"🎭 LISTA DE EMOTES ({total_emotes} total, {free_emotes} gratuitos):\n\n"
            
            # Mostrar en grupos de 10, ordenados numéricamente
            sorted_emote_items = sorted(emotes.items(), key=lambda x: int(x[0]))
            is_first_message = True
            
            for i in range(0, len(sorted_emote_items), 10):
                batch = sorted_emote_items[i:i+10]
                batch_text = ""
                for num, data in batch:
                    status = "✅" if data["is_free"] else "🔒"
                    batch_text += f"{status} #{num} - {data['name']}\n"
                
                # Incluir encabezado solo en el primer mensaje
                message = (emote_header + batch_text) if is_first_message else batch_text
                
                # REGLA DM: Usar send_response para asegurar que vaya por el canal correcto
                if is_dm or conversation_id:
                    await send_response(message)
                else:
                    await self.highrise.send_whisper(user_id, message)
                
                log_bot_response(f"@{username}: !emote list (batch {i//10 + 1})")
                is_first_message = False
                await asyncio.sleep(0.3)
            
            if is_dm or conversation_id:
                await send_response("💡 Usa: [número] o [nombre] para hacer un emote")
            else:
                await self.highrise.send_whisper(user_id, "💡 Usa: [número] o [nombre] para hacer un emote")
            return

        # Ejecución de emotes por número (Solo dígitos)
        if msg.isdigit():
            emote_number = msg
            emote = emotes.get(emote_number)
            if emote:
                # Verificar si el emote está deshabilitado
                if emote["id"] in DISABLED_EMOTE_IDS:
                    await self.highrise.send_whisper(user.id, "🚫 Emote deshabilitado")
                    return
                
                if emote["is_free"] or user_id == OWNER_ID:
                    try:
                        asyncio.create_task(self.send_emote_loop(user.id, emote["id"]))
                        await self.highrise.send_whisper(user.id, f"💡Bucle [{emote['name']}] emote.\nEscriba 'stop' - para cancelar🛑.")
                    except Exception as e:
                        await self.highrise.send_whisper(user.id, f"❌ Error al iniciar animación: {str(e)[:50]}")
                else:
                    await self.highrise.send_whisper(user.id, f"❌ El emote #{emote_number} no es gratuito.")
            else:
                await self.highrise.send_whisper(user.id, f"❌ El número #{emote_number} no existe. Usa !emote list.")
            return

        # Comando !custom [emote_id] - Ejecutar cualquier emote por ID
        if msg.startswith("!custom "):
            emote_id = msg[8:].strip()
            if not emote_id:
                await send_response("❌ Uso: !custom [emote_id]\n💡 Ejemplo: !custom emote-dance")
                return
            try:
                await self.highrise.send_emote(emote_id, user.id)
                await send_response(f"🎭 Emote personalizado '{emote_id}' ejecutado")
            except Exception as e:
                await send_response(f"❌ Error ejecutando emote: {emote_id}\n⚠️ Verifica que el ID sea correcto")
                log_event("ERROR", f"Error en !custom: {e}")
            return

        # Ejecución rápida de emotes sin !emote
        emote_found = False
        msg_parts = msg.split()
        potential_emote_name = msg_parts[0].lower() if msg_parts else ""
        
        # Verificar si es una estructura de comando de emote: emote @user o emote
        for e in emotes.values():
            if e["name"].lower() == potential_emote_name or e["id"].lower() == potential_emote_name:
                emote_found = True
                emote = e
                break
        
        if msg and not msg.startswith("!") and emote_found:
            target_user_ids = [user.id]
            is_vip = self.is_vip(user_id) or self.is_admin(user_id) or user_id == OWNER_ID
            
            # Caso: emote all
            if len(msg_parts) >= 2 and msg_parts[1].lower() == "all":
                if not (self.is_admin(user_id) or user_id == OWNER_ID):
                    await send_response("❌ ¡Solo Administradores y el Propietario pueden usar animaciones masivas!")
                    return
                
                response = await self.highrise.get_room_users()
                if not isinstance(response, Error):
                    # Filtrar bots y al bot mismo por ID
                    target_user_ids = [u.id for u, _ in response.content if u.id != BOT_ID and not any(name in u.username.lower() for name in ["bot", "glux", "highrise"])]
                    
                    if emote["is_free"] or user_id == OWNER_ID:
                        for target_id in target_user_ids:
                            asyncio.create_task(self.send_emote_loop(target_id, emote["id"]))
                        await send_response(f"📣 ¡ANIMACIÓN MASIVA! Todos haciendo: {emote['name']} 🌟")
                    else:
                        await send_response(f"❌ El emote '{emote['name']}' no es gratuito.")
                else:
                    await send_response("❌ Error obteniendo usuarios")
                return

            # Caso: emote @usuario
            if len(msg_parts) >= 2 and msg_parts[1].startswith("@"):
                target_username = msg_parts[1][1:]

                # Bloquear emotes dirigidos al bot (caso individual con @)
                response = await self.highrise.get_room_users()
                if not isinstance(response, Error):
                    target_user = next((u for u, _ in response.content if u.username.lower() == target_username.lower()), None)
                    
                    # Bloqueo por ID del bot
                    if target_user and target_user.id == BOT_ID:
                        await self.highrise.send_emote("emote-death", user.id)
                        responses = [
                            "💀 ¡Ni lo intentes @{user.username}! No soy tu marioneta.",
                            "👻 ¿Intentas bailar con un fantasma @{user.username}? ¡Buen intento!",
                            "⚰️ ¡Zzz... no estoy disponible para bailes @{user.username}!",
                            "🛡️ Mi sistema rechaza invitaciones de baile externas @{user.username}.",
                            "⚡ ¡Error @{user.username}! No tengo articulaciones para ese emote."
                        ]
                        await self.highrise.chat(random.choice(responses).format(user=user))
                        return

                if any(name in target_username.lower() for name in ["bot", "glux", "highrise"]):
                    await send_response("❌ No puedes usar animaciones en el bot.")
                    return
                if not is_vip:
                    await send_response("❌ ¡Solo usuarios VIP, Administradores y Propietario pueden usar animaciones en otros usuarios!")
                    return
                response = await self.highrise.get_room_users()
                if not isinstance(response, Error):
                    target_user = next((u for u, _ in response.content if u.username.lower() == target_username.lower()), None)
                    
                    # Bloqueo por ID del bot
                    if target_user and target_user.id == BOT_ID:
                        await self.highrise.send_emote("emote-death", user.id)
                        responses = [
                            "💀 ¡Ni lo intentes @{user.username}! No soy tu marioneta.",
                            "👻 ¿Intentas bailar con un fantasma @{user.username}? ¡Buen intento!",
                            "⚰️ ¡Zzz... no estoy disponible para bailes @{user.username}!",
                            "🛡️ Mi sistema rechaza invitaciones de baile externas @{user.username}.",
                            "⚡ ¡Error @{user.username}! No tengo articulaciones para ese emote."
                        ]
                        await self.highrise.chat(random.choice(responses).format(user=user))
                        return

                    if target_user:
                        # Emote DUO: El autor y el objetivo
                        target_user_ids = [user.id, target_user.id]
                    else:
                        await send_response(f"❌ Usuario @{target_username} no encontrado en la sala")
                        return
                else:
                    await send_response("❌ Error obteniendo usuarios")
                    return

            # Ejecutar el emote
            if emote["is_free"] or user_id == OWNER_ID:
                for target_id in target_user_ids:
                    asyncio.create_task(self.send_emote_loop(target_id, emote["id"]))
                
                if len(target_user_ids) > 1:
                    await send_response(f"🎭 ¡EMOTE DÚO! @{user.username} y @{target_username} haciendo: {emote['name']} ✨")
                else:
                    await self.highrise.send_whisper(user.id, f"💡Bucle [{emote['name']}] emote.\nEscriba 'stop' - para cancelar🛑.")
            else:
                if len(target_user_ids) > 1:
                    await send_response(f"❌ El emote '{emote['name']}' no es gratuito.")
                else:
                    await self.highrise.send_whisper(user.id, f"❌ El emote '{emote['name']}' no es gratuito.")
            return

        # Comando stop (incluyendo "alto" y "Alto")
        if msg.lower() in ["stop", "!stop", "0", "alto", "!alto"]:
            # Restricción: 'alto' solo para VIP+
            if msg.lower() in ["alto", "!alto"] and not (self.is_vip_by_username(username) or self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("🛑Acceso denegado.\nPermisos requeridos: “VIP”")
                return

            if user.id in ACTIVE_EMOTES:
                await self.stop_emote_loop(user.id)
                await send_response(f"🛑Bucle de emoticonos detenido.")
            else:
                await send_response(f"ℹ️ No estás ejecutando ningún emote en este momento.")
            return
        if msg.startswith("!stop "):
            stop_target = msg[6:].strip()
            if stop_target == "all":
                if not (self.is_admin(user_id) or user_id == OWNER_ID):
                    await send_response("❌ Acceso denegado.\nPermisos requeridos: “SISTEMA DIRECTIVO”")
                    return
                active_users = list(ACTIVE_EMOTES.keys())
                for active_user_id in active_users: await self.stop_emote_loop(active_user_id)
                await send_response( f"🛑 Detuviste todas las animaciones en la sala.")
                return
            elif stop_target.startswith("@"):
                # SOLO Administradores y Propietario pueden detener emotes de otros
                is_admin_or_owner = self.is_admin(user_id) or user_id == OWNER_ID
                
                if not is_admin_or_owner:
                    await send_response("❌ Acceso denegado.\nPermisos requeridos: “SISTEMA DIRECTIVO”")
                    return
                
                target_username = stop_target[1:]
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                target_user = next((u for u, _ in users if u.username == target_username), None)
                if not target_user: await send_response( f"❌ ¡Usuario {target_username} no encontrado!"); return
                await self.stop_emote_loop(target_user.id)
                await send_response( f"🛑 Detuviste la animación de @{target_username}")
                return
            return
        
        # EMOTES MUTUOS SIMPLIFICADOS - Sin "!" (VIP, Admin, Owner)
        # Formato: "ghostfloat @usuario" o "5 @usuario"
        parts_msg = msg.split()
        if len(parts_msg) >= 2 and parts_msg[1].startswith("@") and not msg.startswith("!"):
            emote_key = parts_msg[0]
            target_username = parts_msg[1].replace("@", "")

            # Bloquear emotes mutuos hacia el bot (para todos los usuarios)
            response = await self.highrise.get_room_users()
            if not isinstance(response, Error):
                target_user = next((u for u, _ in response.content if u.username.lower() == target_username.lower()), None)
                if target_user and target_user.id == "694c37fcb3a6081eecdd9d34":
                    await self.highrise.send_emote("emote-death", user.id)
                    responses = [
                        "💀 ¡Ni lo intentes @{user.username}! No soy tu marioneta.",
                        "👻 ¿Intentas bailar con un fantasma @{user.username}? ¡Buen intento!",
                        "⚰️ ¡Zzz... no estoy disponible para bailes @{user.username}!",
                        "🛡️ Mi sistema rechaza invitaciones de baile externas @{user.username}.",
                        "⚡ ¡Error @{user.username}! No tengo articulaciones para ese emote."
                    ]
                    await self.highrise.chat(random.choice(responses).format(user=user))
                    return

            if any(name in target_username.lower() for name in ["bot", "glux", "highrise"]):
                await send_response("❌ No puedes usar animaciones en el bot.")
                return
            if not (self.is_vip(user_id) or self.is_admin(user_id) or user_id == OWNER_ID):
                await self.highrise.send_whisper(user.id, "🛑Acceso denegado.\nPermisos requeridos: “VIP”")
                return
                
                emote_found = None
                if emote_key.isdigit():
                    emote_found = emotes.get(emote_key)
                else:
                    for e in emotes.values():
                        if e["name"].lower() == emote_key.lower() or e["id"].lower() == emote_key.lower():
                            emote_found = e
                            break
                
                if emote_found and emote_found["is_free"] and emote_found["id"] not in DISABLED_EMOTE_IDS:
                    response = await self.highrise.get_room_users()
                    if not isinstance(response, Error):
                        users = response.content
                        target_user = next((u for u, _ in users if u.username == target_username), None)
                        if target_user:
                            # Activar para el target
                            asyncio.create_task(self.send_emote_loop(target_user.id, emote_found["id"]))
                            # Activar para quien envió el comando
                            asyncio.create_task(self.send_emote_loop(user.id, emote_found["id"]))
                            
                            safe_print(f"🎭 {username} activó dúo '{emote_found['name']}' con {target_username}")
                            await send_response(f"🎭 ¡EMOTE DÚO! @{username} y @{target_username} haciendo: {emote_found['name']} ✨")
                            return
        
        # Comando !stopall
        if msg == "!stopall":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ Acceso denegado.\nPermisos requeridos: “SISTEMA DIRECTIVO”")
                return
            active_users = list(ACTIVE_EMOTES.keys())
            for active_user_id in active_users: await self.stop_emote_loop(active_user_id)
            await send_response( f"🛑 Detuviste todas las animaciones en la sala.")
            return

        # Comando !myid
        if msg == "!myid": await send_response( f"🆔 Tu ID de usuario es: {user_id}")

        # Comando !position (nuevo - muestra posición actual)
        if msg == "!position" or msg == "!pos":
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            user_position = next((pos for u, pos in users if u.id == user_id), None)
            if user_position:
                if isinstance(user_position, Position):
                    await send_response(f"📍 Tu posición:\nX: {user_position.x:.2f}\nY: {user_position.y:.2f}\nZ: {user_position.z:.2f}")
                elif isinstance(user_position, AnchorPosition):
                    if user_position.offset:
                        await send_response(f"📍 Tu posición:\nX: {user_position.offset.x:.2f}\nY: {user_position.offset.y:.2f}\nZ: {user_position.offset.z:.2f}")
                    else:
                        await send_response("❌ No se pudo obtener tu posición (sin offset)")
                else:
                    await send_response("❌ No se pudo obtener tu posición")
            else:
                await send_response("❌ No se pudo obtener tu posición")
            return

        # Comando !reactions (nuevo - lista de reacciones disponibles)
        if msg == "!reactions":
            reactions_list = "💫 REACCIONES DISPONIBLES:\n"
            reactions_list += "❤️ heart - Corazón\n"
            reactions_list += "👍 thumbs - Pulgar arriba\n"
            reactions_list += "👏 clap - Aplauso\n"
            reactions_list += "👋 wave - Saludo\n"
            reactions_list += "😂 laugh - Risa\n"
            reactions_list += "😮 wink - Guiño\n"
            reactions_list += "\n💡 Usa: !heart @user, !thumbs @user, etc."
            await send_response(reactions_list)
            return

        # Comando !leaderboard
        if msg.startswith("!leaderboard"):
            parts = msg.split()
            if len(parts) == 1: await send_response("🏆 !leaderboard heart\n!leaderboard active")
            elif len(parts) > 1:
                lb_type = parts[1].lower()
                if lb_type == "heart":
                    top = sorted(USER_HEARTS.items(), key=lambda x: x[1], reverse=True)[:10]
                    response = await self.highrise.get_room_users()
                    if isinstance(response, Error):
                        await send_response("❌ Error obteniendo usuarios")
                        log_event("ERROR", f"get_room_users failed: {response.message}")
                        return
                    id_to_name = {u.id: u.username for u, _ in response.content}
                    lines = ["❤️ Top por corazones:"]
                    count = 0
                    for i, (uid, count_val) in enumerate(top, 1):
                        uname = id_to_name.get(uid) or USER_NAMES.get(uid) or f"User_{uid[:8]}"
                        lines.append(f"{i}. {uname}: {count_val}")
                        count += 1
                    if count == 0: lines.append("Sin datos")
                    await send_response("\n".join(lines))
                elif lb_type == "active":
                    top = sorted(USER_ACTIVITY.items(), key=lambda x: x[1]["messages"], reverse=True)[:10]
                    response = await self.highrise.get_room_users()
                    if isinstance(response, Error):
                        await send_response("❌ Error obteniendo usuarios")
                        log_event("ERROR", f"get_room_users failed: {response.message}")
                        return
                    id_to_name = {u.id: u.username for u, _ in response.content}
                    lines = ["💬 Top por actividad:"]
                    count = 0
                    for i, (uid, data) in enumerate(top, 1):
                        uname = id_to_name.get(uid) or USER_NAMES.get(uid) or f"User_{uid[:8]}"
                        lines.append(f"{i}. {uname}: {data['messages']}")
                        count += 1
                    if count == 0: lines.append("Sin datos")
                    await send_response("\n".join(lines))
            return

        # Comando !trackme
        if msg == "!trackme": await send_response("Activaste seguimiento de actividad!")

        # Comando !heartall (Owner/Admin/Moderador)
        if msg == "!heartall":
            if not (user_id == OWNER_ID or self.is_admin(user_id) or self.is_moderator(user_id)):
                await send_response("🛑Acceso denegado.\nPermisos requeridos: Propietario, Admin o Moderador")
                return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            heart_count = 0
            for u, _ in users:
                if not any(name in u.username.lower() for name in ["bot", "glux", "highrise"]):
                    self.add_user_hearts(u.id, 1, u.username)
                    await self.highrise.react("heart", u.id)
                    # Formato: @NOCTURNO_BOT le ha dado 1 -->❤️ a @USUARIO
                    heart_count += 1
                    await asyncio.sleep(0.05)
            await send_response(f"💖 Se enviaron ❤️ a {heart_count} usuarios")
            safe_print(f"💖 Bot envió corazones a {heart_count} usuarios")

        # Comando !heart
        if msg.startswith("!heart"):
            parts = msg.split()
            if len(parts) >= 2:
                target_username = parts[1].replace("@", "")
                hearts_count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                target_user_obj = next((u for u, _ in users if u.username == target_username), None)
                if not target_user_obj: await send_response( f"❌ ¡Usuario {target_username} no encontrado!"); return

                is_admin_or_owner = self.is_admin(user_id) or user_id == OWNER_ID
                is_vip = self.is_vip_by_username(user.username)

                if is_admin_or_owner:
                    if hearts_count > 100: await send_response("❌ ¡Máximo 100 corazones por comando!"); return
                    self.add_user_hearts(target_user_obj.id, hearts_count, target_username)
                    for _ in range(hearts_count):
                        await self.highrise.react("heart", target_user_obj.id)
                        await asyncio.sleep(0.05)
                    await send_response(f"@{username} le ha dado {hearts_count} -->❤️ a @{target_username}")
                elif is_vip:
                    if hearts_count > 5:
                        await send_response("❌ ¡Los VIP pueden enviar máximo 5 corazones por comando!")
                        return
                    self.add_user_hearts(target_user_obj.id, hearts_count, target_username)
                    for _ in range(hearts_count):
                        await self.highrise.react("heart", target_user_obj.id)
                        await asyncio.sleep(0.05)
                    await send_response(f"@{username} le ha dado {hearts_count} -->❤️ a @{target_username}")
                else:
                    await send_response("🛑Acceso denegado.\nPermisos requeridos: “VIP”")
            else:
                await send_response( "❌ Usa: !heart @username [cantidad]")
            return

        # Comando !thumbs
        if msg.startswith("!thumbs"):
            parts = msg.split()
            if len(parts) >= 2:
                target = parts[1].replace("@", "")
                thumbs_count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                
                if target.lower() == "all":
                    count = 0
                    for u, _ in users:
                        if not any(name in u.username.lower() for name in ["bot", "glux", "highrise"]):
                            await self.highrise.react("thumbs", u.id)
                            count += 1
                            await asyncio.sleep(0.1)
                    await send_response(f"👍 Enviaste pulgar arriba a todos los {count} usuarios!")
                else:
                    target_user = next((u for u, _ in users if u.username == target), None)
                    if not target_user: await send_response( f"❌ Usuario {target} no encontrado!"); return
                    for _ in range(min(thumbs_count, 30)):
                        await self.highrise.react("thumbs", target_user.id)
                        await asyncio.sleep(0.05)
                    await send_response( f"👍 Enviaste {thumbs_count} pulgar(es) arriba a @{target}")
            else:
                await send_response( "❌ Usa: !thumbs @username [cantidad] o !thumbs all")
            return

        # Comando !clap
        if msg.startswith("!clap"):
            parts = msg.split()
            if len(parts) >= 2:
                target = parts[1].replace("@", "")
                clap_count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                
                if target.lower() == "all":
                    count = 0
                    for u, _ in users:
                        if not any(name in u.username.lower() for name in ["bot", "glux", "highrise"]):
                            await self.highrise.react("clap", u.id)
                            count += 1
                            await asyncio.sleep(0.1)
                    await send_response(f"👏 Enviaste aplauso a todos los {count} usuarios!")
                else:
                    target_user = next((u for u, _ in users if u.username == target), None)
                    if not target_user: await send_response( f"❌ Usuario {target} no encontrado!"); return
                    for _ in range(min(clap_count, 30)):
                        await self.highrise.react("clap", target_user.id)
                        await asyncio.sleep(0.05)
                    await send_response( f"👏 Enviaste {clap_count} aplauso(s) a @{target}")
            else:
                await send_response( "❌ Usa: !clap @username [cantidad] o !clap all")
            return

        # Comando !wave
        if msg.startswith("!wave"):
            parts = msg.split()
            if len(parts) >= 2:
                target = parts[1].replace("@", "")
                wave_count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                
                if target.lower() == "all":
                    count = 0
                    for u, _ in users:
                        if not any(name in u.username.lower() for name in ["bot", "glux", "highrise"]):
                            await self.highrise.react("wave", u.id)
                            count += 1
                            await asyncio.sleep(0.1)
                    await send_response(f"👋 Enviaste ola a todos los {count} usuarios!")
                else:
                    target_user = next((u for u, _ in users if u.username == target), None)
                    if not target_user: await send_response( f"❌ Usuario {target} no encontrado!"); return
                    for _ in range(min(wave_count, 30)):
                        await self.highrise.react("wave", target_user.id)
                        await asyncio.sleep(0.05)
                    await send_response( f"👋 Enviaste {wave_count} ola(s) a @{target}")
            else:
                await send_response( "❌ Usa: !wave @username [cantidad] o !wave all")
            return

        # Comando !anchor (nuevo - teleporte sin restricciones para admin/owner)
        if msg.startswith("!anchor "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar este comando!")
                return
            parts = msg.split()
            if len(parts) >= 4:
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    pos = Position(x, y, z)
                    await self.highrise.teleport(user_id, pos)
                    await send_response(f"⚓ Anclado a posición ({x}, {y}, {z})")
                except ValueError:
                    await send_response("❌ Usa: !anchor [x] [y] [z]")
            else:
                await send_response("❌ Usa: !anchor [x] [y] [z]")
            return

        # Comando !flash
        if msg.startswith("!flash"):
            parts = msg.split()
            if len(parts) >= 4:
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    response = await self.highrise.get_room_users()
                    if isinstance(response, Error):
                        await send_response("❌ Error obteniendo usuarios")
                        log_event("ERROR", f"get_room_users failed: {response.message}")
                        return
                    users = response.content
                    current_position = next((pos for u, pos in users if u.id == user.id), None)
                    if current_position:
                        current_y = current_position.y if isinstance(current_position, Position) else (current_position.offset.y if current_position.offset else 0)
                        current_x = current_position.x if isinstance(current_position, Position) else (current_position.offset.x if current_position.offset else 0)
                        current_z = current_position.z if isinstance(current_position, Position) else (current_position.offset.z if current_position.offset else 0)
                        if abs(current_y - y) < 1.0: await send_response("❌ ¡Flash solo para subir/bajar pisos!"); return
                        if abs(current_x - x) > 3.0 or abs(current_z - z) > 3.0: await send_response("❌ ¡Flash solo para subir/bajar pisos!"); return
                        if not self.is_in_forbidden_zone(x, y, z, user.id):
                            pos = Position(x, y, z)
                            await self.highrise.teleport(user.id, pos)
                            await send_response( f"⚡ Flasheaste entre pisos ({x}, {y}, {z})")
                        else:
                            await send_response( f"❌ ¡No puedes teletransportarte a una zona prohibida!")
                    else:
                        await send_response( "❌ Error obteniendo tu posición actual")
                except ValueError:
                    await send_response( "❌ Usa: !flash [x] [y] [z] (ejemplo: !flash 5 17 3)")
            else:
                await send_response( "❌ Usa: !flash [x] [y] [z] (ejemplo: !flash 5 17 3)")
            return

        # Comando !inventory
        if msg.startswith("!inventory"):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("🛑Acceso denegado.\nPermisos requeridos: “VIP”")
                return
            parts = msg.split()
            if len(parts) == 2 and parts[1].startswith("@"):
                target_username = parts[1].replace("@", "")
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                target_user = next((u for u, _ in users if u.username == target_username), None)
                if not target_user: await send_response( f"❌ Usuario {target_username} no encontrado!"); return
                inv_response = await self.highrise.get_user_outfit(target_user.id)
                if isinstance(inv_response, Error):
                    await send_response( f"❌ Error obteniendo outfit de {target_username}")
                    log_event("ERROR", f"get_user_outfit failed: {inv_response.message}")
                    return
                outfit = inv_response.outfit
                if outfit:
                    await send_response( f"👔 OUTFIT de {target_username}:")
                    for i, item in enumerate(outfit, 1): await send_response( f"{i}. {item.type}: {item.id}"); await asyncio.sleep(0.2)
                else: await send_response( f"👔 {target_username} no tiene outfit equipado")
            else:
                inventory_response = await self.highrise.get_inventory()
                if isinstance(inventory_response, Error):
                    await send_response( f"❌ Error obteniendo inventario")
                    log_event("ERROR", f"get_inventory failed: {inventory_response.message}")
                    return
                inventory = inventory_response.items
                if inventory:
                    total_items = len(inventory)
                    await send_response( f"👔 INVENTARIO: {total_items} items")
                    for i, item in enumerate(inventory, 1): await send_response( f"{i}. {item.type}: {item.id}"); await asyncio.sleep(0.2)
                else: await send_response("📦 Inventario vacío")
            return

        # Comando !give
        if msg.startswith("!give "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar este comando!")
                return
            parts = msg.split()
            if len(parts) >= 3:
                target_username = parts[1].replace("@", "")
                item_id = " ".join(parts[2:])
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                target_user = next((u for u, _ in users if u.username == target_username), None)
                if not target_user: await send_response( f"❌ Usuario {target_username} no encontrado!"); return
                await send_response( f"⚠️ Comando !give deshabilitado (set_inventory no disponible)")
            else: await send_response("❌ Usa: !give @user [item_id]")
            return

        # Comando !wallet (Owner/Admin)
        if msg == "!wallet":
            if not (user_id == OWNER_ID or self.is_admin(user_id)):
                await send_response("❌ ¡Solo el propietario y administradores pueden ver el balance del bot!")
                return
            balance = await self.get_bot_wallet_balance()
            await self.highrise.chat(f"💰 Balance del bot: {balance} oro")
            return

        # Comando !restart (Owner)
        if msg.startswith("!restart"):
            if user_id != OWNER_ID:
                await send_response("❌ ¡Solo el propietario puede reiniciar el bot!")
                return
            await send_response("🔄 Reiniciando bot..."); await send_response("⚠️ El bot se detendrá en 3 segundos!"); await send_response("💡 Usa restart_bot.bat para reinicio automático!")
            asyncio.create_task(self.delayed_restart())
            return

        # Comando !say (Admin/Owner)
        if msg.startswith("!say "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo propietario y administradores pueden usar este comando!")
                return
            message_to_send = msg[5:].strip()
            if message_to_send:
                await self.highrise.chat(message_to_send)
                await send_response( f"✅ Mensaje enviado: {message_to_send}")
            else: await send_response("❌ Usa: !say [mensaje]")
            return

        # Comando !tome (Owner/Admin)
        if msg == "!tome":
            if not (user_id == OWNER_ID or self.is_admin(user_id)):
                await send_response("❌ ¡Solo el propietario y administradores pueden usar este comando!")
                return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            bot_user, bot_pos, user_pos = None, None, None
            for u, pos in users:
                if hasattr(self, 'bot_id') and u.id == self.bot_id: bot_user, bot_pos = u, pos
                if u.id == user_id: user_pos = pos
            if bot_user and user_pos:
                if isinstance(user_pos, Position):
                    target_pos = Position(user_pos.x + 1.0, user_pos.y, user_pos.z)
                elif isinstance(user_pos, AnchorPosition) and user_pos.offset:
                    target_pos = Position(user_pos.offset.x + 1.0, user_pos.offset.y, user_pos.offset.z)
                else:
                    await send_response("❌ No se pudo obtener tu posición!")
                    return
                await self.highrise.teleport(bot_user.id, target_pos)
                await send_response( f"🤖 Bot teletransportado a @{user.username}")
            elif not bot_user: await send_response("❌ ¡Bot no encontrado en la sala!")
            else: await send_response("❌ No se pudo obtener tu posición!")
            return

        # Comando !outfit
        if msg.startswith("!outfit"):
            if not (self.is_admin(user_id) or self.is_moderator(user_id) or user_id == OWNER_ID):
                await send_response("🛑Acceso denegado.\nPermisos requeridos: Propietario, Admin o Moderador")
                return
            parts = msg.split()
            if len(parts) >= 2:
                try:
                    outfit_number = int(parts[1])
                    if outfit_number in SAVED_OUTFITS:
                        await self.highrise.set_outfit(SAVED_OUTFITS[outfit_number])
                        await send_response( f"👕 Outfit #{outfit_number} aplicado")
                    else: await send_response( f"❌ Outfit #{outfit_number} no existe.")
                except ValueError: await send_response("❌ Usa: !outfit [número]")
                except Exception as e: await send_response( f"❌ Error de cambio de ropa: {e}")
            else:
                if SAVED_OUTFITS:
                    outfits_list = ", ".join([f"#{num}" for num in sorted(SAVED_OUTFITS.keys())])
                    await send_response( f"👔 Outfits guardados: {outfits_list}\n❌ Usa: !outfit [número]")
                else: await send_response("📦 No hay outfits guardados.")
            return

        # Comando !automode (Admin/Owner)
        if msg == "!automode":
            if not (user_id == OWNER_ID or self.is_admin(user_id)):
                await send_response("❌ ¡Solo administradores y propietario pueden usar este comando!")
                return
            try:
                # Detener floss si está activo
                if self.floss_loop_active:
                    self.floss_loop_active = False
                    self.bot_mode = "idle"
                    if self.floss_task and not self.floss_task.done():
                        self.floss_task.cancel()
                    await asyncio.sleep(0.5)
                
                # Detener cualquier tarea activa
                if self.current_emote_task and not self.current_emote_task.done(): 
                    self.current_emote_task.cancel()
                    await asyncio.sleep(0.5)
                
                # Desactivar modo de emote copiado
                self.copied_emote_mode = False
                self.current_copied_emote = None
                
                # Iniciar ciclo automático
                self.current_emote_task = asyncio.create_task(self.start_auto_emote_cycle())
                await send_response("🎭 ¡Modo AUTOMÁTICO activado!\n📊 Ejecutando 224 emotes en ciclo")
                await self.highrise.chat("🎭 Modo AUTOMÁTICO activado por admin")
                log_event("BOT", f"Modo automático activado por {user.username}")
            except Exception as e:
                await send_response( f"❌ Error activando modo automático: {e}")
            return

        # Comando !mimic (Admin/Owner)
        if msg.startswith("!mimic "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar este comando!")
                return
            target_username = msg[7:].strip().replace("@", "")
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            if not target_user: await send_response( f"❌ Usuario {target_username} no encontrado"); return
            target_outfit_response = await self.highrise.get_user_outfit(target_user.id)
            if isinstance(target_outfit_response, Error):
                await send_response(f"❌ Error obteniendo outfit de {target_username}")
                log_event("ERROR", f"get_user_outfit failed: {target_outfit_response.message}")
                return
            await self.highrise.set_outfit(target_outfit_response.outfit)
            target_position = next((pos for u, pos in users if u.id == target_user.id), None)
            if target_position:
                if isinstance(target_position, Position):
                    mimic_position = Position(target_position.x + 0.5, target_position.y, target_position.z + 0.5)
                elif isinstance(target_position, AnchorPosition) and target_position.offset:
                    mimic_position = Position(target_position.offset.x + 0.5, target_position.offset.y, target_position.offset.z + 0.5)
                else:
                    await send_response("❌ No se pudo obtener la posición")
                    return
                await self.highrise.teleport(self.bot_id, mimic_position)
            await send_response( f"🎭 Bot imitando a @{target_username}"); await self.highrise.chat(f"🎭 ¡Soy @{target_username}!")
            return

        # Comando !copyoutfit (Admin/Owner)
        if msg == "!copyoutfit":
            if not (user_id == OWNER_ID or self.is_admin(user_id)):
                await send_response("❌¡Solo el propietario y administradores pueden copiar el outfit del bot!")
                return
            user_outfit_response = await self.highrise.get_user_outfit(user.id)
            if isinstance(user_outfit_response, Error):
                await send_response("❌ Error obteniendo outfit")
                log_event("ERROR", f"get_user_outfit failed: {user_outfit_response.message}")
                return
            
            # Verificar si el bot puede usar la ropa
            try:
                # Intentar aplicar el outfit para verificar validez
                # (set_outfit lanzará una excepción si hay items que el bot no posee o no puede usar)
                await self.highrise.set_outfit(user_outfit_response.outfit)
                await send_response("✅ ¡Outfit aplicado correctamente! Puedo usar esta ropa.")
            except Exception as e:
                await send_response(f"❌ No puedo usar esta ropa completa: {e}")
                log_event("WARNING", f"Bot cannot use full outfit: {e}")
                return
            
            # Guardar en SAVED_OUTFITS y persistir
            outfit_number = len(SAVED_OUTFITS) + 1
            SAVED_OUTFITS[outfit_number] = user_outfit_response.outfit
            
            # Guardar a archivo JSON
            try:
                import os
                os.makedirs("data", exist_ok=True)
                import json
                outfits_data = {}
                for num, outfit in SAVED_OUTFITS.items():
                    outfits_data[num] = [{"type": item.type, "id": item.id, "amount": item.amount} for item in outfit]
                
                with open("data/saved_outfits.json", "w", encoding="utf-8") as f:
                    json.dump(outfits_data, f, indent=2, ensure_ascii=False)
                
                safe_print(f"✅ Outfit #{outfit_number} guardado en archivo")
                log_event("OUTFIT", f"Outfit #{outfit_number} guardado por {username}")
            except Exception as e:
                safe_print(f"❌ Error guardando outfit a archivo: {e}")
                log_event("ERROR", f"Error guardando outfit: {e}")
            
            await send_response(f"👔 Outfit copiado y guardado como #{outfit_number}")
            return

        # Comando !setdirectivo (Owner)
        if msg == "!setdirectivo":
            if user_id != OWNER_ID:
                await send_response("❌ ¡Solo el propietario puede establecer la zona directiva!")
                return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            user_position = next((pos for u, pos in users if u.id == user_id), None)
            if user_position:
                if isinstance(user_position, Position):
                    new_directivo_zone = {"x": user_position.x, "y": user_position.y, "z": user_position.z}
                elif isinstance(user_position, AnchorPosition) and user_position.offset:
                    new_directivo_zone = {"x": user_position.offset.x, "y": user_position.offset.y, "z": user_position.offset.z}
                else:
                    await send_response("¡Error obteniendo posición del usuario!")
                    return
                # Cargar config actual
                config = load_config()
                config["directivo_zone"] = new_directivo_zone
                # Guardar a archivo
                with open("config.json", "w", encoding="utf-8") as f: 
                    json.dump(config, f, indent=2, ensure_ascii=False)
                # Actualizar variable global
                global DIRECTIVO_ZONE
                DIRECTIVO_ZONE = new_directivo_zone
                await send_response( f"👑 Zona directiva establecida en: X={new_directivo_zone['x']}, Y={new_directivo_zone['y']}, Z={new_directivo_zone['z']}")
                log_event("CONFIG", f"Zona directiva actualizada: {new_directivo_zone}")
            else: await send_response("¡Error obteniendo posición del usuario!")
            return

        # Comando !tip
        if msg.startswith("!tip"):
            if not (self.is_admin(user_id) or self.is_moderator(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar el comando !tip!")
                return
            parts = msg.split()
            if len(parts) >= 3:
                tip_type = parts[1]
                try:
                    amount = int(parts[2])
                except ValueError: await send_response("❌ ¡Cantidad de oro inválida!"); return

                if tip_type == "all" and 1 <= amount <= 5:
                    try:
                        response = await self.highrise.get_room_users()
                        if isinstance(response, Error):
                            await send_response("❌ Error obteniendo usuarios")
                            log_event("ERROR", f"get_room_users failed: {response.message}")
                            return
                        users = response.content
                        bot_user = next((u for u, _ in users if u.username == "NOCTURNO_BOT" or u.username.upper() == "NOCTURNO_BOT" or u.username.lower() in ["highrisebot", "gluxbot", "bot"] or any(name in u.username.lower() for name in ["nocturno", "bot", "glux", "highrise"])), None)
                        available_users = [u for u, _ in users if bot_user and u.id != bot_user.id]
                        user_count = len(available_users)
                        total_cost = user_count * amount
                        real_balance = await self.get_bot_wallet_balance()
                        if total_cost > real_balance: await send_response( f"❌ ¡Oro insuficiente! Necesario: {total_cost}, disponible: {real_balance}"); return

                        valid_tips = ["gold_bar_1", "gold_bar_5", "gold_bar_10", "gold_bar_50", "gold_bar_100", "gold_bar_500", "gold_bar_1k", "gold_bar_5000", "gold_bar_10k"]
                        for u in available_users:
                            tip_bars = self.convert_to_gold_bars(amount)
                            if tip_bars and tip_bars in valid_tips:
                                await self.highrise.tip_user(u.id, tip_bars)
                                await self.highrise.chat(f"💰 ¡Propinó a @{u.username} {amount} de oro!")
                    except Exception as e: await send_response( f"❌ Error dando oro: {e}")

                elif tip_type == "only" and amount > 0:
                    try:
                        response = await self.highrise.get_room_users()
                        if isinstance(response, Error):
                            await send_response("❌ Error obteniendo usuarios")
                            log_event("ERROR", f"get_room_users failed: {response.message}")
                            return
                        users = response.content
                        bot_user = next((u for u, _ in users if u.username == "NOCTURNO_BOT" or u.username.upper() == "NOCTURNO_BOT" or u.username.lower() in ["highrisebot", "gluxbot", "bot"] or any(name in u.username.lower() for name in ["nocturno", "bot", "glux", "highrise"])), None)
                        available_users = [u for u, _ in users if bot_user and u.id != bot_user.id]
                        num_users = min(amount, len(available_users))
                        selected_users = random.sample(available_users, num_users)
                        total_cost = num_users * 5
                        real_balance = await self.get_bot_wallet_balance()
                        if total_cost > real_balance: await send_response( f"❌ ¡Oro insuficiente! Necesario: {total_cost}, disponible: {real_balance}"); return
                        valid_tips = ["gold_bar_1", "gold_bar_5", "gold_bar_10", "gold_bar_50", "gold_bar_100", "gold_bar_500", "gold_bar_1k", "gold_bar_5000", "gold_bar_10k"]
                        for u in selected_users:
                            tip_bars = self.convert_to_gold_bars(5)
                            if tip_bars and tip_bars in valid_tips:
                                await self.highrise.tip_user(u.id, tip_bars)
                                await self.highrise.chat(f"💰 ¡Propinó a @{u.username} 5 de oro!")
                    except Exception as e: await send_response( f"❌ Error al dar oro: {e}")
                else: await send_response("❌ ¡Formato de comando inválido! Usa: !tip all [1-5] o !tip only [X]")
            else: await send_response("❌ ¡Formato de comando inválido! Usa: !tip all [1-5] o !tip only [X]")
            return

        # Comando !kick @usuario [razón]
        if msg.startswith("!kick "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ Solo administradores y propietario pueden expulsar usuarios.")
                return
            parts = msg.split()
            if len(parts) >= 2:
                target_username = parts[1].replace("@", "")
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                target_user = next((u for u, _ in users if u.username == target_username), None)
                if not target_user: await send_response( f"❌ Usuario {target_username} no encontrado en la sala!"); return
                await self.highrise.moderate_room(target_user.id, "kick")
                await send_response( f"👢 Expulsaste a {target_username} de la sala")
            else: await send_response("❌ Usa: !kick @username")
            return

        # Comando !ban @usuario [razón]
        if msg.startswith("!ban "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ Solo administradores y propietario pueden banear usuarios.")
                return
            parts = msg.split()
            if len(parts) >= 2:
                target_username = parts[1].replace("@", "")
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                target_user = next((u for u, _ in users if u.username == target_username), None)
                if not target_user: await send_response( f"❌ Usuario {target_username} no encontrado en la sala!"); return
                await self.highrise.moderate_room(target_user.id, "ban", 86400)
                await send_response( f"🚫 Baneaste a {target_username} por 1 día")
            else: await send_response("❌ Usa: !ban @username")
            return

        

        # Comando !givevip (Admin/Owner)
        if msg.startswith("!givevip"):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden dar VIP!")
                return
            target_user = msg[8:].strip().replace("@", "")
            if target_user not in VIP_USERS:
                VIP_USERS.add(target_user)
                self.save_data()
                await send_response( f"🎉 Otorgaste estatus VIP a {target_user}!")
                response = await self.highrise.get_room_users()
                if not isinstance(response, Error):
                    target_user_id = next((u.id for u, _ in response.content if u.username == target_user), None)
                    if target_user_id: await self.highrise.send_whisper(target_user_id, f"🎉 ¡Felicitaciones! Ahora eres VIP gracias a @{user.username}")
            else: await send_response( f"¡Usuario {target_user} ya tiene estatus VIP!")
            return

        # Comando !unvip (Admin/Owner)
        if msg.startswith("!unvip"):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden quitar VIP!")
                return
            target_user = msg[6:].strip().replace("@", "")
            if target_user in VIP_USERS:
                VIP_USERS.remove(target_user)
                self.save_data()
                await send_response( f"❌ Removiste estatus VIP de {target_user}!")
            else: await send_response( f"¡Usuario {target_user} no tiene estatus VIP!")
            return

        # Comando !freeze (Admin/Owner)
        if msg.startswith("!freeze"):
            if not (self.is_admin(user_id) or user_id == OWNER_ID): await send_response("❌ ¡Solo administradores y propietario pueden usar freeze!"); return
            target_username = msg[7:].strip().replace("@", "")
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            if not target_user: await send_response( f"❌ Usuario {target_username} no encontrado en la sala!"); return
            await self.highrise.moderate_room(target_user.id, "mute", 300)
            await send_response( f"🧊 Congelaste a {target_username} por 5 minutos")
            return

        # Comando !mute
        if msg.startswith("!mute"):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar mute!")
                return
            parts = msg.split()
            if len(parts) >= 2:
                target_username = parts[1].replace("@", "")
                duration = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 60
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                target_user = next((u for u, _ in users if u.username == target_username), None)
                if not target_user: await send_response( f"❌ Usuario {target_username} no encontrado!"); return
                await self.highrise.moderate_room(target_user.id, "mute", duration)
                await send_response( f"🔇 Silenciaste a {target_username} por {duration} segundos")
            else: await send_response("❌ Usa: !mute @username [segundos]")
            return

        # Comando !unmute
        if msg.startswith("!unmute"):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar unmute!")
                return
            target_username = msg[7:].strip().replace("@", "")
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            if not target_user: await send_response( f"❌ Usuario {target_username} no encontrado!"); return
            await self.highrise.moderate_room(target_user.id, "mute", 0)
            await send_response( f"🔊 Quitaste el silencio a {target_username}")
            return

        # Comando !jail - Enviar usuario a la cárcel (Admin/Owner)
        if msg.startswith("!jail "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden enviar a la cárcel!")
                return
            
            target_username = msg[6:].strip().replace("@", "")
            
            # Buscar al usuario
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            
            if not target_user:
                await send_response(f"❌ Usuario {target_username} no encontrado en la sala!")
                return
            
            # Crear zona cárcel automáticamente si no existe (muy alto, Y=100.0)
            if "carcel" not in TELEPORT_POINTS:
                # Posición muy alta fuera de la sala normal
                TELEPORT_POINTS["carcel"] = {"x": 0.0, "y": 100.0, "z": 0.0}
                self.save_data()
                safe_print(f"🔒 Zona cárcel creada automáticamente en Y=100.0")
                log_event("JAIL", "Zona cárcel creada automáticamente en altura Y=100.0")
            
            # Agregar al usuario a la lista de cárcel
            JAIL_USERS.add(target_user.id)
            
            # Teletransportar a la cárcel (altura muy elevada)
            point = TELEPORT_POINTS["carcel"]
            try:
                carcel_position = Position(point["x"], point["y"], point["z"])
                await self.highrise.teleport(target_user.id, carcel_position)
                await send_response(f"⛓️ {target_username} fue enviado a la cárcel en altura Y={point['y']}!")
                await self.highrise.send_whisper(target_user.id, f"⛓️ Fuiste enviado a la cárcel por @{username}.\n⚠️ No puedes escapar hasta que un admin te libere.")
                await self.highrise.chat(f"🚨 @{target_username} fue enviado a la cárcel por @{username}")
                log_event("JAIL", f"{username} envió a {target_username} a la cárcel (Y={point['y']})")
            except Exception as e:
                await send_response(f"❌ Error enviando a la cárcel: {e}")
                JAIL_USERS.discard(target_user.id)
            return

        # Comando !unjail - Liberar usuario de la cárcel (Admin/Owner)
        if msg.startswith("!unjail "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden liberar de la cárcel!")
                return
            
            target_username = msg[8:].strip().replace("@", "")
            
            # Buscar al usuario
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                return
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            
            if not target_user:
                await send_response(f"❌ Usuario {target_username} no encontrado en la sala!")
                return
            
            if target_user.id in JAIL_USERS:
                JAIL_USERS.discard(target_user.id)
                
                # Teletransportar a un punto seguro (entrada de la sala)
                try:
                    # Usar spawn point si existe, sino posición por defecto
                    spawn = config.get("spawn_point", {"x": 0.0, "y": 0.0, "z": 0.0})
                    spawn_position = Position(spawn["x"], spawn["y"], spawn["z"])
                    await self.highrise.teleport(target_user.id, spawn_position)
                except Exception as e:
                    safe_print(f"⚠️ Error teletransportando a spawn: {e}")
                
                await send_response(f"✅ {target_username} fue liberado de la cárcel!")
                await self.highrise.send_whisper(target_user.id, f"✅ Fuiste liberado de la cárcel por @{username}!")
                await self.highrise.chat(f"🔓 @{target_username} fue liberado de la cárcel por @{username}")
                log_event("JAIL", f"{username} liberó a {target_username} de la cárcel")
            else:
                await send_response(f"ℹ️ {target_username} no está en la cárcel")
            return

        # Comando !unban
        if msg.startswith("!unban"):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar este comando!")
                return
            target_username = msg[6:].strip().replace("@", "")
            target_id = next((uid for uid, uname in USER_NAMES.items() if uname == target_username), None)
            if target_id and target_id in BANNED_USERS:
                del BANNED_USERS[target_id]
                await send_response( f"✅ Desbaneaste a {target_username}")
            else: await send_response( f"❌ {target_username} no está baneado")
            return

        # Comando !banlist
        if msg == "!banlist":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden ver la lista de baneados!")
                return
            if BANNED_USERS:
                ban_list = "🚫 USUARIOS BANEADOS:\n"
                for i, (uid, ban_data) in enumerate(BANNED_USERS.items(), 1):
                    username = USER_NAMES.get(uid, f"User_{uid[:8]}")
                    ban_time = ban_data.get("time", "indefinido")
                    ban_list += f"{i}. {username} (hasta {ban_time})\n"
                await send_response(ban_list)
            else:
                await send_response("✅ No hay usuarios baneados")
            return

        # Sistema de emotes mutuos (VIP) - formato: (emote) @user
        if msg.startswith("(") and ")" in msg and "@" in msg:
            # Verificar que sea VIP o superior
            is_vip = self.is_vip_by_username(username)
            is_admin_or_owner = self.is_admin(user_id) or user_id == OWNER_ID
            
            if not (is_vip or is_admin_or_owner):
                await send_response("🔒 Solo usuarios VIP pueden usar emotes mutuos!")
                return
            
            try:
                # Extraer emote y usuario
                emote_part = msg[msg.index("(")+1:msg.index(")")]
                target_username = msg[msg.index("@")+1:].strip().split()[0]
                
                # Buscar el emote
                emote = None
                emote_key = emote_part.strip().lower()
                
                if emote_key.isdigit() and emote_key in emotes:
                    emote = emotes[emote_key]
                else:
                    for e in emotes.values():
                        if e["name"].lower() == emote_key or e["id"].lower() == emote_key:
                            emote = e
                            break
                
                if not emote:
                    await send_response(f"❌ Emote '{emote_part}' no encontrado. Usa !emote list")
                    return
                
                if not emote["is_free"]:
                    await send_response(f"❌ El emote '{emote['name']}' no es gratuito")
                    return
                
                # Verificar si el emote está deshabilitado
                if emote["id"] in DISABLED_EMOTE_IDS:
                    await send_response("🚫 Emote deshabilitado")
                    return
                
                # Buscar usuario objetivo
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    return
                
                users = response.content
                target_user = next((u for u, _ in users if u.username == target_username), None)
                
                if not target_user:
                    await send_response(f"❌ Usuario {target_username} no encontrado")
                    return
                
                # Ejecutar emote en ambos usuarios
                await self.highrise.send_emote(emote["id"], user.id)
                await self.highrise.send_emote(emote["id"], target_user.id)
                
                await send_response(f"🎭 Emote mutuo '{emote['name']}' entre @{username} y @{target_username}")
                
            except Exception as e:
                await send_response(f"❌ Error: Usa el formato: (nombre_emote) @usuario")
                log_event("ERROR", f"Error en emote mutuo: {e}")
            return

        # Comando !mutelist
        if msg == "!mutelist":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden ver la lista de silenciados!")
                return
            if MUTED_USERS:
                mute_list = "🔇 USUARIOS SILENCIADOS:\n"
                for i, (uid, mute_time) in enumerate(MUTED_USERS.items(), 1):
                    username = USER_NAMES.get(uid, f"User_{uid[:8]}")
                    mute_list += f"{i}. {username} (hasta {mute_time})\n"
                await send_response( mute_list)
            else: await send_response("✅ No hay usuarios silenciados")
            return

        # Comando !privilege
        if msg.startswith("!privilege "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden ver privilegios!")
                return
            target_username = msg[11:].strip().replace("@", "")
            target_user_id = next((uid for uid, uname in USER_NAMES.items() if uname == target_username), None)
            if not target_user_id: await send_response(f"❌ Usuario {target_username} no encontrado!"); return
            status = "👤 Usuario normal"
            if self.is_admin(target_user_id): status = "⚔️ Administrador"
            elif self.is_moderator(target_user_id): status = "👮 Moderador"
            await send_response( f"🔍 Privilegios de @{target_username}: {status}")
            return

        # Comando !addmod - Agregar moderador (Solo Owner)
        if msg.startswith("!addmod "):
            if user_id != OWNER_ID:
                await send_response("❌ Solo el propietario puede agregar moderadores")
                return
            
            target_username = msg[8:].strip().replace("@", "")
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                return
            
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            
            if not target_user:
                await send_response(f"❌ Usuario {target_username} no encontrado")
                return
            
            if target_user.id in MODERATOR_IDS:
                await send_response(f"ℹ️ {target_username} ya es moderador")
                return
            
            # Agregar a la lista de moderadores
            MODERATOR_IDS.append(target_user.id)
            
            # Guardar en config.json
            try:
                config = load_config()
                config["moderator_ids"] = MODERATOR_IDS
                with open("config.json", "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                await send_response(f"✅ {target_username} agregado como moderador")
                await self.highrise.chat(f"👮 @{target_username} ahora es moderador de la sala")
                log_event("MOD", f"{username} agregó a {target_username} como moderador")
            except Exception as e:
                await send_response(f"❌ Error guardando: {e}")
            return

        # Comando !removemod - Remover moderador (Solo Owner)
        if msg.startswith("!removemod "):
            if user_id != OWNER_ID:
                await send_response("❌ Solo el propietario puede remover moderadores")
                return
            
            target_username = msg[11:].strip().replace("@", "")
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                return
            
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            
            if not target_user:
                await send_response(f"❌ Usuario {target_username} no encontrado")
                return
            
            if target_user.id not in MODERATOR_IDS:
                await send_response(f"ℹ️ {target_username} no es moderador")
                return
            
            # Remover de la lista
            MODERATOR_IDS.remove(target_user.id)
            
            # Guardar en config.json
            try:
                config = load_config()
                config["moderator_ids"] = MODERATOR_IDS
                with open("config.json", "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                await send_response(f"✅ {target_username} removido como moderador")
                log_event("MOD", f"{username} removió a {target_username} como moderador")
            except Exception as e:
                await send_response(f"❌ Error guardando: {e}")
            return

        # Comando !listmods - Listar moderadores
        if msg.lower() == "!listmods":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌¡Solo administradores y propietario pueden ver la lista de moderadores!")
                return
            
            if not MODERATOR_IDS:
                await send_response("📋 No hay moderadores asignados")
                return
            
            # Obtener nombres de usuarios
            response = await self.highrise.get_room_users()
            mod_names = []
            
            if not isinstance(response, Error):
                user_map = {u.id: u.username for u, _ in response.content}
                mod_names = [user_map.get(mod_id, f"ID:{mod_id[:8]}") for mod_id in MODERATOR_IDS]
            
            await send_response(f"👮 Moderadores ({len(MODERATOR_IDS)}):\n" + "\n".join([f"• @{name}" for name in mod_names]))
            return

        # Comando !tplist
        if msg == "!tplist":
            if TELEPORT_POINTS:
                tele_message = "📍 PUNTOS DE TELETRANSPORTE:\n"
                for name in TELEPORT_POINTS.keys():
                    tele_message += f"🔹 {name}\n"
                tele_message += "\n💡 Usa: !tp [nombre] o escribe el nombre directamente"
                await send_response(tele_message)
            else: await send_response("📍 No hay puntos de teletransporte creados")
            return
        if msg == "!tele list":
            if TELEPORT_POINTS:
                tele_message = "🗺️ UBICACIONES DE TELETRANSPORTE:\n"
                for i, (name, coords) in enumerate(TELEPORT_POINTS.items(), 1):
                    tele_message += f"{i}. {name} (X:{coords['x']:.1f}, Y:{coords['y']:.1f}, Z:{coords['z']:.1f})\n"
                tele_message += "\n💡 Usa: !tp [nombre]"
                await send_response( tele_message)
            else: await send_response("📍 No hay ubicaciones de teletransporte creadas")
            return

        # Comando !delpoint (Owner)
        if msg.startswith("!delpoint"):
            if not self.is_owner(user_id):
                await send_response("❌ ¡Solo el propietario puede eliminar puntos creados!")
                return
            parts = msg.split()
            if len(parts) != 2: await send_response("❌ Usa: !delpoint [nombre]"); return
            point_name = parts[1]
            if point_name in TELEPORT_POINTS:
                del TELEPORT_POINTS[point_name]
                self.save_data()
                await send_response( f"✅ Punto '{point_name}' eliminado!")
            else: await send_response( f"❌ Punto '{point_name}' no encontrado!")
            return

        # Comando !checkvip
        if msg.startswith("!checkvip"):
            parts = msg.split()
            if len(parts) >= 2:
                target_user = parts[1].replace("@", "")
                if target_user in VIP_USERS: await send_response( f"✅ {target_user} tiene estatus VIP!")
                else: await send_response( f"❌ {target_user} no tiene estatus VIP!")
            else:
                is_vip_status = self.is_vip_by_username(user.username)
                await send_response( f"🔍 Tu verificación VIP: {'✅ VIP' if is_vip_status else '❌ No VIP'}")
                await send_response( f"📋 VIP actuales: {', '.join(list(VIP_USERS)[:3])}...")
            return

        # Comando !setvipzone (Owner)
        if msg.startswith("!setvipzone") or msg == "!sv":
            if not self.is_owner(user_id):
                await send_response("❌ ¡Solo el propietario puede establecer la zona VIP!")
                return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            user_position = next((pos for u, pos in users if u.id == user_id), None)
            if user_position:
                if isinstance(user_position, Position):
                    new_vip_zone = {"x": user_position.x, "y": user_position.y, "z": user_position.z}
                elif isinstance(user_position, AnchorPosition) and user_position.offset:
                    new_vip_zone = {"x": user_position.offset.x, "y": user_position.offset.y, "z": user_position.offset.z}
                else:
                    await send_response("¡Error obteniendo posición del usuario!")
                    return
                # Cargar config actual
                config = load_config()
                config["vip_zone"] = new_vip_zone
                # Guardar a archivo
                with open("config.json", "w", encoding="utf-8") as f: 
                    json.dump(config, f, indent=2, ensure_ascii=False)
                # Actualizar variable global
                global VIP_ZONE
                VIP_ZONE = new_vip_zone
                await send_response( f"🎯 Zona VIP establecida en: X={new_vip_zone['x']}, Y={new_vip_zone['y']}, Z={new_vip_zone['z']}")
                log_event("CONFIG", f"Zona VIP actualizada: {new_vip_zone}")
            else: await send_response("¡Error obteniendo posición del usuario!")
            return

        # Comando !setdj (Owner)
        if msg == "!setdj":
            if not self.is_owner(user_id):
                await send_response("❌ ¡Solo el propietario puede establecer la zona DJ!")
                return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            user_position = next((pos for u, pos in users if u.id == user_id), None)
            if user_position:
                if isinstance(user_position, Position):
                    new_dj_zone = {"x": user_position.x, "y": user_position.y, "z": user_position.z}
                elif isinstance(user_position, AnchorPosition) and user_position.offset:
                    new_dj_zone = {"x": user_position.offset.x, "y": user_position.offset.y, "z": user_position.offset.z}
                else:
                    await send_response("¡Error obteniendo posición del usuario!")
                    return
                config = load_config()
                config["dj_zone"] = new_dj_zone
                with open("config.json", "w", encoding="utf-8") as f: 
                    json.dump(config, f, indent=2, ensure_ascii=False)
                global DJ_ZONE
                DJ_ZONE = new_dj_zone
                await send_response(f"🎵 Zona DJ establecida en: X={new_dj_zone['x']}, Y={new_dj_zone['y']}, Z={new_dj_zone['z']}")
                log_event("CONFIG", f"Zona DJ actualizada: {new_dj_zone}")
            else:
                await send_response("¡Error obteniendo posición del usuario!")
            return

        # Comando !setspawn (Owner)
        if msg == "!setspawn":
            if not self.is_owner(user_id):
                await send_response("❌ ¡Solo el propietario puede establecer el punto de inicio!")
                return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            user_position = next((pos for u, pos in users if u.id == user_id), None)
            if user_position:
                if isinstance(user_position, Position):
                    spawn_point = {"x": user_position.x, "y": user_position.y, "z": user_position.z}
                elif isinstance(user_position, AnchorPosition) and user_position.offset:
                    spawn_point = {"x": user_position.offset.x, "y": user_position.offset.y, "z": user_position.offset.z}
                else:
                    await send_response("¡Error obteniendo posición del usuario!")
                    return
                # Guardar el punto sin reiniciar la sesión ni cambiar de sala.
                # El runner solo lee config.json al arrancar un proceso nuevo,
                # por eso también actualizamos el diccionario activo en memoria.
                updated_config = load_config()
                updated_config["spawn_point"] = spawn_point
                with open("config.json", "w", encoding="utf-8") as f:
                    json.dump(updated_config, f, indent=2, ensure_ascii=False)
                config["spawn_point"] = spawn_point

                # El comando debe mover al bot dentro de la sala actual.
                # No se llama a leave_room, disconnect ni a ninguna rutina de
                # reconexión: guardar el spawn no requiere abandonar la sala.
                try:
                    if self.session_active and getattr(self, "bot_id", None):
                        await self.highrise.teleport(
                            self.bot_id,
                            Position(spawn_point["x"], spawn_point["y"], spawn_point["z"]),
                        )
                        log_event("CONFIG", f"Spawn actualizado y bot movido dentro de la sala: {spawn_point}")
                        await send_response(
                            f"📍 Spawn guardado. Bot movido dentro de la sala a "
                            f"X={spawn_point['x']}, Y={spawn_point['y']}, Z={spawn_point['z']}"
                        )
                    else:
                        log_event("CONFIG", f"Spawn actualizado sin mover: sesión no activa ({spawn_point})")
                        await send_response(
                            f"📍 Punto de inicio guardado: X={spawn_point['x']}, "
                            f"Y={spawn_point['y']}, Z={spawn_point['z']}"
                        )
                except Exception as e:
                    # La configuración sigue guardada aunque el servidor no
                    # acepte el teletransporte en ese instante.
                    log_event("WARNING", f"Spawn guardado, pero no se pudo mover al bot: {e}")
                    await send_response(
                        f"📍 Spawn guardado, pero no pude mover al bot ahora. "
                        f"Seguirá en la sala y usará este punto al volver a entrar."
                    )
            else: await send_response("¡Error obteniendo posición del usuario!")
            return

        # Comando !floss_start (Admin/Owner) - Floss infinito
        if msg == "!floss_start":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden activar floss!")
                return
            if self.floss_loop_active and self.bot_mode == "floss":
                await send_response("⚠️ ¡El floss ya está activado!")
                return
            
            # Detener ciclo automático de emotes
            if self.current_emote_task and not self.current_emote_task.done():
                self.current_emote_task.cancel()
                await asyncio.sleep(0.5)
            
            # Cambiar a idle para detener cualquier emote activo
            self.bot_mode = "idle"
            await asyncio.sleep(0.5)
            
            # Ejecutar emotes de parada para limpiar completamente
            try:
                stop_animations = ["idle", "idle-loop-happy", "idle-loop-sad", "idle-loop-tired"]
                for stop_anim in stop_animations:
                    try:
                        await self.highrise.send_emote(stop_anim)
                        await asyncio.sleep(0.1)
                    except:
                        pass
            except:
                pass
            
            await asyncio.sleep(1)
            
            # Iniciar floss
            self.floss_loop_active = True
            self.bot_mode = "floss"
            self.floss_task = asyncio.create_task(self.floss_loop())
            
            await send_response("💃 ¡Floss infinito activado!")
            await self.highrise.chat("💃 Bot ejecutando floss en bucle infinito!")
            safe_print("💃 Floss infinito activado")
            return

        # Comando !floss_stop (Admin/Owner) - Detener floss
        if msg == "!floss_stop":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden desactivar floss!")
                return
            if not self.floss_loop_active:
                await send_response("⚠️ ¡El floss no está activado!")
                return
            
            self.floss_loop_active = False
            self.bot_mode = "idle"
            
            if self.floss_task and not self.floss_task.done():
                self.floss_task.cancel()
            
            await asyncio.sleep(0.5)
            
            # Ejecutar emotes de parada para limpiar completamente
            try:
                stop_animations = ["idle", "idle-loop-happy", "idle-loop-sad", "idle-loop-tired"]
                for stop_anim in stop_animations:
                    try:
                        await self.highrise.send_emote(stop_anim)
                        await asyncio.sleep(0.1)
                    except:
                        pass
            except:
                pass
            
            await send_response("⏹️ Floss desactivado")
            await self.highrise.chat("⏹️ Floss detenido")
            safe_print("⏹️ Floss desactivado")
            return

        # Comando !bot (Admin/Owner) - Bot ataca y usuario recibe revival
            
            # Limpiar el nombre de usuario de posibles espacios y el @
            target_username = msg[5:].strip()
            if target_username.startswith("@"):
                target_username = target_username[1:].strip()
            
            if not target_username:
                return

            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            
            users = response.content
            bot_user, bot_pos, target_user, target_pos = None, None, None, None
            
            # Buscar al bot y al objetivo
            for u, pos in users:
                if hasattr(self, 'bot_id') and u.id == self.bot_id: 
                    bot_user, bot_pos = u, pos
                if u.username.lower() == target_username.lower(): 
                    target_user, target_pos = u, pos
            
            if not bot_user: await send_response("❌ Bot no encontrado!"); return
            if not target_user: await send_response(f"❌ ¡Usuario {target_username} no encontrado en la sala!"); return
            if not bot_pos or not target_pos: await send_response("❌ Error: No se pudieron obtener las posiciones"); return
            
            # Obtener posición actual del bot para regresar después
            response_bot = await self.highrise.get_room_users()
            if isinstance(response_bot, Error):
                await send_response("❌ Error obteniendo usuarios")
                return
            
            users = response_bot.content
            bot_pos = next((pos for u, pos in users if u.id == self.bot_id), None)
            target_user = next((u for u, pos in users if u.username.lower() == target_username.lower()), None)
            target_pos = next((pos for u, pos in users if u.username.lower() == target_username.lower()), None)

            if not bot_pos: await send_response("❌ Error obteniendo posición del bot"); return
            if not target_user or not target_pos: await send_response(f"❌ ¡Usuario {target_username} no encontrado!"); return

            if isinstance(bot_pos, Position):
                original_pos = Position(bot_pos.x, bot_pos.y, bot_pos.z)
            elif isinstance(bot_pos, AnchorPosition):
                original_pos = Position(bot_pos.offset.x, bot_pos.offset.y, bot_pos.offset.z)
            
            if isinstance(target_pos, Position):
                new_position = Position(target_pos.x + 0.5, target_pos.y, target_pos.z)
            elif isinstance(target_pos, AnchorPosition):
                new_position = Position(target_pos.offset.x + 0.5, target_pos.offset.y, target_pos.offset.z)

            # Ejecutar secuencia de ataque
            await self.highrise.teleport(self.bot_id, new_position)
            await asyncio.sleep(1.0)
            await self.highrise.chat(f"‼️ CÁLLATE ‼️")
            
            # Forzar emotes de forma secuencial y con IDs explícitos
            try:
                # El bot hace el punch
                print(f"[DEBUG] Enviando emoji-punch a bot {self.bot_id}")
                await self.highrise.send_emote("emoji-punch", self.bot_id)
                await asyncio.sleep(1.5)
                
                # El usuario hace el revival
                print(f"[DEBUG] Enviando emote-revival a usuario {target_user.id}")
                await self.highrise.send_emote("emote-revival", target_user.id)
                await asyncio.sleep(2.5)
            except Exception as emote_error: 
                print(f"[ERROR] Error en emotes: {emote_error}")
                log_event("WARNING", f"No se pudo hacer emote: {emote_error}")
            
            # Regresar a posición original
            try:
                print(f"[DEBUG] Regresando bot a {original_pos}")
                await self.highrise.teleport(self.bot_id, original_pos)
            except Exception as tp_error:
                print(f"[ERROR] Error al regresar: {tp_error}")
                log_event("ERROR", f"No se pudo regresar al bot: {tp_error}")
            return

        # Comando !spam (Admin/Owner)
        if msg.startswith("!spam "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID): await send_response("❌¡Solo administradores y propietario pueden usar !spam!"); return
            parts = msg.split(" ")
            if len(parts) < 3: await send_response("❌ Uso: !spam <mensaje> <cantidad>"); return
            try:
                # El último elemento es la cantidad, el resto es el mensaje
                count = int(parts[-1])
                spam_msg = " ".join(parts[1:-1])
                # Limitamos a un máximo razonable de 100 permitido por el SDK
                count = min(count, 100) 
                for _ in range(count):
                    await self.highrise.chat(spam_msg)
                    await asyncio.sleep(0.5)
            except: await send_response("❌ Cantidad inválida al final del comando"); return
            return

        # Comando !invite (Para todos los usuarios)
        if msg == "!invite" or msg.startswith("!invite "):
            parts = message.split()
            if len(parts) < 2:
                await send_response("❌ Uso: !invite @usuario o !invite all")
                return
                
            target = parts[1].replace("@", "")
            
            # Carga global del config
            try:
                with open("config.json", "r") as f:
                    config_data = json.load(f)
                    room_id = config_data.get("room_id", "694a084d0bde2d163e1191d3")
            except Exception:
                room_id = "694a084d0bde2d163e1191d3"
            
            if target.lower() == "all":
                if not (self.is_admin(user_id) or user_id == OWNER_ID):
                    await send_response("❌ Solo administradores pueden usar !invite all.")
                    return
                
                # Obtener usuarios actuales en la sala para no invitarlos
                room_users_response = await self.highrise.get_room_users()
                users_in_room_ids = set()
                if not isinstance(room_users_response, Error):
                    users_in_room_ids = {u.id for u, _ in room_users_response.content}

                # Copia segura para evitar errores de iteración si el dict cambia
                convs_to_invite = []
                # Ahora usamos ACTIVE_CONVERSATIONS en lugar de SUBSCRIBERS para máxima efectividad
                for uid, conv_data in ACTIVE_CONVERSATIONS.items():
                    if uid not in users_in_room_ids:
                        if isinstance(conv_data, dict) and "id" in conv_data:
                            convs_to_invite.append((uid, conv_data["id"]))
                        else:
                            # Fallback si el formato es antiguo
                            convs_to_invite.append((uid, conv_data))
                
                count = 0
                
                if not convs_to_invite:
                    await send_response("ℹ️ No hay conversaciones activas fuera de la sala para invitar.")
                    return

                # Obtener usuarios actuales en la sala para no invitarlos
                room_users_response = await self.highrise.get_room_users()
                users_in_room_ids = set()
                if not isinstance(room_users_response, Error):
                    users_in_room_ids = {u.id for u, _ in room_users_response.content}

                await send_response(f"⏳ Iniciando envío de {len(convs_to_invite)} invitaciones a usuarios con chat activo...")
                
                for target_uid, conv_id in convs_to_invite:
                    try:
                        # Mensaje único de invitación masiva (sin nombre de usuario)
                        try:
                            await self.highrise.send_message(conv_id, f"👋 ¡Hola! Te invitamos a pasar un buen rato en la sala, ¡te esperamos! ✨\n🔗 Únete aquí: https://high.rs/room?id={room_id}")
                            count += 1
                        except: pass
                        # Delay para no saturar el SDK
                        await asyncio.sleep(1.0)
                    except Exception as invite_err:
                        safe_print(f"❌ Fallo al enviar invitación a {target_uid}: {invite_err}")
                        # Si la conversación es inválida, la removemos
                        if any(err in str(invite_err).lower() for err in ["invalid", "not active", "not found"]):
                            if target_uid in ACTIVE_CONVERSATIONS: del ACTIVE_CONVERSATIONS[target_uid]
                        continue
                await send_response(f"✉️ Proceso finalizado. Se enviaron {count} invitaciones exitosamente.")
            else:
                try:
                    # Verificar si el usuario ya está en la sala
                    room_users_response = await self.highrise.get_room_users()
                    is_in_room = False
                    if not isinstance(room_users_response, Error):
                        for u, _ in room_users_response.content:
                            if u.username.lower() == target.lower():
                                is_in_room = True
                                break
                    
                    if is_in_room:
                        await send_response(f"ℹ️ @{target} ya se encuentra en la sala.")
                        return

                    target_user = await self.get_user_by_username(target)
                    if not target_user:
                        await send_response(f"❌ Usuario @{target} no encontrado.")
                        return

                    conv_id = ACTIVE_CONVERSATIONS.get(target_user.id)
                    if not conv_id:
                        await send_response(f"❌ @{target} no tiene una conversación de DM activa con el bot. Debe enviarle un mensaje primero.")
                        return

                    try:
                        # Mensajes específicos para invitación individual
                        invite_messages_single = [
                            f"👋 ¡Hola @{target}! Te estoy esperando en mi sala 🎉",
                            f"✨ @{target}, ven a visitarme, ¡la estamos pasando genial! 🎈",
                            f"🌟 ¡Hola! Me gustaría que te unieras a nosotros ahora 💃",
                            f"🔥 @{target}, ¡únete a la diversión en NOCTURNO! 🚀",
                            "🌈 ¡Te espero! No te pierdas lo que está pasando en la sala 💎"
                        ]
                        selected_msg = random.choice(invite_messages_single)
                        
                        # 1. Enviar mensaje de texto
                        await self.highrise.send_message(conv_id, selected_msg, type="text")
                        await asyncio.sleep(0.5)
                        
                        # 2. Enviar invitación oficial del SDK
                        try:
                            await self.highrise.send_message(conv_id, "¡Te invito a mi sala!", type="invite", room_id=room_id)
                            await send_response(f"✅ Invitación enviada por DM a @{target}.")
                        except Exception as official_err:
                            safe_print(f"⚠️ Error en invitación oficial a {target}: {official_err}")
                            # 3. Fallback: enviar enlace manual si falla la oficial
                            await self.highrise.send_message(conv_id, f"🔗 ¡Únete aquí! https://high.rs/room?id={room_id}", type="text")
                            await send_response(f"✅ Invitación enviada por DM a @{target} (enlace manual).")
                    except Exception as invite_err:
                        safe_print(f"❌ Fallo al enviar invitación a {target}: {invite_err}")
                        if any(err in str(invite_err).lower() for err in ["invalid", "not active", "not found"]):
                            if target_user.id in ACTIVE_CONVERSATIONS: del ACTIVE_CONVERSATIONS[target_user.id]
                        await send_response(f"❌ No se pudo enviar el DM a @{target}. Conversación no válida.")
                except Exception as e:
                    safe_print(f"❌ Error crítico en comando invite individual: {e}")
                    await send_response("❌ Ocurrió un error al procesar la invitación.")
            return

        # Comando !Dm (mensaje) - Enviar DM a todos los suscriptores (Admin/Owner)
        if msg.startswith("!dm "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo admins y propietario pueden usar este comando!")
                return
            
            dm_msg = message[4:].strip()
            if not dm_msg:
                await send_response("❌ Usa: !dm [mensaje]")
                return
                
            subs_to_msg = list(SUBSCRIBERS)
            if not subs_to_msg:
                await send_response("ℹ️ No hay suscriptores a quienes enviar el mensaje.")
                return

            await send_response(f"⏳ Iniciando envío de mensaje a {len(subs_to_msg)} suscriptores...")
            
            count = 0
            for sub_id in subs_to_msg:
                conv_id = ACTIVE_CONVERSATIONS.get(sub_id)
                if not conv_id:
                    continue
                try:
                    await self.highrise.send_message(conv_id, dm_msg)
                    count += 1
                    await asyncio.sleep(1.0) # Delay para evitar rate limiting
                except Exception as e:
                    safe_print(f"❌ Fallo al enviar DM a {sub_id}: {e}")
                    if any(err in str(e).lower() for err in ["invalid", "not active", "not found"]):
                        if sub_id in ACTIVE_CONVERSATIONS: del ACTIVE_CONVERSATIONS[sub_id]
                    continue
            
            await send_response(f"📩 Proceso finalizado. Se enviaron {count} mensajes exitosamente.")
            log_event("ADMIN", f"{username} envió un DM masivo: {dm_msg[:50]}...")
            return

        # Comando !auto (mensaje) (tiempo) - Admin/Owner
        if msg.startswith("!auto "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo admins y propietario pueden usar este comando!")
                return
            
            # Usar message original para preservar espacios y minúsculas/mayúsculas
            parts = message.split()
            if len(parts) >= 3:
                try:
                    interval = int(parts[-1])
                    # Extraer el mensaje preservando el formato original del comando inicial
                    # El mensaje está entre el comando "!auto" y el último argumento (tiempo)
                    cmd_start = message.find(" ") + 1
                    cmd_end = message.rfind(" ")
                    custom_msg = message[cmd_start:cmd_end].strip()
                    
                    if not custom_msg:
                         await send_response("❌ Error: El mensaje no puede estar vacío")
                         return

                    if self.auto_msg_task:
                        self.auto_msg_task.cancel()
                    
                    # Guardar configuración para persistencia
                    try:
                        os.makedirs("data", exist_ok=True)
                        with open("data/auto_msg_config.json", "w", encoding="utf-8") as f:
                            json.dump({"active": True, "message": custom_msg, "interval": interval}, f)
                    except:
                        pass
                    
                    self.auto_msg_task = asyncio.create_task(self.auto_msg_loop(custom_msg, interval))
                    await send_response(f"✅ Anuncio automático activado cada {interval}s 🤖✨")
                    log_event("ADMIN", f"Anuncio auto activado: '{custom_msg}' cada {interval}s")
                except ValueError:
                    await send_response("❌ Error: El tiempo debe ser un número en segundos ⏱️")
            else:
                await send_response("ℹ️ Uso: !auto <mensaje> <segundos> 📋💡")
            return

        # Comando !stopauto - Admin/Owner
        if msg == "!stopauto":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo admins y propietario pueden usar este comando!")
                return
            if self.auto_msg_task:
                self.auto_msg_task.cancel()
                self.auto_msg_task = None
                
                # Desactivar persistencia
                try:
                    if os.path.exists("data/auto_msg_config.json"):
                        with open("data/auto_msg_config.json", "w", encoding="utf-8") as f:
                            json.dump({"active": False}, f)
                except:
                    pass
                
                await send_response("🛑 Anuncios automáticos detenidos 🔇")
            else:
                await send_response("ℹ️ No hay anuncios activos.")
            return

        # Comando !room (room_id) - Admin/Owner
        if msg == "!room" or msg.startswith("!room "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ Solo el Propietario o Administradores pueden usar este comando.")
                return
            
            parts = msg.split()
            if len(parts) < 2:
                await send_response("❌ Uso: !room <room_id>")
                return
            
            new_room_id = parts[1].strip()
            await send_response(f"🔄 Cambiando a la sala {new_room_id}... El bot se reiniciará en unos segundos.")
            
            try:
                # Actualizar config.json para que al reiniciar entre en la nueva sala
                import json as json_lib
                import os as os_lib
                with open("config.json", "r", encoding="utf-8") as f:
                    config_data = json_lib.load(f)
                
                config_data["room_id"] = new_room_id
                
                with open("config.json", "w", encoding="utf-8") as f:
                    json_lib.dump(config_data, f, indent=4)
                    f.flush()
                    os_lib.fsync(f.fileno())
                
                log_event("ADMIN", f"Cambiando de sala a {new_room_id} por {user.username}")
                
                # Pequeña pausa para asegurar el envío del mensaje antes del cierre forzoso
                await asyncio.sleep(2)
                
                # Cierre agresivo del proceso para garantizar la desconexión
                import sys as sys_lib
                sys_lib.exit(0)
            except Exception as e:
                await send_response(f"❌ Error al intentar cambiar de sala: {e}")
            return
            if not (self.is_admin(user_id) or user_id == OWNER_ID): await send_response("❌ No tienes permiso"); return
            parts = msg.split()
            if len(parts) < 3: await send_response("❌ Uso: !mover @user <room_id>"); return
            target_username = parts[1].replace("@", "")
            room_id = parts[2]
            target_user = await self.get_user_by_username(target_username)
            if target_user:
                await self.highrise.move_user_to_room(target_user.id, room_id)
                await send_response(f"✈️ Moviendo a @{target_username}...")
            else: await send_response("❌ Usuario no encontrado."); return
            return

        # Comando !test (Clasificar outfit)
        if msg.startswith("!test"):
            # Si hay un argumento, usarlo como target, si no, usar el autor del mensaje
            parts = msg.split()
            if len(parts) > 1:
                target_username = parts[1].strip().replace("@", "")
                target_user = await self.get_user_by_username(target_username)
            else:
                target_user = user
                target_username = user.username

            if not target_user: await send_response("❌ Usuario no encontrado"); return
            
            outfit = await self.highrise.get_user_outfit(target_user.id)
            if isinstance(outfit, Error): await send_response("❌ Error al obtener outfit"); return
            
            items_count = len(outfit.items)
            score = min(items_count * 10, 100) # Lógica simple de puntuación
            if score > 80: rank = "🔥 ¡LEGENDARIO!"
            elif score > 50: rank = "✨ Elegante"
            else: rank = "👕 Básico"
            
            await self.highrise.chat(f"👗 Outfit de @{target_username}: {items_count} items.\n📊 Calificación: {score}/100 - {rank}")
            return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            command_user_position = next((pos for u, pos in users if u.id == user_id), None)
            target_user_obj = next((u for u, _ in users if u.username == target_username), None)
            if not command_user_position: await send_response("❌ ¡Error obteniendo tu posición!"); return
            if not target_user_obj: await send_response( f"❌ ¡Jugador {target_username} no encontrado en la sala!"); return
            if isinstance(command_user_position, Position):
                new_position = Position(command_user_position.x + 1, command_user_position.y, command_user_position.z)
            elif isinstance(command_user_position, AnchorPosition) and command_user_position.offset:
                new_position = Position(command_user_position.offset.x + 1, command_user_position.offset.y, command_user_position.offset.z)
            else:
                await send_response("❌ ¡Error obteniendo tu posición!")
                return
            await self.highrise.teleport(target_user_obj.id, new_position)
            await send_response( f"🎯 @{user.username} movió a {target_username} hacia sí mismo!")
            return

        # Comando !follow @user (Admin/Owner) - El bot sigue a un usuario
        if msg.startswith("!follow "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar este comando!")
                return
            target_username = msg[8:].strip().replace("@", "")
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                return
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            if not target_user:
                await send_response(f"❌ Usuario {target_username} no encontrado")
                return
            FOLLOW_TARGET = target_user.id
            await send_response(f"🚶 Bot siguiendo a @{target_username}")
            asyncio.create_task(self.follow_user_loop(target_user.id))
            return

        # Comando !unfollow (Admin/Owner) - El bot deja de seguir
        if msg == "!unfollow":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar este comando!")
                return
            FOLLOW_TARGET = None
            await send_response("🛑 Bot dejó de seguir")
            return

        # Comando !tpall [punto] (Admin/Owner) - Teletransportar a todos a un punto
        if msg.startswith("!tpall "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo administradores y propietario pueden usar este comando!")
                return
            point_name = msg[7:].strip().lower()
            if point_name not in TELEPORT_POINTS:
                await send_response(f"❌ Punto '{point_name}' no existe\n💡 Usa !tp para ver puntos disponibles")
                return
            point = TELEPORT_POINTS[point_name]
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                return
            users = response.content
            teleported = 0
            for u, _ in users:
                if hasattr(self, 'bot_id') and u.id == self.bot_id:
                    continue
                try:
                    tp_position = Position(point["x"], point["y"], point["z"])
                    await self.highrise.teleport(u.id, tp_position)
                    teleported += 1
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
            await send_response(f"🚀 {teleported} usuarios teletransportados a '{point_name}'")
            return

        # Comando !love all
        if msg.startswith("!love all"):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ Solo propietario y administradores pueden usar !love all")
                return
            
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios de la sala")
                return
            
            # Filtrar usuarios (no bots, no el bot mismo)
            # Regla: No incluir bots
            room_users = [u for u, _ in response.content if u.id != self.bot_id and not any(name in u.username.lower() for name in ["bot", "glux", "highrise"])]
            
            if len(room_users) < 1:
                await send_response("❌ No hay usuarios suficientes en la sala.")
                return
            
            # Regla: No repetir los mismos usuarios y no repetir la misma pareja
            random.shuffle(room_users)
            
            love_messages = {
                (1, 10): "💔 Remplaza a tu pareja... Mejor solo que mal acompañado 😅",
                (11, 30): "🧊 El ambiente está un poco frío aquí...",
                (31, 50): "👀 Hay potencial, pero necesitan conocerse más.",
                (51, 70): "✨ ¡Chispas! Aquí hay algo interesante...",
                (71, 90): "🔥 ¡La temperatura sube! Una pareja espectacular.",
                (91, 100): "💘 ¡AMOR VERDADERO! Están hechos el uno para el otro. ✨"
            }
            
            def get_love_text(percentage):
                for (low, high), text in love_messages.items():
                    if low <= percentage <= high:
                        return text
                return "💖 Interesante conexión."

            available_users = list(room_users)
            
            # Regla: Repetir hasta usar todos los usuarios de la sala
            while len(available_users) >= 2:
                # Regla: No emparejar usuarios consigo mismos (pop asegura unicidad)
                u1 = available_users.pop()
                u2 = available_users.pop()
                
                # Regla: Porcentaje del 1% al 100%
                percentage = random.randint(1, 100)
                text = get_love_text(percentage)
                
                # Regla: Formato exacto de colores y estructura
                love_msg = (
                    f"<#FF0000>❣️ AMORÓMETRO:\n"
                    f"<#FFFFFF>👥 USUARIOS: @{u1.username} --> @{u2.username}\n"
                    f"📊 PORCENTAJE:<#FF0000>{percentage}%\n"
                    f"<#FFFFFF>📝 TEXTO: {text}"
                )
                await self.highrise.chat(love_msg)
                # Optimización: Tiempo mínimo para evitar lag pero ser rápido
                await asyncio.sleep(0.2)
            
            # Caso especial — si queda 1 solo usuario sin pareja
            if available_users:
                u = available_users.pop()
                love_msg = (
                    f"<#FF0000>❣️ AMORÓMETRO:\n"
                    f"<#FFFFFF>👤 USUARIO: @{u.username}\n"
                    f"📊 PORCENTAJE:<#FF0000>0%\n"
                    f"<#FFFFFF>📝 TEXTO: 💔 Parece que Cupido anda de vacaciones… o no hay una flecha a tu nombre 😅"
                )
                await self.highrise.chat(love_msg)
            
            return

        # Comando !love @user @user (público)
        if msg.startswith("!love"):
            parts = msg.split()
            mentions = [p.replace("@", "") for p in parts if p.startswith("@")]
            
            if len(mentions) >= 2:
                u1_username = mentions[0]
                u2_username = mentions[1]

                # Detectar si el bot es mencionado
                bot_name = (self.bot_username or "").lower().lstrip("@")
                mentioned = [u1_username.lower(), u2_username.lower()]
                if bot_name and bot_name in mentioned:
                    await send_response("💔 Yo no sé amar... soy un rompecorazones 🖤✨")
                    return
                
                percentage = random.randint(1, 100)
                
                love_messages = {
                    (0, 10): "💔 Remplaza a tu pareja... Mejor solo que mal acompañado 😅",
                    (11, 30): "🧊 El ambiente está un poco frío aquí...",
                    (31, 50): "👀 Hay potencial, pero necesitan conocerse más.",
                    (51, 70): "✨ ¡Chispas! Aquí hay algo interesante...",
                    (71, 90): "🔥 ¡La temperatura sube! Una pareja espectacular.",
                    (91, 100): "💘 ¡AMOR VERDADERO! Están hechos el uno para el otro. ✨"
                }
                
                def get_love_text(percentage):
                    for (low, high), text in love_messages.items():
                        if low <= percentage <= high:
                            return text
                    return "💖 Interesante conexión."
                
                text = get_love_text(percentage)
                
                love_msg = (
                    f"<#FF0000>❣️ AMORÓMETRO:\n"
                    f"<#FFFFFF>👥 USUARIOS: @{u1_username} --> @{u2_username}\n"
                    f"📊 PORCENTAJE:<#FF0000>{percentage}%\n"
                    f"<#FFFFFF>📝 TEXTO: {text}"
                )
                await self.highrise.chat(love_msg)
                return
            elif msg == "!love":
                # Si solo ponen !love sin argumentos, podemos dar instrucciones o mantener el comportamiento anterior
                # Pero el usuario pidió específicamente !love @user @user
                await send_response("ℹ️ Uso correcto: !love @usuario1 @usuario2")
                return

        # Comando !stats
        if msg == "!stats":
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            total_users = len(users)
            admin_count = sum(1 for u, _ in users if self.is_admin(u.id))
            mod_count = sum(1 for u, _ in users if self.is_moderator(u.id) and not self.is_admin(u.id))
            vip_count = sum(1 for u, _ in users if self.is_vip_by_username(u.username))
            total_messages = sum(data.get("messages", 0) for data in USER_ACTIVITY.values())
            total_hearts = sum(USER_HEARTS.values())
            stats_msg = f"📊 ESTADÍSTICAS DE LA SALA:\n👥 Usuarios: {total_users}\n🛡️ Admins: {admin_count}\n⚖️ Mods: {mod_count}\n⭐ VIPs: {vip_count}\n💬 Mensajes: {total_messages}\n💖 Corazones: {total_hearts}"
            await self.highrise.chat(stats_msg)
            return

        # Comando !online
        if msg == "!online":
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                log_event("ERROR", f"get_room_users failed: {response.message}")
                return
            users = response.content
            admins, mods, vips, regular = [], [], [], []
            for u, _ in users:
                if self.is_admin(u.id): admins.append(u.username)
                elif self.is_moderator(u.id): mods.append(u.username)
                elif self.is_vip_by_username(u.username): vips.append(u.username)
                else: regular.append(u.username)
            online_msg = f"👥 USUARIOS ONLINE ({len(users)}):\n"
            if admins: online_msg += f"🛡️ Admins: {', '.join(admins)}\n"
            if mods: online_msg += f"⚖️ Mods: {', '.join(mods)}\n"
            if vips:
                online_msg += f"⭐ VIPs: {', '.join(vips[:5])}"
                if len(vips) > 5: online_msg += f" (+{len(vips)-5} más)"
                online_msg += "\n"
            online_msg += f"👤 Usuarios: {len(regular)}"
            await self.highrise.chat(online_msg)
            return

        # Comando !achievements
        if msg == "!achievements":
            user_hearts = self.get_user_hearts(user_id)
            user_messages = USER_ACTIVITY.get(user_id, {}).get("messages", 0)
            user_time = self.get_user_total_time(user_id)
            achievements = []
            if user_hearts >= 1000: achievements.append("💎 Maestro del Amor")
            elif user_hearts >= 500: achievements.append("💖 Coleccionista de Corazones")
            elif user_hearts >= 100: achievements.append("❤️ Amante")
            if user_messages >= 1000: achievements.append("📢 Locutor Profesional")
            elif user_messages >= 500: achievements.append("💬 Conversador Activo")
            elif user_messages >= 100: achievements.append("✍️ Participante")
            if user_time >= 36000: achievements.append("⏰ Veterano de la Sala")
            elif user_time >= 18000: achievements.append("🕐 Residente Frecuente")
            if self.is_vip_by_username(user.username): achievements.append("⭐ Miembro VIP")
            if self.is_admin(user_id): achievements.append("🛡️ Administrador")
            ach_msg = f"🏆 LOGROS DE @{user.username}:\n" + "\n".join(f"• {ach}" for ach in achievements) if achievements else f"🎯 @{user.username} aún no ha desbloqueado logros\n💡 Sé activo para conseguirlos!"
            await send_response(ach_msg)
            return

        # Comando !rank
        if msg == "!rank":
            user_hearts = self.get_user_hearts(user_id)
            user_messages = USER_ACTIVITY.get(user_id, {}).get("messages", 0)
            total_score = user_hearts + (user_messages * 2)
            if total_score >= 5000: rank = "💎 Diamante"
            elif total_score >= 2000: rank = "🥇 Oro"
            elif total_score >= 1000: rank = "🥈 Plata"
            elif total_score >= 500: rank = "🥉 Bronce"
            else: rank = "🌱 Novato"
            rank_msg = f"🎖️ RANGO DE @{user.username}:\n{rank}\nPuntuación: {total_score}\n💖 Corazones: {user_hearts}\n💬 Mensajes: {user_messages}"
            await send_response(rank_msg)
            return

        # Comando !daily
        if msg == "!daily":
            current_time = datetime.now()
            last_daily_key = f"{user_id}_last_daily"
            if last_daily_key in USER_INFO.get(user_id, {}):
                last_claim_str = USER_INFO[user_id][last_daily_key]
                last_claim = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
                if (current_time - last_claim).days < 1:
                    hours_left = 24 - (current_time - last_claim).seconds // 3600
                    await send_response(f"⏰ Ya reclamaste tu recompensa diaria\n🕐 Vuelve en {hours_left}h")
                    return
            daily_hearts = 10
            self.add_user_hearts(user_id, daily_hearts, user.username)
            if user_id not in USER_INFO: USER_INFO[user_id] = {}
            USER_INFO[user_id][last_daily_key] = current_time.isoformat()
            save_user_info()
            await send_response(f"🎁 ¡Recompensa diaria reclamada!\n💖 +{daily_hearts} corazones")
            return

        # Comando !TPus (Owner)
        if msg.startswith("!TPus"):
            if user_id != OWNER_ID: await send_response("❌ ¡Solo el propietario puede crear puntos de teletransporte!"); return
            parts = msg.split()
            if len(parts) >= 2:
                point_name = parts[1]
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    log_event("ERROR", f"get_room_users failed: {response.message}")
                    return
                users = response.content
                user_position = next((pos for u, pos in users if u.id == user_id), None)
                if user_position:
                    if isinstance(user_position, Position):
                        TELEPORT_POINTS[point_name] = {"x": user_position.x, "y": user_position.y, "z": user_position.z}
                        self.save_data()
                        await send_response( f"📍 Punto de teletransporte '{point_name}' creado en posición: X={user_position.x}, Y={user_position.y}, Z={user_position.z}")
                    elif isinstance(user_position, AnchorPosition) and user_position.offset:
                        TELEPORT_POINTS[point_name] = {"x": user_position.offset.x, "y": user_position.offset.y, "z": user_position.offset.z}
                        save_leaderboard_data()
                        self.save_data()
                        await send_response( f"📍 Punto de teletransporte '{point_name}' creado en posición: X={user_position.offset.x}, Y={user_position.offset.y}, Z={user_position.offset.z}")
                    else:
                        await send_response("¡Error obteniendo posición del usuario!")
                else: await send_response("¡Error obteniendo posición del usuario!")
            else: await send_response("❌ Usa: !TPus [nombre]")
            return

        # Comandos de interacción (Solo VIP+)
        if msg.startswith("!punch") or msg.startswith("!puñetazo") or msg.startswith("!puño") or msg.startswith("!slap") or msg.startswith("!bofetada") or msg.startswith("!flirt") or msg.startswith("!scare") or msg.startswith("!electro") or msg.startswith("!hug") or msg.startswith("!abrazo") or msg.startswith("!ninja") or msg.startswith("!laugh") or msg.startswith("!boom"):
            # Verificar permisos: Solo VIP, Admin y Owner pueden usar interacciones
            is_vip = self.is_vip_by_username(username)
            is_admin_or_owner = self.is_admin(user_id) or user_id == OWNER_ID
            
            if not (is_vip or is_admin_or_owner):
                await send_response("🛑Acceso denegado.\nPermisos requeridos: “VIP”")
                return
            
            parts = msg.split()
            if len(parts) >= 2:
                target_username = parts[1].replace("@", "")
                command = parts[0]
                
                # Evitar que el usuario interactúe consigo mismo
                if target_username.lower() == username.lower():
                    await send_response(f"❌ ¡No puedes usar {command} contigo mismo!")
                    return

                # PROTECCIÓN ESPECIAL para el BOT
                if target_username.lower() == BOT_ID.lower() or any(name == target_username.lower() for name in ["bot", "glux", "highrise"]):
                    await self.highrise.send_emote("emote-death", user.id)
                    responses = [
                        "🛡️ Mi armadura es impenetrable @{user.username}",
                        "⚡ ¡Cuidado @{user.username}! Si me tocas podrías electrocutarte.",
                        "🤖 @{user.username} Soy un ser digital, no puedes lastimarme.",
                        "💨 ¡Fallaste @{user.username}! Soy más rápido que tu comando.",
                        "✨ @{user.username} Tus ataques solo me dan más energía."
                    ]
                    await self.highrise.chat(random.choice(responses).format(user=user))
                    return

                # PROTECCIÓN ESPECIAL para los jefes
                protected_users = ["_Kmi.77", "Alber_JG_69"]
                if target_username in protected_users:
                    if command in ["!punch", "!puñetazo", "!puño", "!slap", "!bofetada", "!scare", "!electro", "!ninja", "!boom"]:
                        await self.highrise.chat(f"🛡️ ¡ALTO! @{target_username} es mi JEFE")
                        await asyncio.sleep(0.5)
                        await self.highrise.chat(f"👑 No puedo permitir que lastimen a @{target_username}. ¡Respeto total!")
                        return
                
                users = (await self.highrise.get_room_users()).content
                sender_pos, target_user, target_pos = None, None, None
                for u, pos in users:
                    if u.id == user.id: sender_pos = pos
                    if u.username == target_username: target_user, target_pos = u, pos
                if not target_user: await send_response( f"❌ ¡Usuario {target_username} no encontrado!"); return
                
                # Bloquear interacciones hacia el bot
                if target_username.lower() == BOT_ID.lower() or target_user.id == self.bot_id or any(name == target_username.lower() for name in ["bot", "glux", "highrise"]):
                    await self.highrise.send_emote("emote-rofl", user.id)
                    responses = ["😂 ¡No puedes hacerme eso!", "🤣 ¡Inténtalo de nuevo!", "😝 ¡Soy un bot, no puedes tocarme!", "🤪 ¡Jajaja, buen intento!"]
                    await send_response(random.choice(responses))
                    return

                if not sender_pos or not target_pos: await send_response( f"❌ No se pudo obtener la posición de los usuarios!"); return
                # Eliminada restricción de distancia para permitir cualquier distancia
                # distance = self.calculate_distance(sender_pos, target_pos)
                # if command not in ["!punch", "!slap"] and distance > 3.0: await send_response( f"❌ ¡{target_username} está muy lejos!"); return

                sender_emote_id, receiver_emote_id, action_message = "", "", ""
                if command in ["!punch", "!puñetazo", "!puño"]: sender_emote_id, receiver_emote_id, action_message = "emoji-punch", "emote-death", f"🥊 @{user.username} golpeó a @{target_username} y lo dejó noqueado!"
                elif command in ["!slap", "!bofetada"]: sender_emote_id, receiver_emote_id, action_message = "emote-slap", "emoji-dizzy", f"👋 @{user.username} dio una bofetada a @{target_username} y lo dejó en shock!"
                elif command == "!flirt": sender_emote_id, receiver_emote_id, action_message = "emote-kissing", "emote-hearteyes", f"💕 @{user.username} coquetea con @{target_username} y se derrite de amor!"
                elif command == "!scare": sender_emote_id, receiver_emote_id, action_message = "emote-panic", "emoji-scared", f"😱 @{user.username} asustó a @{target_username} y huyó en pánico!"
                elif command == "!electro": sender_emote_id, receiver_emote_id, action_message = "emote-fail1", "emote-fail2", f"⚡ @{user.username} electrocutó a @{target_username} y se quemó!"
                elif command in ["!hug", "!abrazo"]: sender_emote_id, receiver_emote_id, action_message = "emote-hug", "emote-hugyourself", f"🤗 @{user.username} abrazó a @{target_username} y lloró de emoción!"
                elif command == "!ninja": sender_emote_id, receiver_emote_id, action_message = "emote-ninjarun", "emote-fail1", f"🥷 @{user.username} atacó como ninja a @{target_username} y se retuerce de dolor!"
                elif command == "!laugh": sender_emote_id, receiver_emote_id, action_message = "emote-laughing", "emote-laughing2", f"😂 @{user.username} hizo reír a @{target_username} sin parar!"
                elif command == "!boom": sender_emote_id, receiver_emote_id, action_message = "emote-disappear", "emote-fail1", f"💥 @{user.username} explotó a @{target_username} y literalmente explotó!"

                if sender_emote_id and receiver_emote_id:
                    # Usar highrise.send_emote directamente en lugar de send_emote_loop
                    # para evitar el bucle infinito en las interacciones
                    asyncio.create_task(self.highrise.send_emote(sender_emote_id, user.id))
                    asyncio.create_task(self.highrise.send_emote(receiver_emote_id, target_user.id))
                    
                    # Log para debug (opcional)
                    safe_print(f"DEBUG: Interaction - Sender: {user.username} ({sender_emote_id}), Target: {target_username} ({receiver_emote_id})")
                    
                    await send_response(action_message)
                    return
            else: await send_response("❌ Usa: !comando @usuario")
            return

        # Comando !sendall [zona] - Enviar a todos los usuarios a una zona (Admin/Owner)
        if msg.startswith("!sendall "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo admins y propietario pueden usar !sendall!")
                return
            
            parts = msg.split()
            if len(parts) < 2:
                await send_response("❌ Usa: !sendall [zona]\n💡 Usa !tplist para ver zonas disponibles")
                return
            
            zone_name = parts[1].lower()
            
            if zone_name not in TELEPORT_POINTS:
                await send_response(f"❌ Zona '{zone_name}' no encontrada. Usa !tplist")
                return
            
            point = TELEPORT_POINTS[zone_name]
            
            try:
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    return
                
                users = response.content
                moved_count = 0
                
                for u, _ in users:
                    # Saltar admin, owner y bots
                    if u.id == OWNER_ID or self.is_admin(u.id):
                        continue
                    if any(name in u.username.lower() for name in ["bot", "glux", "highrise"]):
                        continue
                    
                    try:
                        teleport_position = Position(point["x"], point["y"], point["z"])
                        await self.highrise.teleport(u.id, teleport_position)
                        moved_count += 1
                        await asyncio.sleep(0.2)  # Delay para evitar rate limit
                    except Exception as e:
                        safe_print(f"⚠️ Error moviendo a {u.username}: {e}")
                        continue
                
                await self.highrise.chat(f"🚁 {moved_count} usuarios fueron enviados a '{zone_name}' por @{username}")
                await send_response(f"✅ {moved_count} usuarios enviados a '{zone_name}'")
                log_event("TELEPORT", f"{username} envió {moved_count} usuarios a '{zone_name}'")
            except Exception as e:
                await send_response(f"❌ Error: {e}")
                log_event("ERROR", f"Error en !sendall: {e}")
            return

        # Comando !summ @user - Traer usuario a tu posición (Admin/Owner)
        if msg.startswith("!summ "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo admins y propietario pueden usar !summ!")
                return
            
            parts = msg.split()
            if len(parts) < 2:
                await send_response("❌ Usa: !summ @usuario")
                return
            
            target_username = parts[1].replace("@", "")
            
            # Obtener posición del admin que llama
            try:
                # Obtener todos los usuarios para encontrar al que ejecuta y al target
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    return
                
                users = response.content
                # Encontrar la posición del usuario que ejecutó el comando (user_id)
                caller_pos = next((pos for u, pos in users if u.id == user_id), None)
                target_user = next((u for u, pos in users if u.username == target_username), None)
                
                if not caller_pos or not isinstance(caller_pos, Position):
                    await send_response("❌ No se pudo determinar tu posición actual.")
                    return
                
                if not target_user:
                    await send_response(f"❌ Usuario @{target_username} no encontrado en la sala.")
                    return
                
                await self.highrise.teleport(target_user.id, caller_pos)
                await send_response(f"✨ Trajiste a @{target_username} a tu posición 🌀")
                log_event("TELEPORT", f"{username} trajo a {target_username} a su posición")
            except Exception as e:
                await send_response(f"❌ Error: {e}")
            return

        # Comando !goto @user [punto] - Teletransportar usuario a punto guardado (Admin/Owner)
        if msg.startswith("!goto "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ ¡Solo admins y propietario pueden usar !goto!")
                return
            
            parts = msg.split()
            if len(parts) < 3:
                await send_response("❌ Usa: !goto @usuario [punto]")
                return
            
            target_username = parts[1].replace("@", "")
            point_name = parts[2].lower()
            
            if point_name not in TELEPORT_POINTS:
                await send_response(f"❌ Punto '{point_name}' no encontrado. Usa !tplist")
                return
            
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo usuarios")
                return
            
            users = response.content
            target_user = next((u for u, _ in users if u.username == target_username), None)
            
            if not target_user:
                await send_response(f"❌ Usuario {target_username} no encontrado!")
                return
            
            point = TELEPORT_POINTS[point_name]
            try:
                teleport_position = Position(point["x"], point["y"], point["z"])
                await self.highrise.teleport(target_user.id, teleport_position)
                await send_response(f"🚁 Teletransportaste a @{target_username} a '{point_name}'!")
                await self.highrise.send_whisper(target_user.id, f"📍 Fuiste teletransportado a '{point_name}' por @{username}")
                log_event("TELEPORT", f"{username} envió a {target_username} a '{point_name}' - X:{point['x']}, Y:{point['y']}, Z:{point['z']}")
            except Exception as e:
                await send_response(f"❌ Error: {e}")
                log_event("ERROR", f"Error en !goto: {e}")
            return

        # Comando !send @user [punto] (Admin/Owner)
        if msg.startswith("!send ") and self.is_admin(user_id):
            parts = msg.split()
            if len(parts) >= 3:
                target_username = parts[1].replace("@", "")
                point_name = parts[2].lower()
                
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    if point_name in TELEPORT_POINTS:
                        p = TELEPORT_POINTS[point_name]
                        await self.highrise.teleport(target_user.id, Position(p["x"], p["y"], p["z"]))
                        await send_response(f"🚀 @{target_username} enviado a {point_name} ✨")
                    else:
                        await send_response(f"❌ Punto '{point_name}' no encontrado. Usa !tplist 📍")
                else:
                    await send_response("❌ Usuario no encontrado en la sala 👤")
            else:
                await send_response("ℹ️ Uso: !send @usuario [punto] 📋📍")

        # Comando !tp [punto]
        if msg.startswith("!tp "):
            point_name = msg[4:].strip().lower()
            if point_name in TELEPORT_POINTS:
                # Verificar permisos para zonas restringidas
                if point_name in ["vip", "pv"]:
                    has_permission = (
                        user_id == OWNER_ID or 
                        self.is_admin(user_id) or 
                        username in VIP_USERS
                    )
                    if not has_permission:
                        await send_response(f"🔒 '{point_name}' es zona VIP. ¡Solo VIP, admins y el propietario pueden acceder!")
                        return
                
                elif point_name in ["directivo", "dj", "carcel"]:
                    has_permission = (
                        user_id == OWNER_ID or 
                        self.is_admin(user_id)
                    )
                    if not has_permission:
                        await send_response(f"🔒 '{point_name}' es zona exclusiva. ¡Solo admins y el propietario pueden acceder!")
                        return
                
                point = TELEPORT_POINTS[point_name]
                try:
                    teleport_position = Position(point["x"], point["y"], point["z"])
                    await self.highrise.teleport(user_id, teleport_position)
                    await send_response(f"🚀 Te teletransportaste a '{point_name}'!")
                    log_event("TELEPORT", f"{username} fue a zona '{point_name}' - X:{point['x']}, Y:{point['y']}, Z:{point['z']}")
                except Exception as e: 
                    await send_response(f"❌ Error de teletransporte: {e}")
                    log_event("ERROR", f"Error teletransporte {username} a '{point_name}': {e}")
            else:
                await send_response(f"❌ Punto '{point_name}' no encontrado. Usa !tplist para ver los disponibles")
            return

        # Comando vip (teletransporte a zona VIP usando VIP_ZONE del config)
        if msg == "vip" or msg == "!vip":
            has_permission = (
                user_id == OWNER_ID or 
                self.is_admin(user_id) or 
                username in VIP_USERS or
                self.is_vip(user_id)
            )
            if not has_permission:
                await send_response("🛑Acceso denegado.\nPermisos requeridos: “VIP”")
                return
            
            if VIP_ZONE and VIP_ZONE.get("x") is not None:
                try:
                    vip_position = Position(VIP_ZONE["x"], VIP_ZONE["y"], VIP_ZONE["z"])
                    await self.highrise.teleport(user_id, vip_position)
                    await send_response(f"⭐ Te teletransportaste a la zona VIP!")
                    log_event("TELEPORT", f"{username} accedió a zona VIP - X:{VIP_ZONE['x']}, Y:{VIP_ZONE['y']}, Z:{VIP_ZONE['z']}")
                except Exception as e:
                    await send_response(f"❌ Error de teletransporte: {e}")
                    log_event("ERROR", f"Error teletransporte {username} a zona VIP: {e}")
            else:
                await send_response("❌ Zona VIP no configurada. Usa !setvipzone para establecerla")
            return

        # Comando dj (teletransporte a zona DJ)
        if msg == "dj" or msg == "!dj":
            has_permission = (user_id == OWNER_ID or self.is_admin(user_id))
            if not has_permission:
                await send_response("❌ ¡Solo administradores y propietario pueden acceder a la zona DJ!")
                return
            
            if DJ_ZONE and DJ_ZONE.get("x") is not None:
                try:
                    dj_position = Position(DJ_ZONE["x"], DJ_ZONE["y"], DJ_ZONE["z"])
                    await self.highrise.teleport(user_id, dj_position)
                    await send_response(f"🎵 Te teletransportaste a la zona DJ!")
                    log_event("TELEPORT", f"{username} accedió a zona DJ - X:{DJ_ZONE['x']}, Y:{DJ_ZONE['y']}, Z:{DJ_ZONE['z']}")
                except Exception as e:
                    await send_response(f"❌ Error de teletransporte: {e}")
            else:
                await send_response("❌ Zona DJ no configurada. Usa !setdj para establecerla")
            return

        # Comando directivo (teletransporte a zona directivo)
        if msg == "directivo" or msg == "!directivo":
            has_permission = (user_id == OWNER_ID or self.is_admin(user_id))
            if not has_permission:
                await send_response("❌ ¡Solo administradores y propietario pueden acceder a la zona directiva!")
                return
            
            if DIRECTIVO_ZONE and DIRECTIVO_ZONE.get("x") is not None:
                try:
                    directivo_position = Position(DIRECTIVO_ZONE["x"], DIRECTIVO_ZONE["y"], DIRECTIVO_ZONE["z"])
                    await self.highrise.teleport(user_id, directivo_position)
                    await send_response(f"👑 Te teletransportaste a la zona directivo!")
                    log_event("TELEPORT", f"{username} accedió a zona directivo - X:{DIRECTIVO_ZONE['x']}, Y:{DIRECTIVO_ZONE['y']}, Z:{DIRECTIVO_ZONE['z']}")
                except Exception as e:
                    await send_response(f"❌ Error de teletransporte: {e}")
            else:
                await send_response("❌ Zona directivo no configurada. Usa !setdirectivo para establecerla")
            return

        # Comando carcel (teletransporte a carcel - solo admin/owner pueden ir voluntariamente)
        if msg == "carcel" or msg == "!carcel":
            has_permission = (user_id == OWNER_ID or self.is_admin(user_id))
            if not has_permission:
                await send_response("❌ ¡La cárcel es solo para prisioneros!\n⚠️ Solo administradores y propietario pueden visitarla voluntariamente")
                return
            
            # Crear cárcel automáticamente si no existe
            if "carcel" not in TELEPORT_POINTS:
                TELEPORT_POINTS["carcel"] = {"x": 0.0, "y": 100.0, "z": 0.0}
                self.save_data()
                safe_print(f"🔒 Zona cárcel creada automáticamente en Y=100.0")
            
            point = TELEPORT_POINTS["carcel"]
            try:
                carcel_position = Position(point["x"], point["y"], point["z"])
                await self.highrise.teleport(user_id, carcel_position)
                await send_response(f"⛓️ Visitaste la cárcel en altura Y={point['y']}")
                log_event("TELEPORT", f"{username} visitó la cárcel - X:{point['x']}, Y:{point['y']}, Z:{point['z']}")
            except Exception as e:
                await send_response(f"❌ Error de teletransporte: {e}")
            return

        # Teletransporte a puntos (escribiendo el nombre directamente)
        if msg.lower() in TELEPORT_POINTS:
            point_name = msg.lower()
            
            # Verificar permisos para zonas restringidas
            if point_name in ["vip", "pv"]:
                has_permission = (
                    user_id == OWNER_ID or 
                    self.is_admin(user_id) or 
                    username in VIP_USERS or
                    self.is_vip(user_id)
                )
                if not has_permission:
                    await send_response(f"🔒 '{point_name}' es zona VIP. ¡Solo VIP, admins y el propietario pueden acceder!")
                    log_event("TELEPORT", f"{username} intentó acceder a '{point_name}' sin permisos")
                    return
            
            elif point_name in ["directivo", "dj"]:
                has_permission = (
                    user_id == OWNER_ID or 
                    self.is_admin(user_id)
                )
                if not has_permission:
                    await send_response(f"🔒 '{point_name}' es zona exclusiva. ¡Solo admins y el propietario pueden acceder!")
                    log_event("TELEPORT", f"{username} intentó acceder a '{point_name}' sin permisos")
                    return
            
            elif point_name == "carcel":
                # La cárcel solo puede ser accedida por admin/owner
                is_admin_or_owner = (user_id == OWNER_ID or self.is_admin(user_id))
                
                if not is_admin_or_owner:
                    await send_response(f"🔒 ¡Solo admins y propietario pueden ir a la cárcel!")
                    log_event("TELEPORT", f"{username} intentó acceder a cárcel sin autorización")
                    return
            
            point = TELEPORT_POINTS[point_name]
            try:
                teleport_position = Position(point["x"], point["y"], point["z"])
                await self.highrise.teleport(user_id, teleport_position)
                await send_response(f"🚀 @{username} se teletransportó al punto '{point_name}'!")
                log_event("TELEPORT", f"{username} accedió a '{point_name}' - X:{point['x']}, Y:{point['y']}, Z:{point['z']}")
            except Exception as e: 
                await send_response(f"❌ Error de teletransporte: {e}")
                log_event("ERROR", f"Error teletransporte {username} a '{point_name}': {e}")
            return

        # Comando !tele @user (VIP)
        if msg.startswith("!tele @"):
            target_username = msg[7:].strip().lower()
            
            # Owner y Admin pueden usar !tele hacia cualquier usuario, sin restricción
            is_privileged = user_id == OWNER_ID or self.is_admin(user_id)
            
            try:
                response = await self.highrise.get_room_users()
                if isinstance(response, Error):
                    await send_response("❌ Error obteniendo usuarios")
                    return
                users = response.content
                target_user = None
                target_position = None
                for u, pos in users:
                    if u.username.lower() == target_username:
                        target_user = u
                        target_position = pos
                        break
                
                if not target_user or not target_position:
                    await send_response(f"❌ ¡Usuario {target_username} no encontrado!")
                    return

                # Restricción de línea para usuarios no privilegiados
                if not is_privileged and self.restrict_p1 and self.restrict_p2:
                    # Posición del objetivo
                    px, pz = 0.0, 0.0
                    if isinstance(target_position, Position):
                        px, pz = target_position.x, target_position.z
                    elif isinstance(target_position, AnchorPosition) and target_position.offset:
                        px, pz = target_position.offset.x, target_position.offset.z
                    else:
                        await send_response("❌ No se pudo obtener la posición del usuario")
                        return

                    # Coordenadas de la línea
                    x1, z1 = self.restrict_p1["x"], self.restrict_p1["z"]
                    x2, z2 = self.restrict_p2["x"], self.restrict_p2["z"]

                    # Cálculo del lado (Cross Product en plano XZ)
                    side = (x2 - x1) * (pz - z1) - (z2 - z1) * (px - x1)
                    
                    # Definimos "detrás" como side < 0
                    if side < 0:
                        await send_response("❌ El usuario está en una zona restringida.")
                        return

                if not is_privileged and not self.is_vip_by_username(user.username):
                    await send_response("❌ ¡Solo VIP pueden usar este comando!")
                    return
                
                # Obtener altura (Y) del objetivo
                target_y = 0.0
                if isinstance(target_position, Position):
                    target_y = target_position.y
                elif isinstance(target_position, AnchorPosition) and target_position.offset:
                    target_y = target_position.offset.y
                
                # Verificar alturas prohibidas
                for altura_prohibida, zona_nombre in ALTURAS_PROHIBIDAS.items():
                    if abs(target_y - altura_prohibida) <= 0.1:
                        await send_response(f"❌ No puedes ir ahí, es la zona de {zona_nombre}")
                        return

                # Teletransportar
                if isinstance(target_position, Position):
                    new_position = Position(target_position.x + 1, target_position.y, target_position.z)
                elif isinstance(target_position, AnchorPosition) and target_position.offset:
                    new_position = Position(target_position.offset.x + 1, target_position.offset.y, target_position.offset.z)
                else:
                    await send_response("❌ No se pudo obtener la posición del usuario")
                    return
                
                await self.highrise.teleport(user_id, new_position)
                await send_response(f"🎯 Te has teletransportado a @{target_username}!")
            except Exception as e:
                await send_response(f"❌ Error: {e}")
            return

        # Comando !x (Admin/Owner) - Guardar primer punto de restricción
        if msg == "!x":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ Solo Owner y Admin pueden configurar la restricción.")
                return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo posición")
                return
            user_pos = next((pos for u, pos in response.content if u.id == user_id), None)
            if user_pos:
                if isinstance(user_pos, Position):
                    self.restrict_p1 = {"x": user_pos.x, "y": user_pos.y, "z": user_pos.z}
                elif isinstance(user_pos, AnchorPosition) and user_pos.offset:
                    self.restrict_p1 = {"x": user_pos.offset.x, "y": user_pos.offset.y, "z": user_pos.offset.z}
                
                if self.restrict_p1:
                    await send_response(f"📍 Punto X guardado: ({self.restrict_p1['x']:.2f}, {self.restrict_p1['z']:.2f})")
            else:
                await send_response("❌ No se pudo obtener tu posición.")
            return

        # Comando !y (Admin/Owner) - Guardar segundo punto de restricción
        if msg == "!y":
            if not (self.is_admin(user_id) or user_id == OWNER_ID):
                await send_response("❌ Solo Owner y Admin pueden configurar la restricción.")
                return
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                await send_response("❌ Error obteniendo posición")
                return
            user_pos = next((pos for u, pos in response.content if u.id == user_id), None)
            if user_pos:
                if isinstance(user_pos, Position):
                    self.restrict_p2 = {"x": user_pos.x, "y": user_pos.y, "z": user_pos.z}
                elif isinstance(user_pos, AnchorPosition) and user_pos.offset:
                    self.restrict_p2 = {"x": user_pos.offset.x, "y": user_pos.offset.y, "z": user_pos.offset.z}
                
                if self.restrict_p2:
                    await send_response(f"📍 Punto Y guardado: ({self.restrict_p2['x']:.2f}, {self.restrict_p2['z']:.2f})")
                    if self.restrict_p1:
                        await send_response("✅ Línea de restricción definida.")
            else:
                await send_response("❌ No se pudo obtener tu posición.")
            return

        # Comando !addzone (Admin/Owner)
        if msg.startswith("!addzone "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID): await send_response("❌ ¡Solo administradores y propietario pueden crear zonas!"); return
            zone_name = msg[9:].strip()
            if not zone_name: await send_response("❌ Usa: !addzone [nombre]"); return
            users = (await self.highrise.get_room_users()).content
            user_position = next((pos for u, pos in users if u.id == user_id), None)
            if user_position:
                if isinstance(user_position, Position):
                    TELEPORT_POINTS[zone_name] = {"x": user_position.x, "y": user_position.y, "z": user_position.z}
                elif isinstance(user_position, AnchorPosition) and user_position.offset:
                    TELEPORT_POINTS[zone_name] = {"x": user_position.offset.x, "y": user_position.offset.y, "z": user_position.offset.z}
                else:
                    await send_response("❌ Error obteniendo posición")
                    return
                save_leaderboard_data()
                self.save_data()
                await send_response( f"🗺️ Zona '{zone_name}' creada en posición ({TELEPORT_POINTS[zone_name]['x']}, {TELEPORT_POINTS[zone_name]['y']}, {TELEPORT_POINTS[zone_name]['z']})")
            else: await send_response("❌ Error obteniendo posición")
            return

        # Comando !vip @user (Admin/Owner)
        if msg.startswith("!vip "):
            if not (self.is_admin(user_id) or user_id == OWNER_ID): await send_response("❌ ¡Solo administradores y propietario pueden dar VIP!"); return
            target_username = msg[5:].strip().replace("@", "")
            users = (await self.highrise.get_room_users()).content
            target_found = False
            target_user_id = None
            for u, pos in users:
                if u.username == target_username:
                    target_found = True
                    target_user_id = u.id
                    break
            if target_found:
                VIP_USERS.add(target_username)
                self.save_data()
                await send_response( f"⭐ @{target_username} ahora es VIP!")
                if target_user_id: await self.highrise.send_whisper(target_user_id, f"🎉 ¡Felicitaciones! Ahora eres VIP gracias a @{user.username}")
            else: await send_response( f"❌ Usuario {target_username} no encontrado en la sala")
            return

    async def auto_msg_loop(self, message: str, interval: int):
        """Bucle de mensajes automáticos personalizados"""
        try:
            while True:
                # El bucle persistirá a menos que la tarea sea cancelada explícitamente
                # por self.auto_msg_task.cancel() en !auto o !stopauto
                await self.highrise.chat(message)
                log_event("AUTO", f"Mensaje automático enviado: {message}")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            log_event("AUTO", "Bucle de mensaje automático detenido por solicitud")
        except Exception as e:
            log_event("ERROR", f"Error en auto_msg_loop: {e}")
            # Si hay un error, esperamos un poco y reintentamos para que no se detenga
            await asyncio.sleep(5)
            try:
                self.auto_msg_task = asyncio.create_task(self.auto_msg_loop(message, interval))
            except:
                pass

    async def on_user_move(self, user_id: str, pos: Position | AnchorPosition) -> None:
        """Manejador de movimiento de usuarios"""
        pass

    async def on_whisper(self, user: User, message: str) -> None:
        """Manejador de mensajes privados"""
        msg = message.strip()
        user_id = user.id
        username = user.username
        USER_NAMES[user_id] = username
        
        # Procesar otros comandos por DM si es necesario
        pass

    async def on_chat(self, user: User, message: str) -> None:
        """Manejador de mensajes públicos"""
        msg = message.strip()
        user_id = user.id
        username = user.username

        USER_NAMES[user_id] = username

        # GUARDAR CONVERSACIÓN (Chat Público y Susurros)
        # El bot no debe guardar los usuarios que hablen por susurro o chat público (por solicitud)
        # log_event("CHAT_HISTORY", f"[{username} ({user_id})]: {message}")

        # PROTECCIÓN DEL BOT (Chat Público y Susurros)
        # Detectar si intentan hacerle un emote mutuo al bot
        # El mensaje de emote mutuo suele ser "EmoteName @Target" o similar
        parts_msg = msg.split()
        if len(parts_msg) >= 2 and any(p.startswith("@") for p in parts_msg) and not msg.startswith("!"):
            # Buscar cuál de las partes es la mención
            target_mention = next((p for p in parts_msg if p.startswith("@")), "")
            target_username = target_mention.replace("@", "").lower()
            
            # Solo activar protección si se menciona específicamente al bot por ID o nombre reservado
            is_bot = target_username == BOT_ID.lower() or any(name == target_username for name in ["bot", "glux", "highrise"])
            if is_bot:
                await self.highrise.send_emote("emote-death", user.id)
                responses = [
                    "💀 ¡Ni lo intentes @{user.username}! No soy tu marioneta.",
                    "👻 ¿Intentas bailar con un fantasma @{user.username}? ¡Buen intento!",
                    "⚰️ ¡Zzz... no estoy disponible para bailes @{user.username}!",
                    "🛡️ Mi sistema rechaza invitaciones de baile externas @{user.username}.",
                    "⚡ ¡Error @{user.username}! No tengo articulaciones para ese emote."
                ]
                # Siempre responder públicamente para protección
                await self.highrise.chat(random.choice(responses).format(user=user))
                return

        # COMANDOS DE ADMINISTRACIÓN Y PROPIETARIO
        if msg.startswith("!ancla") and (user_id == OWNER_ID or user_id in ADMIN_IDS):
            global IS_ANCHORED, ANCHOR_POSITION
            try:
                # Obtener la posición actual del usuario que envía el comando
                room_users = await self.highrise.get_room_users()
                user_pos = None
                for u, pos in room_users.content:
                    if u.id == user_id:
                        user_pos = pos
                        break
                
                if user_pos and isinstance(user_pos, Position):
                    IS_ANCHORED = True
                    ANCHOR_POSITION = user_pos
                    # Teletransportar al bot a esa posición
                    await self.highrise.teleport(BOT_ID, user_pos)
                    await self.highrise.chat(f"⚓ ¡Anclado con éxito en {user_pos.x}, {user_pos.y}, {user_pos.z}! Solo me moveré si me reinician.")
                    log_event("ADMIN", f"Bot anclado por {username} en {user_pos}")
                else:
                    await self.highrise.send_whisper(user_id, "❌ No pude obtener tu posición para anclarme.")
            except Exception as e:
                await self.highrise.send_whisper(user_id, f"❌ Error al anclar: {e}")
            return

        # EMOTES POR PALABRAS CLAVE - Activar automáticamente para TODOS
        # Procesamos ANTES de cualquier otra lógica
        keyword_emotes = {
            "relajado": "sit-open", "dormir": "idle-floorsleeping", "triste": "idle-sad", "feliz": "emote-pose8",
            "zombie": "idle_zombie", "flotar": "emote-ghost-idle", "bailar": "dance-gangnamstyle", "dab": "emote-dab",
            "saludo": "emoji-hello", "aplauso": "emoji-clapping", "pensar": "emote-think", "llorar": "emoji-crying",
            "enojado": "idle-angry", "nervioso": "idle-nervous", "confundido": "emote-confused", "reposar": "sit-relaxed",
            "cansado": "idle-loop-tired", "uwu": "idle-uwu", "asustado": "emote-panic", "aburrido": "idle-loop-sad",
            "lindo": "emote-cute", "tiktok": "dance-tiktok11", "salto": "emote-jumpb", "risas": "emote-rofl",
            "posh": "idle-posh", "tímido": "emote-shy", "vergüenza": "emote-shy2", "sorpresa": "emote-pose6",
            "miedo": "emote-panic", "arrogancia": "emoji-arrogance", "rendirse": "emoji-give-up", "fireball": "emoji-hadoken",
            "levita": "emoji-halo", "mentir": "emoji-lying", "travieso": "emoji-naughty", "apestoso": "emoji-poop",
            "rezar": "emoji-pray", "golpe": "emoji-punch", "enfermo": "emoji-sick", "burla": "emoji-smirking",
            "estornudo": "emoji-sneeze", "apuntar": "emoji-there", "colapso": "emote-death2", "disco": "emote-disco",
            "fantasma": "emote-ghost-idle", "voltereta": "emote-handstand", "patada": "emote-kicking", "pánico": "emote-panic",
            "splits": "emote-splitsdrop", "beisbol": "emote-baseball", "abucheo": "emote-boo", "saltar": "emote-bunnyhop",
            "muerte": "emote-death", "codo": "emote-elbowbump", "caída": "emote-fail1", "torpe": "emote-fail2",
            "desmayo": "emote-fainting", "abrazo": "emote-hugyourself", "jetpack": "emote-jetpack", "karate": "emote-judochop",
            "carcajada": "emote-laughing2", "nivel": "emote-levelup", "ninjarun": "emote-ninjarun", "paz": "emoji-peace",
            "peekaboo": "emote-peekaboo", "propuesta": "emote-proposing", "arcoiris": "emote-rainbow", "robot": "emote-robot",
            "rodar": "emote-roll", "cuerda": "emote-ropepull", "apretón": "emote-secrethandshake", "sumo": "emote-sumo",
            "superpuño": "emote-superpunch", "supercarrera": "emote-superrun", "teatro": "emote-theatrical", "alas": "emote-wings",
            "frustrado": "emote-frustrated", "siesta": "idle-floorsleeping", "héroe": "idle-hero", "meditación": "idle-lookup",
            "elegante": "idle-posh", "tap": "idle-loop-tapdance", "dormilón": "idle-sleep", "peleador": "idle-fighter",
            "renegade": "idle-dance-tiktok7", "palmada": "emote-facepalm", "latido": "idle-dance-headbobbing",
            "beso": "emote-kissing", "lanzar": "emote-launch", "atencion": "emote-salute", "aeroguitar": "idle-guitar",
            "gazing": "emote-stargazer", "ditzy": "emote-pose9", "fashion": "emote-fashionista", "helado": "dance-icecream",
            "diciendo": "idle-dance-tiktok4", "astronauta": "emote-astronaut", "punk": "emote-punkguitar", "gravedad": "emote-gravity",
            "hermoso": "emote-pose5", "casual": "idle-dance-casual", "guiño": "emote-pose1", "pelear": "emote-pose3",
            "codicia": "emote-greedy", "viral": "dance-tiktok9", "raro": "dance-weird", "shuffle": "dance-tiktok10",
            "arcada": "emoji-gagging", "elevar": "emoji-celebrate", "salvaje": "dance-tiktok8", "blackpink": "dance-blackpink",
            "modelo": "emote-model", "ahora": "dance-tiktok2", "pennywise": "dance-pennywise", "reverencia": "emote-bow",
            "ruso": "dance-russian", "cortesia": "emote-curtsy", "bola": "emote-snowball", "caliente": "emote-hot",
            "nieve": "emote-snowangel", "cargando": "emote-charging", "compras": "dance-shoppingcart", "telekinesis": "emote-telekinesis",
            "flotante": "emote-float", "teleportando": "emote-teleporting", "espada": "emote-swordfight", "maniaco": "emote-maniac",
            "energia": "emote-energyball", "gusano": "emote-snake", "cantando": "idle_singing", "rana": "emote-frog",
            "macarena": "dance-macarena", "miningfail": "mining-fail", "fishingpull": "fishing-pull", "onda": "dance-thewave",
            "aspero": "emote-rough", "fishingidle": "fishing-idle", "soltar": "emote-dropped", "miningsuccess": "mining-success",
            "recibir": "emote-receive-happy", "frio": "emote-cold", "fishingcast": "fishing-cast", "sentarse": "emote-sit",
            "cansancio": "idle-loop-tired", "cadera": "dance-hipshake", "fruity": "dance-fruity", "animadora": "dance-cheerleader",
            "magnetico": "dance-tiktok14", "aullido": "emote-howl", "luna": "idle-howl", "trampolin": "emote-trampoline",
            "laidback": "sit-open", "encoger": "emote-shrink", "titere": "emote-puppet", "flexiones": "dance-aerobics",
            "pato": "dance-duckwalk", "manos": "dance-handsup", "rock": "dance-metal", "naranja": "dance-orangejustice",
            "dama": "dance-singleladies", "smoothwalk": "dance-smoothwalk", "vogue": "dance-voguehands", "timejump": "emote-timejump",
            "rascado": "idle-wild", "celebracion": "emote-celebrationstep", "pinguino": "dance-pinguin", "boxeador": "emote-boxer",
            "patinaje": "emote-iceskating", "hielo": "emote-iceskating", "revoloteo": "emote-looping", "flotador": "idle-floating",
            "trineo": "emote-sleigh", "emocionado": "emote-hyped", "jingle": "dance-jinglebell", "bano": "idle-toilet",
            "entusiasmo": "idle-enthusiastic", "animar": "emote-celebrate", "arabesco": "emote-pose10", "revelacion": "emote-headblowup",
            "espeluznante": "emote-creepycute", "creepy": "dance-creepypuppet", "desfile": "dance-anime", "titiritero": "dance-creepypuppet",
            "eyeroll": "emoji-eyeroll", "moonwalk": "dance-moonwalk", "happy": "emote-happy", "acurrucado": "idle-floorsleeping",
            "ponderando": "idle-lookup", "hug": "emote-hug",
            "balance": "emote-looping", "hada": "idle-floating", "cohete": "emote-launch", "saludo2": "emote-cutesalute",
            "atencion2": "emote-salute", "besito": "emote-kissing", "empuje": "dance-employee", "regalo": "emote-gift",
            "toque": "dance-touch", "kawaii": "dance-kawai", "descanso": "sit-relaxed", "trineo2": "emote-sleigh",
            "animado": "emote-hyped", "jingle2": "dance-jinglebell", "banito": "idle-toilet", "salto2": "emote-timejump",
            "nervios": "idle-nervous", "hielo2": "emote-iceskating", "fiesta": "emote-celebrate", "arabesco2": "emote-pose10",
            "tímido2": "emote-shy2", "revelacion2": "emote-headblowup", "acecho": "emote-creepycute", "marioneta": "dance-creepypuppet",
            "anime": "dance-anime", "sorpresa2": "emote-pose6", "celebracion2": "emote-celebrationstep", "pinguino2": "dance-pinguin",
            "boxer": "emote-boxer", "aire": "idle-guitar", "mirar": "emote-stargazer", "ditzy": "emote-pose9",
            "fashion2": "emote-fashionista", "helado2": "dance-icecream", "zombi2": "idle_zombie", "astronauta2": "emote-astronaut",
            "punk2": "emote-punkguitar", "gravedad2": "emote-gravity", "hermoso2": "emote-pose5", "casual2": "idle-dance-casual",
            "pelea": "emote-pose3", "monada": "emote-cute", "lindo2": "emote-cutey", "shuffledance": "dance-shuffle",
            "recibirtriste": "emote-receive-sad", "tristeza": "idle-sad", "asentir": "emoji-nod", "pulgar": "emoji-thumbsup",
            "fallo": "mining-fail", "tímido3": "emote-shy", "pesca": "fishing-pull", "aspero2": "emote-rough",
            "pescando": "fishing-idle", "soltar2": "emote-dropped", "exito": "mining-success", "frio2": "emote-cold",
            "lanzarpesca": "fishing-cast", "fruity": "dance-fruity", "animadora2": "dance-cheerleader", "nocturno": "emote-howl",
            "luna2": "idle-howl", "trampolin2": "emote-trampoline", "atencion3": "emote-attention", "laidback2": "sit-open",
            "encoger2": "emote-shrink", "titere2": "emote-puppet", "flexion": "dance-aerobics", "pato2": "dance-duckwalk",
            "manos2": "dance-handsup", "rock2": "dance-metal", "naranja2": "dance-orangejustice", "anillo": "dance-singleladies",
            "vogue2": "dance-voguehands", "arrogancia2": "emoji-arrogance", "hadoken": "emoji-hadoken", "levitar": "emoji-halo",
            "mentiroso": "emoji-lying", "picante": "emoji-naughty", "caca": "emoji-poop", "rezar2": "emoji-pray",
            "golpe2": "emoji-punch", "enfermo2": "emoji-sick", "sonrisa": "emoji-smirking", "estornudo2": "emoji-sneeze",
            "punto": "emoji-there", "colapso2": "emote-death2", "disco2": "emote-disco", "parada": "emote-handstand",
            "superpatada": "emote-kicking", "panico2": "emote-panic", "abierta": "emote-splitsdrop", "atento": "idle_layingdown",
            "relajado2": "idle_layingdown2", "roto": "emote-apart", "homerun": "emote-baseball", "boo2": "emote-boo",
            "conejo": "emote-bunnyhop", "resurreccion": "emote-death", "desmayo2": "emote-deathdrop", "codo2": "emote-elbowbump",
            "caida1": "emote-fail1", "caida2": "emote-fail2", "desvanecer": "emote-fainting", "autoabrazo": "emote-hugyourself",
            "jetpack2": "emote-jetpack", "judo": "emote-judochop", "salto3": "emote-jumpb", "divertido": "emote-laughing2",
            "subir": "emote-levelup", "monstruo": "emote-monster_fail", "fiebre": "idle-dance-headbobbing", "ninjarun2": "emote-ninjarun",
            "paz2": "emoji-peace", "peekaboo2": "emote-peekaboo", "boda": "emote-proposing", "arcoiris2": "emote-rainbow",
            "robot2": "emote-robot", "rofl": "emote-rofl", "rodar2": "emote-roll", "tiron": "emote-ropepull",
            "secreto": "emote-secrethandshake", "sumo2": "emote-sumo", "supergolpe": "emote-superpunch", "superrun": "emote-superrun",
            "teatral": "emote-theatrical", "alas2": "emote-wings", "irritado": "emote-frustrated", "siesta2": "idle-floorsleeping",
            "siesta3": "idle-floorsleeping2", "heroe": "idle-hero", "ponderar": "idle-lookup", "posh2": "idle-posh",
            "puchero": "idle-sad", "gangnam": "dance-gangnamstyle", "lloro": "emoji-crying", "sexy": "dance-sexy",
            "eyeroll2": "emoji-eyeroll", "luchador": "idle-fighter", "renegade2": "idle-dance-tiktok7", "palmada2": "emote-facepalm",
            "ritmo": "idle-dance-headbobbing", "feliz2": "emote-pose8", "abrazo2": "emote-hug", "bofetada": "emote-slap",
            "puñetazo": "emoji-punch", "puño": "emoji-punch", "aplauso2": "emoji-clapping", "exasperado": "emote-exasperated", "besos": "emote-kissing-passionate", "tapdance": "emote-tapdance",
            "chupar": "emote-suckthumb", "harlem": "dance-harlemshake", "dedos": "emote-heartfingers", "aerobics": "idle-loop-aerobics",
            "forma": "emote-heartshape", "ojos": "emote-hearteyes", "karma": "dance-wild", "jadeo": "emoji-scared",
            "pensar2": "emote-think", "aturdido": "emoji-dizzy", "avergonzado": "emote-embarrassed", "desaparecer": "emote-disappear",
            "molesto": "idle-loop-annoyed", "zombidance": "dance-zombie", "chillin": "idle-loop-happy", "frustrado2": "emote-frustrated",
            "triste2": "idle-loop-sad", "fantasma2": "emoji-ghost", "explotar": "emoji-mind-blown"
        }
        
        msg_lower = msg.lower().strip()
        emote_activated = False
        for keyword, emote_id in keyword_emotes.items():
            # Solo activar si el mensaje es exactamente la palabra clave (sin otro texto)
            if msg_lower == keyword:
                # Restricción: solo para VIP+
                if not (self.is_vip_by_username(username) or self.is_admin(user_id) or user_id == OWNER_ID):
                    await self.highrise.send_whisper(user_id, "🛑Acceso denegado.\nPermisos requeridos: “VIP”")
                    return

                asyncio.create_task(self.send_emote_loop(user_id, emote_id))
                await self.highrise.send_whisper(user_id, f"🎭 Bucle [{keyword}] emote.\nEscriba 'stop' - para cancelar🛑.")
                safe_print(f"🎭 {username} activó emote automático: {keyword}")
                emote_activated = True
                break
        
        # Si se activó un emote, no procesar más
        if emote_activated:
            return

        # Detectar mención al bot secundario
        if "@secundario_BOT" in msg or "@secundario" in msg.lower():
            await asyncio.sleep(0.3)
            await self.highrise.send_whisper(user_id, "📞 Llamando a la barra...")
            log_event("CALL", f"{username} mencionó al bot secundario")
            # El bot secundario responderá automáticamente con sistema extendido
            return

        # Detectar si mencionan al bot
        is_bot_mention = False
        treat_as_whisper = False
        if f"@{BOT_ID}" in msg or "@bot" in msg.lower():
            is_bot_mention = True
            treat_as_whisper = True
            msg = msg.replace(f"@{BOT_ID}", "").replace("@bot", "").strip()

        log_event("CHAT", f"[PUBLIC] {username}: {message}" + (" [BOT_MENTION]" if is_bot_mention else ""))

        if is_bot_mention:
            # NO usar whisper ni chat si ya tenemos un sistema de respuesta privado
            if not msg or msg.isspace():
                await self.highrise.send_whisper(user_id, f"👋 ¡Hola @{username}! Me mencionaste. Usa !help en privado para ver comandos.")
                return

        if self.is_banned(user_id) or self.is_muted(user_id):
            return

        self.update_activity(user_id)
        await self.handle_command(user, msg, is_whisper=treat_as_whisper)

    async def on_whisper(self, user: User, message: str) -> None:
        """Manejador de susurros"""
        msg = message.strip()
        user_id = user.id
        username = user.username

        USER_NAMES[user_id] = username

        if self.is_banned(user_id) or self.is_muted(user_id):
            return

        self.update_activity(user_id)
        log_event("WHISPER", f"{username}: {message}")

        # Procesar palabras clave de emotes también en susurros
        msg_lower = msg.lower().strip()
        keyword_emotes = {
            "relajado": "sit-open", "dormir": "idle-floorsleeping", "triste": "idle-sad", "feliz": "emote-pose8",
            "zombie": "idle_zombie", "flotar": "emote-ghost-idle", "bailar": "dance-gangnamstyle", "dab": "emote-dab",
            "saludo": "emoji-hello", "aplauso": "emoji-clapping", "pensar": "emote-think", "llorar": "emoji-crying",
            "enojado": "idle-angry", "nervioso": "idle-nervous", "confundido": "emote-confused", "reposar": "sit-relaxed",
            "cansado": "idle-loop-tired", "uwu": "idle-uwu", "asustado": "emote-panic", "aburrido": "idle-loop-sad",
            "lindo": "emote-cute", "tiktok": "dance-tiktok11", "salto": "emote-jumpb", "risas": "emote-rofl",
            "posh": "idle-posh", "tímido": "emote-shy", "vergüenza": "emote-shy2", "sorpresa": "emote-pose6",
            "miedo": "emote-panic", "arrogancia": "emoji-arrogance", "rendirse": "emoji-give-up", "fireball": "emoji-hadoken",
            "levita": "emoji-halo", "mentir": "emoji-lying", "travieso": "emoji-naughty", "apestoso": "emoji-poop",
            "rezar": "emoji-pray", "golpe": "emoji-punch", "enfermo": "emoji-sick", "burla": "emoji-smirking",
            "estornudo": "emoji-sneeze", "apuntar": "emoji-there", "colapso": "emote-death2", "disco": "emote-disco",
            "fantasma": "emote-ghost-idle", "voltereta": "emote-handstand", "patada": "emote-kicking", "pánico": "emote-panic",
            "splits": "emote-splitsdrop", "beisbol": "emote-baseball", "abucheo": "emote-boo", "saltar": "emote-bunnyhop",
            "muerte": "emote-death", "codo": "emote-elbowbump", "caída": "emote-fail1", "torpe": "emote-fail2",
            "desmayo": "emote-fainting", "abrazo": "emote-hugyourself", "jetpack": "emote-jetpack", "karate": "emote-judochop",
            "carcajada": "emote-laughing2", "nivel": "emote-levelup", "ninjarun": "emote-ninjarun", "paz": "emoji-peace",
            "peekaboo": "emote-peekaboo", "propuesta": "emote-proposing", "arcoiris": "emote-rainbow", "robot": "emote-robot",
            "rodar": "emote-roll", "cuerda": "emote-ropepull", "apretón": "emote-secrethandshake", "sumo": "emote-sumo",
            "superpuño": "emote-superpunch", "supercarrera": "emote-superrun", "teatro": "emote-theatrical", "alas": "emote-wings",
            "frustrado": "emote-frustrated", "siesta": "idle-floorsleeping", "héroe": "idle-hero", "meditación": "idle-lookup",
            "elegante": "idle-posh", "tap": "idle-loop-tapdance", "dormilón": "idle-sleep", "peleador": "idle-fighter",
            "renegade": "idle-dance-tiktok7", "palmada": "emote-facepalm", "latido": "idle-dance-headbobbing",
            "palmada": "emote-facepalm", "beso": "emote-kissing", "lanzar": "emote-launch", "atencion": "emote-salute", "aeroguitar": "idle-guitar",
            "gazing": "emote-stargazer", "ditzy": "emote-pose9", "fashion": "emote-fashionista", "helado": "dance-icecream",
            "diciendo": "idle-dance-tiktok4", "astronauta": "emote-astronaut", "punk": "emote-punkguitar", "gravedad": "emote-gravity",
            "hermoso": "emote-pose5", "casual": "idle-dance-casual", "guiño": "emote-pose1", "pelear": "emote-pose3",
            "codicia": "emote-greedy", "viral": "dance-tiktok9", "raro": "dance-weird", "shuffle": "dance-tiktok10",
            "arcada": "emoji-gagging", "elevar": "emoji-celebrate", "salvaje": "dance-tiktok8", "blackpink": "dance-blackpink",
            "modelo": "emote-model", "ahora": "dance-tiktok2", "pennywise": "dance-pennywise", "reverencia": "emote-bow",
            "ruso": "dance-russian", "cortesia": "emote-curtsy", "bola": "emote-snowball", "caliente": "emote-hot",
            "nieve": "emote-snowangel", "cargando": "emote-charging", "compras": "dance-shoppingcart", "telekinesis": "emote-telekinesis",
            "flotante": "emote-float", "teleportando": "emote-teleporting", "espada": "emote-swordfight", "maniaco": "emote-maniac",
            "energia": "emote-energyball", "gusano": "emote-snake", "cantando": "idle_singing", "rana": "emote-frog",
            "macarena": "dance-macarena", "miningfail": "mining-fail", "fishingpull": "fishing-pull", "onda": "dance-thewave",
            "aspero": "emote-rough", "fishingidle": "fishing-idle", "soltar": "emote-dropped", "miningsuccess": "mining-success",
            "recibir": "emote-receive-happy", "frio": "emote-cold", "fishingcast": "fishing-cast", "sentarse": "emote-sit",
            "cansancio": "idle-loop-tired", "cadera": "dance-hipshake", "fruity": "dance-fruity", "animadora": "dance-cheerleader",
            "magnetico": "dance-tiktok14", "aullido": "emote-howl", "luna": "idle-howl", "trampolin": "emote-trampoline",
            "laidback": "sit-open", "encoger": "emote-shrink", "titere": "emote-puppet", "flexiones": "dance-aerobics",
            "pato": "dance-duckwalk", "manos": "dance-handsup", "rock": "dance-metal", "naranja": "dance-orangejustice",
            "dama": "dance-singleladies", "smoothwalk": "dance-smoothwalk", "vogue": "dance-voguehands", "timejump": "emote-timejump",
            "rascado": "idle-wild", "celebracion": "emote-celebrationstep", "pinguino": "dance-pinguin", "boxeador": "emote-boxer",
            "patinaje": "emote-iceskating", "hielo": "emote-iceskating", "revoloteo": "emote-looping", "flotador": "idle-floating",
            "trineo": "emote-sleigh", "emocionado": "emote-hyped", "jingle": "dance-jinglebell", "bano": "idle-toilet",
            "entusiasmo": "idle-enthusiastic", "animar": "emote-celebrate", "arabesco": "emote-pose10", "revelacion": "emote-headblowup",
            "espeluznante": "emote-creepycute", "creepy": "dance-creepypuppet", "desfile": "dance-anime", "titiritero": "dance-creepypuppet",
            "eyeroll": "emoji-eyeroll", "moonwalk": "dance-moonwalk", "happy": "emote-happy", "acurrucado": "idle-floorsleeping",
            "ponderando": "idle-lookup", "hug": "emote-hug",
            "balance": "emote-looping", "hada": "idle-floating", "cohete": "emote-launch", "saludo2": "emote-cutesalute",
            "atencion2": "emote-salute", "besito": "emote-kissing", "empuje": "dance-employee", "regalo": "emote-gift",
            "toque": "dance-touch", "kawaii": "dance-kawai", "descanso": "sit-relaxed", "trineo2": "emote-sleigh",
            "animado": "emote-hyped", "jingle2": "dance-jinglebell", "banito": "idle-toilet", "salto2": "emote-timejump",
            "nervios": "idle-nervous", "hielo2": "emote-iceskating", "fiesta": "emote-celebrate", "arabesco2": "emote-pose10",
            "tímido2": "emote-shy2", "revelacion2": "emote-headblowup", "acecho": "emote-creepycute", "marioneta": "dance-creepypuppet",
            "anime": "dance-anime", "sorpresa2": "emote-pose6", "celebracion2": "emote-celebrationstep", "pinguino2": "dance-pinguin",
            "boxer": "emote-boxer", "aire": "idle-guitar", "mirar": "emote-stargazer", "ditzy": "emote-pose9",
            "fashion2": "emote-fashionista", "helado2": "dance-icecream", "zombi2": "idle_zombie", "astronauta2": "emote-astronaut",
            "punk2": "emote-punkguitar", "gravedad2": "emote-gravity", "hermoso2": "emote-pose5", "casual2": "idle-dance-casual",
            "pelea": "emote-pose3", "monada": "emote-cute", "lindo2": "emote-cutey", "shuffledance": "dance-shuffle",
            "recibirtriste": "emote-receive-sad", "tristeza": "idle-sad", "asentir": "emoji-nod", "pulgar": "emoji-thumbsup",
            "fallo": "mining-fail", "tímido3": "emote-shy", "pesca": "fishing-pull", "aspero2": "emote-rough",
            "pescando": "fishing-idle", "soltar2": "emote-dropped", "exito": "mining-success", "frio2": "emote-cold",
            "lanzarpesca": "fishing-cast", "fruity": "dance-fruity", "animadora2": "dance-cheerleader", "nocturno": "emote-howl",
            "luna2": "idle-howl", "trampolin2": "emote-trampoline", "atencion3": "emote-attention", "laidback2": "sit-open",
            "encoger2": "emote-shrink", "titere2": "emote-puppet", "flexion": "dance-aerobics", "pato2": "dance-duckwalk",
            "manos2": "dance-handsup", "rock2": "dance-metal", "naranja2": "dance-orangejustice", "anillo": "dance-singleladies",
            "vogue2": "dance-voguehands", "arrogancia2": "emoji-arrogance", "hadoken": "emoji-hadoken", "levitar": "emoji-halo",
            "mentiroso": "emoji-lying", "picante": "emoji-naughty", "caca": "emoji-poop", "rezar2": "emoji-pray",
            "golpe2": "emoji-punch", "enfermo2": "emoji-sick", "sonrisa": "emoji-smirking", "estornudo2": "emoji-sneeze",
            "punto": "emoji-there", "colapso2": "emote-death2", "disco2": "emote-disco", "parada": "emote-handstand",
            "superpatada": "emote-kicking", "panico2": "emote-panic", "abierta": "emote-splitsdrop", "atento": "idle_layingdown",
            "relajado2": "idle_layingdown2", "roto": "emote-apart", "homerun": "emote-baseball", "boo2": "emote-boo",
            "conejo": "emote-bunnyhop", "resurreccion": "emote-death", "desmayo2": "emote-deathdrop", "codo2": "elbowbump",
            "caida1": "emote-fail1", "caida2": "emote-fail2", "desvanecer": "emote-fainting", "autoabrazo": "emote-hugyourself",
            "jetpack2": "emote-jetpack", "judo": "emote-judochop", "salto3": "emote-jumpb", "divertido": "emote-laughing2",
            "subir": "emote-levelup", "monstruo": "emote-monster_fail", "fiebre": "idle-dance-headbobbing", "ninjarun2": "emote-ninjarun",
            "paz2": "emoji-peace", "peekaboo2": "emote-peekaboo", "boda": "emote-proposing", "arcoiris2": "emote-rainbow",
            "robot2": "emote-robot", "rofl": "emote-rofl", "rodar2": "emote-roll", "tiron": "emote-ropepull",
            "secreto": "emote-secrethandshake", "sumo2": "emote-sumo", "supergolpe": "emote-superpunch", "superrun": "emote-superrun",
            "teatral": "emote-theatrical", "alas2": "emote-wings", "irritado": "emote-frustrated", "siesta2": "idle-floorsleeping",
            "siesta3": "idle-floorsleeping2", "heroe": "idle-hero", "ponderar": "idle-lookup", "posh2": "idle-posh",
            "puchero": "idle-sad", "gangnam": "dance-gangnamstyle", "lloro": "emoji-crying", "sexy": "dance-sexy",
            "eyeroll2": "emoji-eyeroll", "luchador": "idle-fighter", "renegade2": "idle-dance-tiktok7", "palmada2": "emote-facepalm",
            "ritmo": "idle-dance-headbobbing", "feliz2": "emote-pose8", "abrazo2": "emote-hug", "bofetada": "emote-slap",
            "puñetazo": "emoji-punch", "puño": "emoji-punch", "aplauso2": "emoji-clapping", "exasperado": "emote-exasperated", "besos": "emote-kissing-passionate", "tapdance": "emote-tapdance",
            "chupar": "emote-suckthumb", "harlem": "dance-harlemshake", "dedos": "emote-heartfingers", "aerobics": "idle-loop-aerobics",
            "forma": "emote-heartshape", "ojos": "emote-hearteyes", "karma": "dance-wild", "jadeo": "emoji-scared",
            "pensar2": "emote-think", "aturdido": "emoji-dizzy", "avergonzado": "emote-embarrassed", "desaparecer": "emote-disappear",
            "molesto": "idle-loop-annoyed", "zombidance": "dance-zombie", "chillin": "idle-loop-happy", "frustrado2": "emote-frustrated",
            "triste2": "idle-loop-sad", "fantasma2": "emoji-ghost", "explotar": "emoji-mind-blown"
        }

        emote_activated = False
        for keyword, emote_id in keyword_emotes.items():
            if msg_lower == keyword:
                if not (self.is_vip_by_username(username) or self.is_admin(user_id) or user_id == OWNER_ID):
                    await self.highrise.send_whisper(user_id, "🛑Acceso denegado.\nPermisos requeridos: “VIP”")
                    return

                asyncio.create_task(self.send_emote_loop(user_id, emote_id))
                await self.highrise.send_whisper(user_id, f"🎭 Bucle [{keyword}] emote.\nEscriba 'stop' - para cancelar🛑.")
                safe_print(f"🎭 {username} activó emote automático por susurro: {keyword}")
                emote_activated = True
                break

        if emote_activated:
            return

        await self.handle_command(user, msg, is_whisper=True)

    async def handle_dm_commands(self, user_id: str, conversation_id: str, message: str) -> None:
        """Manejador simplificado para comandos recibidos por DM"""
        msg = message.strip().lower()
        
        # Restricción para no suscriptores en DM
        if msg != "!sub" and user_id not in SUBSCRIBERS:
            try:
                await self.highrise.send_message(conversation_id, "⚠️ Debes estar suscrito para usar los comandos por DM. Usa !sub para suscribirte. ✅")
            except Exception as e:
                print(f"Error enviando aviso de suscripción a {user_id}: {e}")
            return

        # Obtener o crear objeto User
        username = USER_NAMES.get(user_id, f"User_{user_id[:5]}")
        user_obj = User(id=user_id, username=username)
        
        # Procesar a través del sistema de comandos existente
        await self.handle_command(user_obj, message.strip(), is_whisper=False, is_dm=True, conversation_id=conversation_id)

    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        """Manejador de mensajes DM independiente (Sin handle_command)"""
        safe_print(f"📨 [on_message] Notificación DM de {user_id}")
        
        # Obtener username actualizado del SDK para evitar nombres genéricos o desactualizados
        username = f"User_{user_id[:5]}"
        try:
            user_info_resp = await self.highrise.get_user_info(user_id)
            if not isinstance(user_info_resp, Error):
                username = user_info_resp.user.username
                USER_NAMES[user_id] = username
        except:
            username = USER_NAMES.get(user_id, username)
        
        # GUARDAR CONVERSACIÓN SIEMPRE
        if user_id not in ACTIVE_CONVERSATIONS or isinstance(ACTIVE_CONVERSATIONS[user_id], str):
            ACTIVE_CONVERSATIONS[user_id] = {"id": conversation_id, "username": username}
            save_user_conversations()
        else:
            # Actualizar si cambió algo
            if ACTIVE_CONVERSATIONS[user_id].get("id") != conversation_id or ACTIVE_CONVERSATIONS[user_id].get("username") != username:
                ACTIVE_CONVERSATIONS[user_id]["id"] = conversation_id
                ACTIVE_CONVERSATIONS[user_id]["username"] = username
                save_user_conversations()
        
        try:
            if is_new_conversation:
                try:
                    await self.highrise.join_conversation(conversation_id)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    safe_print(f"⚠️ Error uniéndose a conversación: {e}")

            response = await self.highrise.get_messages(conversation_id)
            if isinstance(response, Error) or not hasattr(response, 'messages') or not response.messages:
                return
            
            content = None
            for msg_data in response.messages:
                s_id = getattr(msg_data, 'sender_id', None) or (msg_data.sender.id if hasattr(msg_data, 'sender') else None)
                if s_id and str(s_id) == str(user_id):
                    content = getattr(msg_data, 'content', "").strip()
                    break
            
            if not content:
                return

            msg = content.lower().strip()
            safe_print(f"✅ DM de {user_id}: {content}")
            username = USER_NAMES.get(user_id, f"User_{user_id[:5]}")
            user_obj = User(id=user_id, username=username)

            # ===== COMANDOS DM INDEPENDIENTES (SIN HANDLE_COMMAND) =====
            # Guardar conversación si no es !sub y no está suscrito
            if msg != "!sub" and user_id not in SUBSCRIBERS:
                log_event("DM_HISTORY", f"DM de {username} ({user_id}) [No suscrito]: {content}")
                try:
                    await self.highrise.send_message(conversation_id, "⚠️ Debes estar suscrito para usar los comandos por DM. Usa !sub para suscribirte. ✅")
                except Exception as e:
                    print(f"Error enviando aviso de suscripción a {user_id}: {e}")
                return

            elif msg.startswith("!dm "):
                if not (self.is_admin(user_id) or user_id == OWNER_ID):
                    await self.highrise.send_message(conversation_id, "❌ Solo el Propietario o Administradores pueden usar !dm 🚫")
                    return
                
                dm_msg = content[4:].strip()
                if not dm_msg:
                    await self.highrise.send_message(conversation_id, "❌ Usa: !dm [mensaje]")
                    return
                
                # Usamos ACTIVE_CONVERSATIONS en lugar de SUBSCRIBERS
                target_conversations = []
                for uid, data in ACTIVE_CONVERSATIONS.items():
                    if isinstance(data, dict):
                        target_conversations.append(data.get("id"))
                    else:
                        target_conversations.append(data)
                
                target_conversations = [c for c in target_conversations if c]
                if not target_conversations:
                    await self.highrise.send_message(conversation_id, "ℹ️ No hay conversaciones activas registradas en user_conversations.json.")
                    return

                await self.highrise.send_message(conversation_id, f"⏳ Iniciando envío de mensaje a {len(target_conversations)} conversaciones...")
                
                count = 0
                for conv_id in target_conversations:
                    try:
                        await self.highrise.send_message(conv_id, dm_msg)
                        count += 1
                        await asyncio.sleep(1.0)
                    except Exception as e:
                        # Intentar limpiar si la conversación ya no es válida
                        for uid, cid in list(ACTIVE_CONVERSATIONS.items()):
                            if cid == conv_id:
                                del ACTIVE_CONVERSATIONS[uid]
                                break
                        continue
                
                await self.highrise.send_message(conversation_id, f"📩 Proceso finalizado. Se enviaron {count} mensajes exitosamente.")
                return

            elif msg == "!help":
                help_msg = "📖 Comandos DM:\n" \
                           "!info - Ver tus estadísticas\n" \
                           "!ping - Probar conexión\n" \
                           "!time - Ver hora\n" \
                           "!test - Evaluar tu outfit\n" \
                           "!uptime - Tiempo activo del bot\n" \
                           "!roominfo - Info de la sala\n" \
                           "!outfit - Ver lista de tu ropa\n" \
                           "!coinflip - Cara o cruz\n" \
                           "!random - Número aleatorio (1-100)\n" \
                           "!online - Usuarios en sala"
                if self.is_admin(user_id) or user_id == OWNER_ID:
                    help_msg += "\n\n🛡️ Comandos Admin:\n" \
                                "!kick @user - Expulsar\n" \
                                "!mute @user - Silenciar\n" \
                                "!unmute @user - Desilenciar\n" \
                                "!ban @user - Banear\n" \
                                "!unban @user - Desbanear\n" \
                                "!jail @user - Enviar a cárcel\n" \
                                "!unjail @user - Liberar\n" \
                                "!follow @user - Seguir\n" \
                                "!stop - Dejar de seguir\n" \
                                "!teleport @user x y z - Teletransportar"
                await self.highrise.send_message(conversation_id, help_msg)
                return
            
            elif msg == "!info":
                await self.show_user_info(user_obj, conversation_id=conversation_id)

            elif msg == "!test":
                # Aseguramos que usamos el nombre del usuario que envía el DM
                user_to_rate = username if username else f"User_{user_id[:5]}"
                rating = random.randint(1, 10)
                comments = [
                    "¡Ese outfit es espectacular! 🔥",
                    "Se nota el estilo, ¡muy bien! ✨",
                    "Interesante combinación, me gusta. 😎",
                    "Un clásico que nunca falla. 👍",
                    "¡Tienes mucha personalidad vistiendo! 💎",
                    "¡Vaya flow llevas hoy! 🌊",
                    "Me gusta mucho ese toque único. 🎨",
                    "¡Elegancia pura! 🎩",
                    "Un poco arriesgado, ¡pero funciona! ⚡",
                    "¡Definitivamente eres el alma de la sala! 🌟"
                ]
                comment = random.choice(comments)
                await self.highrise.send_message(conversation_id, f"⭐ Calificando el outfit de @{user_to_rate}...\n📊 Puntuación: {rating}/10\n💬 {comment}")

            elif msg.startswith("!auto "):
                if not (self.is_admin(user_id) or user_id == OWNER_ID):
                    await self.highrise.send_message(conversation_id, "❌ Solo el Propietario o Administradores pueden usar !auto 🚫")
                    return
                # Formato: !auto <mensaje> <segundos>
                parts = content.split(" ")
                if len(parts) >= 3:
                    try:
                        interval = int(parts[-1])
                        custom_msg = " ".join(parts[1:-1])
                        
                        if self.auto_msg_task:
                            self.auto_msg_task.cancel()
                        
                        self.auto_msg_task = asyncio.create_task(self.auto_msg_loop(custom_msg, interval))
                        await self.highrise.send_message(conversation_id, f"✅ Mensaje automático activado cada {interval}s 🤖✨")
                    except ValueError:
                        await self.highrise.send_message(conversation_id, "❌ Error: El tiempo debe ser un número en segundos ⏱️")
                else:
                    await self.highrise.send_message(conversation_id, "ℹ️ Uso: !auto <mensaje> <segundos> 📋💡")

            elif msg == "!stopauto" and (self.is_admin(user_id) or user_id == OWNER_ID):
                if self.auto_msg_task:
                    self.auto_msg_task.cancel()
                    self.auto_msg_task = None
                    await self.highrise.send_message(conversation_id, "🛑 Mensajes automáticos detenidos correctamente 🔇")
                else:
                    await self.highrise.send_message(conversation_id, "ℹ️ No hay mensajes automáticos activos 🤷‍♂️")

            elif msg == "!sub":
                is_vip_perm = self.is_vip(user_id) or self.is_admin(user_id) or user_id == OWNER_ID
                
                if user_id not in SUBSCRIBERS:
                    welcome_back = user_id in SUBSCRIBER_HISTORY
                    
                    # Guardar el mapeo de username a ID para que !invite @user funcione
                    username = USER_NAMES.get(user_id, f"User_{user_id[:5]}")
                    ACTIVE_CONVERSATIONS[user_id] = {"id": conversation_id, "username": username}
                    save_user_conversations()
                    
                    # Dar VIP por 24 horas solo si no es VIP permanente/admin y no lo ha recibido antes
                    if not is_vip_perm and user_id not in SUBSCRIBER_HISTORY:
                        expiration_date = datetime.now() + timedelta(hours=24)
                        if user_id not in USER_INFO: USER_INFO[user_id] = {}
                        USER_INFO[user_id]["vip_expires"] = expiration_date.isoformat()
                        save_user_info()
                        
                        # Anuncio en chat global (solo primera vez)
                        asyncio.create_task(self.highrise.chat(f"✅ @{username} se ha suscrito enviándome un mensaje a mi inbox..Ahora es vip 24 horas en la sala🎉"))
                    
                    SUBSCRIBERS.add(user_id)
                    SUBSCRIBER_HISTORY.add(user_id)
                    save_subscribers()
                    
                    try:
                        if is_vip_perm:
                            await self.highrise.send_message(conversation_id, f"✅ Suscripción activada. ¡Gracias por tu apoyo, {username}! 🌟")
                        elif welcome_back:
                            await self.highrise.send_message(conversation_id, f"Bienvenido de vuelta @{username} que te trae por aquí")
                        else:
                            await self.highrise.send_message(conversation_id, f"✅ Te has suscrito correctamente. 🎉 Ahora tienes VIP por 24h.")
                    except Exception as e:
                        print(f"Error confirmando suscripción a {user_id}: {e}")
                else:
                    try:
                        await self.highrise.send_message(conversation_id, "ℹ️ Ya estás suscrito.")
                    except Exception as e:
                        print(f"Error enviando ya suscrito a {user_id}: {e}")

            elif msg == "!unsub":
                if user_id in SUBSCRIBERS:
                    SUBSCRIBERS.remove(user_id)
                    save_subscribers()
                    try:
                        await self.highrise.send_message(conversation_id, "✅ Te has dado de baja correctamente. 👋")
                    except Exception as e:
                        print(f"Error confirmando baja a {user_id}: {e}")
                else:
                    try:
                        await self.highrise.send_message(conversation_id, "ℹ️ No estabas suscrito.")
                    except Exception as e:
                        print(f"Error enviando no suscrito a {user_id}: {e}")

            elif msg == "!ping":
                await self.highrise.send_message(conversation_id, "🏓 ¡Pong! El bot está activo y respondiendo.")

            elif msg == "!uptime":
                uptime = self.format_time(int(time.time() - self.start_time))
                await self.highrise.send_message(conversation_id, f"⏱️ Tiempo activo del bot: {uptime}")

            elif msg == "!roominfo":
                response = await self.highrise.get_room_users()
                user_count = len(response.content) if not isinstance(response, Error) else 0
                await self.highrise.send_message(conversation_id, f"🏠 Sala: NOCTURNO\n👤 Usuarios online: {user_count}\n🛡️ Admin: @NOCTURNO_ADMIN")

            elif msg == "!outfit":
                outfit = await self.highrise.get_user_outfit(user_id)
                if not isinstance(outfit, Error):
                    items = [item.id.split("-")[-1] for item in outfit.items[:10]]
                    await self.highrise.send_message(conversation_id, f"👕 Tu ropa (Top 10): {', '.join(items)}")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Error al obtener tu outfit.")

            elif msg.startswith("!kick ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                target_username = content[6:].strip().replace("@", "")
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    await self.highrise.moderate_user(target_user.id, "kick")
                    await self.highrise.send_message(conversation_id, f"👢 @{target_username} ha sido expulsado.")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Usuario no encontrado en la sala.")

            elif msg.startswith("!mute ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                target_username = content[6:].strip().replace("@", "")
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    self.mute_user(target_user.id, target_username)
                    await self.highrise.send_message(conversation_id, f"🔇 @{target_username} ha sido silenciado.")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Usuario no encontrado.")

            elif msg.startswith("!unmute ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                target_username = content[8:].strip().replace("@", "")
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    if target_user.id in MUTED_USERS:
                        del MUTED_USERS[target_user.id]
                        await self.highrise.send_message(conversation_id, f"🔊 @{target_username} ya puede hablar.")
                    else:
                        await self.highrise.send_message(conversation_id, "❌ El usuario no está silenciado.")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Usuario no encontrado.")

            elif msg.startswith("!ban ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                target_username = content[5:].strip().replace("@", "")
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    self.ban_user(target_user.id, target_username)
                    await self.highrise.moderate_user(target_user.id, "kick")
                    await self.highrise.send_message(conversation_id, f"🚫 @{target_username} ha sido baneado.")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Usuario no encontrado.")

            elif msg.startswith("!unban ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                target_username = content[7:].strip().replace("@", "")
                target_id = next((uid for uid, name in BANNED_USERS.items() if name.lower() == target_username.lower()), None)
                if target_id:
                    del BANNED_USERS[target_id]
                    await self.highrise.send_message(conversation_id, f"✅ @{target_username} ha sido desbaneado.")
                else:
                    await self.highrise.send_message(conversation_id, "❌ El usuario no está en la lista de baneados.")

            elif msg.startswith("!jail ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                target_username = content[6:].strip().replace("@", "")
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    if "carcel" in TELEPORT_POINTS:
                        p = TELEPORT_POINTS["carcel"]
                        await self.highrise.teleport(target_user.id, Position(p["x"], p["y"], p["z"]))
                        self.jail_users.add(target_user.id)
                        await self.highrise.send_message(conversation_id, f"⛓️ @{target_username} enviado a la cárcel.")
                    else:
                        await self.highrise.send_message(conversation_id, "❌ Punto 'carcel' no configurado.")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Usuario no encontrado.")

            elif msg.startswith("!unjail ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                target_username = content[8:].strip().replace("@", "")
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    if target_user.id in self.jail_users:
                        self.jail_users.remove(target_user.id)
                        if "spawn" in TELEPORT_POINTS:
                            p = TELEPORT_POINTS["spawn"]
                            await self.highrise.teleport(target_user.id, Position(p["x"], p["y"], p["z"]))
                        await self.highrise.send_message(conversation_id, f"🔓 @{target_username} liberado.")
                    else:
                        await self.highrise.send_message(conversation_id, "❌ El usuario no está en la cárcel.")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Usuario no encontrado.")

            elif msg.startswith("!follow ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                target_username = content[8:].strip().replace("@", "")
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    self.follow_target = target_user.id
                    await self.highrise.send_message(conversation_id, f"👣 Siguiendo a @{target_username}.")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Usuario no encontrado.")

            elif msg == "!stop" and (self.is_admin(user_id) or user_id == OWNER_ID):
                self.follow_target = None
                await self.highrise.send_message(conversation_id, "🛑 Siguiendo detenido.")

            elif msg.startswith("!teleport ") and (self.is_admin(user_id) or user_id == OWNER_ID):
                parts = content.split()
                if len(parts) >= 5:
                    t_username = parts[1].replace("@", "")
                    try:
                        tx, ty, tz = float(parts[2]), float(parts[3]), float(parts[4])
                        t_user = await self.get_user_by_username(t_username)
                        if t_user:
                            await self.highrise.teleport(t_user.id, Position(tx, ty, tz))
                            await self.highrise.send_message(conversation_id, f"🚀 @{t_username} teletransportado a {tx}, {ty}, {tz}")
                        else:
                            await self.highrise.send_message(conversation_id, "❌ Usuario no encontrado.")
                    except:
                        await self.highrise.send_message(conversation_id, "❌ Coordenadas inválidas.")

            elif msg == "!room" or msg.startswith("!room "):
                if not (self.is_admin(user_id) or user_id == OWNER_ID):
                    await self.highrise.send_message(conversation_id, "❌ Solo el Propietario o Administradores pueden usar !room.")
                    return
                
                parts = message.split()
                if len(parts) < 2:
                    await self.highrise.send_message(conversation_id, "❌ Uso: !room <room_id>")
                    return
                
                new_room_id = parts[1].strip()
                await self.highrise.send_message(conversation_id, f"🔄 Cambiando a la sala {new_room_id}... El bot se reiniciará.")
                
                try:
                    import json as json_lib
                    import os as os_lib
                    with open("config.json", "r", encoding="utf-8") as f:
                        config_data = json_lib.load(f)
                    
                    config_data["room_id"] = new_room_id
                    
                    with open("config.json", "w", encoding="utf-8") as f:
                        json_lib.dump(config_data, f, indent=4)
                        f.flush()
                        os_lib.fsync(f.fileno())
                    
                    await asyncio.sleep(2)
                    import sys as sys_lib
                    sys_lib.exit(0)
                except Exception as e:
                    await self.highrise.send_message(conversation_id, f"❌ Error: {e}")
                return

            elif msg == "!invite" or msg.startswith("!invite "):
                try:
                    parts = content.split()
                    if len(parts) < 2:
                        await self.highrise.send_message(conversation_id, "❌ Uso: !invite @usuario o !invite all")
                        return
                    
                    target = parts[1].replace("@", "")
                    
                    # Intentar obtener username actualizado para el remitente
                    inviter_username = username
                    try:
                        user_info_resp = await self.highrise.get_user_info(user_id)
                        if not isinstance(user_info_resp, Error):
                            inviter_username = user_info_resp.user.username
                            USER_NAMES[user_id] = inviter_username
                    except: pass
                    
                    # Intentar cargar room_id
                    try:
                        with open("config.json", "r") as f:
                            config_data = json.load(f)
                            room_id = config_data.get("room_id", "694a084d0bde2d163e1191d3")
                    except Exception:
                        room_id = "694a084d0bde2d163e1191d3"
                    
                    if target.lower() == "all":
                        if not (self.is_admin(user_id) or user_id == OWNER_ID):
                            await self.highrise.send_message(conversation_id, "❌ Solo administradores pueden usar !invite all.")
                            return
                        
                        # Obtener usuarios actuales en la sala para no invitarlos
                        room_users_response = await self.highrise.get_room_users()
                        users_in_room_ids = set()
                        if not isinstance(room_users_response, Error):
                            users_in_room_ids = {u.id for u, _ in room_users_response.content}

                        # Identificar a quién invitar (los que tienen conversación activa y NO están en la sala)
                        ids_to_invite = [uid for uid in list(ACTIVE_CONVERSATIONS.keys()) if uid not in users_in_room_ids]
                        
                        if not ids_to_invite:
                            await self.highrise.send_message(conversation_id, "ℹ️ No hay usuarios con conversaciones activas fuera de la sala para invitar.")
                            return

                        await self.highrise.send_message(conversation_id, f"⏳ Iniciando envío de {len(ids_to_invite)} invitaciones...")
                        
                        count = 0
                        for target_uid in ids_to_invite:
                            conv_data = ACTIVE_CONVERSATIONS.get(target_uid)
                            conv_id = conv_data.get("id") if isinstance(conv_data, dict) else conv_data
                            if not conv_id: continue

                            try:
                                # Mensaje único de invitación masiva (sin nombre de usuario)
                                await self.highrise.send_message(conv_id, f"👋 ¡Hola! Te invitamos a pasar un buen rato en la sala, ¡te esperamos! ✨\n🔗 Únete aquí: https://high.rs/room?id={room_id}")
                                count += 1
                                # Delay para evitar límites del SDK
                                await asyncio.sleep(1.0)
                            except Exception as invite_err:
                                safe_print(f"❌ Fallo al enviar invitación DM a {target_uid}: {invite_err}")
                                # Verificación de error de permisos o conversación cerrada
                                err_str = str(invite_err).lower()
                                if "forbidden" in err_str or "not_found" in err_str or "invalid" in err_str:
                                    if target_uid in ACTIVE_CONVERSATIONS: del ACTIVE_CONVERSATIONS[target_uid]
                        
                        await self.highrise.send_message(conversation_id, f"✉️ Proceso finalizado. Se enviaron {count} invitaciones exitosamente.")
                    else:
                        # Invitación individual
                        target_id = None
                        
                        # Buscar ID del usuario en ACTIVE_CONVERSATIONS por username guardado
                        for uid, data in ACTIVE_CONVERSATIONS.items():
                            if isinstance(data, dict) and data.get("username", "").lower() == target.lower():
                                target_id = uid
                                break
                        
                        if not target_id:
                            target_user = await self.get_user_by_username(target)
                            if target_user:
                                target_id = target_user.id
                            else:
                                # Último recurso: USER_NAMES
                                target_id = next((uid for uid, uname in USER_NAMES.items() if uname.lower() == target.lower()), None)

                        if not target_id:
                            await self.highrise.send_message(conversation_id, f"❌ Usuario @{target} no encontrado en registros.")
                            return

                        # Verificar si ya está en la sala
                        room_users_response = await self.highrise.get_room_users()
                        if not isinstance(room_users_response, Error):
                            if any(u.id == target_id for u, _ in room_users_response.content):
                                await self.highrise.send_message(conversation_id, f"ℹ️ @{target} ya se encuentra en la sala.")
                                return

                        conv_data = ACTIVE_CONVERSATIONS.get(target_id)
                        conv_id = conv_data.get("id") if isinstance(conv_data, dict) else conv_data
                        
                        # 1. Enviar mensaje personal si hay conversación
                        if conv_id:
                            try:
                                await self.highrise.send_message(conv_id, f"👤: @{inviter_username} te ha invitado a la sala, no tardes... 🎉", type="text")
                                await asyncio.sleep(0.5)
                            except: pass

                        # 1. Intentar invitación oficial del SDK (send_message con type='invite')
                        if conv_id:
                            try:
                                await self.highrise.send_message(conv_id, "¡Te invito a mi sala!", type="invite", room_id=room_id)
                                await self.highrise.send_message(conversation_id, f"✅ Invitación oficial (DM) enviada a @{target}.")
                                return
                            except Exception as official_err:
                                safe_print(f"⚠️ Error en invitación oficial DM a {target}: {official_err}")

                        # 2. Fallback final a enlace DM manual
                        if conv_id:
                            try:
                                await self.highrise.send_message(conv_id, f"🔗 ¡Únete aquí! https://high.rs/room?id={room_id}", type="text")
                                await self.highrise.send_message(conversation_id, f"✅ Invitación enviada por DM a @{target} (manual).")
                                return
                            except Exception as msg_err:
                                if any(err in str(msg_err).lower() for err in ["invalid", "not active", "not found"]):
                                    if target_id in ACTIVE_CONVERSATIONS: del ACTIVE_CONVERSATIONS[target_id]
                                await self.highrise.send_message(conversation_id, f"❌ Fallo al enviar DM a @{target}.")
                                return

                        # 3. Intentar invitación antigua del SDK (Si no hay conversación o fallaron los DMs)
                        try:
                            await self.highrise.invite(target_id)
                            await self.highrise.send_message(conversation_id, f"✅ Invitación oficial (SDK) enviada a @{target}.")
                            return
                        except Exception as invite_err:
                            safe_print(f"⚠️ Error en invitación real a {target}: {invite_err}")
                            await self.highrise.send_message(conversation_id, f"❌ @{target} no tiene conversación activa ni fue posible invitar por SDK.")
                except Exception as e:
                    safe_print(f"❌ Error en comando invite DM: {e}")
                    try: await self.highrise.send_message(conversation_id, "❌ Error al procesar la invitación.")
                    except: pass
                return

            elif msg == "!time":
                now = datetime.now().strftime("%H:%M:%S")
                await self.highrise.send_message(conversation_id, f"🕒 Hora actual del bot: {now}")

            elif msg == "!coinflip":
                result = random.choice(["Cara", "Cruz"])
                await self.highrise.send_message(conversation_id, f"🪙 Lanzando moneda... ¡Salió {result}!")

            elif msg == "!random":
                num = random.randint(1, 100)
                await self.highrise.send_message(conversation_id, f"🎲 Número aleatorio (1-100): {num}")

            # --- COMANDOS EXISTENTES REPLICADOS ---
            elif msg == "!stats":
                stats_message = f"📊 Estadísticas de sala:\n👥 Usuarios actuales: {len(USER_NAMES)}\n💖 Corazones totales: {sum(USER_HEARTS.values())}"
                await self.highrise.send_message(conversation_id, stats_message)

            elif msg == "!online":
                response = await self.highrise.get_room_users()
                if not isinstance(response, Error):
                    online_users = [u.username for u, _ in response.content]
                    await self.highrise.send_message(conversation_id, f"👥 Usuarios en línea ({len(online_users)}): {', '.join(online_users[:10])}...")

            elif msg.startswith("!wallet"):
                balance = await self.get_bot_wallet_balance()
                await self.highrise.send_message(conversation_id, f"💰 Balance de la billetera: {balance} oro")

            elif msg == "!role":
                role_info = self.get_user_role_info(user_obj)
                await self.highrise.send_message(conversation_id, f"🎭 {role_info}")

            elif "tipped" in msg.lower() or "oro" in msg.lower():
                # Ignorar notificaciones automáticas de propinas para no dar error
                return

            else:
                # Otros comandos específicos para DM pueden añadirse aquí
                await self.highrise.send_message(conversation_id, "❓ Comando no reconocido por DM.")
                
        except Exception as e:
            safe_print(f"❌ Error en on_message: {e}")

    async def on_user_join(self, user: User, position: Position | AnchorPosition) -> None:
        """Usuario entra a la sala"""
        user_id = user.id
        username = user.username

        USER_NAMES[user_id] = username
        self.update_user_info(user_id, username)

        USER_JOIN_TIMES[user_id] = time.time()
        USER_INFO[user_id]["time_joined"] = time.time()

        # Determinar emoji según rol
        role_emoji = "💫"  # Default / Invitado
        if user_id == OWNER_ID:
            role_emoji = "👑"
        elif self.is_admin(user_id):
            role_emoji = "🛡️"
        elif user_id in MODERATOR_IDS:
            role_emoji = "⚖️"
        elif self.is_vip(user_id):
            role_emoji = "💎"

        welcome_message = f"{role_emoji}Bienvenido @{username} a la sala ponte cómodo y disfruta al máximo{role_emoji}"
        
        # Enviar bienvenida solo por susurro privado con reintentos
        max_attempts = 3
        
        # Intentar obtener conversación de DM para bienvenida
        # Aunque el SDK recomienda on_message para obtener conversation_id, 
        # para una bienvenida inmediata usamos whisper que solo requiere el user_id.
        
        for attempt in range(1, max_attempts + 1):
            try:
                await asyncio.sleep(0.5 * attempt)  # Delay incremental para evitar rate limiting
                await self.highrise.send_whisper(user_id, welcome_message)
                safe_print(f"✅ Bienvenida enviada a {username} por susurro (intento {attempt})")
                break  # Éxito, salir del loop
            except Exception as e:
                if attempt < max_attempts:
                    safe_print(f"⚠️ Intento {attempt} fallido para {username}: {e}. Reintentando...")
                else:
                    safe_print(f"❌ Error enviando bienvenida a {username} después de {max_attempts} intentos: {e}")
                    log_event("WARNING", f"Fallo bienvenida a {username}: {e}")

    async def on_user_leave(self, user: User) -> None:
        """Usuario sale de la sala"""
        user_id = user.id

        if user_id in USER_JOIN_TIMES:
            join_time = USER_JOIN_TIMES[user_id]
            current_time = time.time()
            time_in_room = round(current_time - join_time)
            if user_id in USER_INFO:
                USER_INFO[user_id]["total_time_in_room"] += time_in_room
            del USER_JOIN_TIMES[user_id]

        await self.stop_emote_loop(user_id)
        save_user_info()

    async def on_tip(self, sender: User, receiver: User, tip: CurrencyItem | Item) -> None:
        """Manejador de propinas - Sistema VIP automático por donación"""
        global BOT_WALLET
        
        if receiver.id == self.bot_id:
            if isinstance(tip, CurrencyItem):
                tip_amount = tip.amount
                
                # Caso: Donación de exactamente 100 oro
                if tip_amount == 100:
                    if sender.username not in VIP_USERS:
                        VIP_USERS.add(sender.username)
                        self.save_data()
                        # Mensajes para NUEVO VIP
                        await self.highrise.chat(f"💰 ¡Recibí {tip_amount} de oro de (@{sender.username})!")
                        await self.highrise.chat(f"🌟 ¡@{sender.username} se ha unido al selecto club VIP con una donación de 100 oro! 🌟")
                        await self.highrise.send_whisper(sender.id, "✨ ¡BIENVENIDO AL CLUB VIP! ✨\nAhora tienes acceso permanente a zonas exclusivas y comandos especiales. ¡Gracias por tu apoyo!")
                        log_event("VIP", f"{sender.username} obtuvo VIP por donación de 100 oro")
                    else:
                        # Mensajes para VIP EXISTENTE que dona 100
                        await self.highrise.chat(f"💰 ¡Recibí {tip_amount} de oro de (@{sender.username})!")
                        await self.highrise.chat(f"💖 ¡Nuestro VIP @{sender.username} sigue apoyando la sala con 100 oro! 💖")
                        await self.highrise.send_whisper(sender.id, "💎 ¡Muchas gracias de nuevo! Tu generosa donación de 100 oro como VIP ayuda enormemente a mantener el bot activo.")
                        log_event("TIP", f"{sender.username} (VIP) donó 100 oro")
                else:
                    # Mensajes para OTRAS CANTIDADES
                    # 1. Agradecer en público (siempre)
                    await self.highrise.chat(f"💰 ¡Recibí {tip_amount} de oro de (@{sender.username})!")
                    
                    if sender.username in VIP_USERS:
                        # Caso VIP existente
                        await self.highrise.chat(f"💎 ¡Gracias por el apoyo continuo, @{sender.username}! 💎")
                        await self.highrise.send_whisper(sender.id, f"💖 ¡Mil gracias por donar {tip_amount} oro! Tu apoyo como VIP es fundamental para nosotros.")
                    else:
                        # Caso NO-VIP
                        # 2. Agradecer por DM (Bandeja de entrada)
                        # El bot recibe el aviso de oro por DM, por lo que ACTIVE_CONVERSATIONS ya tiene al usuario
                        if sender.id in ACTIVE_CONVERSATIONS:
                            await self.highrise.send_message(ACTIVE_CONVERSATIONS[sender.id], f"💰 ¡Muchas gracias por tu generosa donación de {tip_amount} oro!")
                        
                        # 3. Instrucción por Susurro (whisper en la sala)
                        await self.highrise.send_whisper(sender.id, "💡 RECUERDA: Si donas exactamente 100 oro, recibirás el rol VIP permanente de forma automática.")
                
                BOT_WALLET += tip_amount
                log_event("TIP", f"{sender.username} donó {tip_amount} oro al bot (Balance: {BOT_WALLET})")
            else:
                log_event("TIP", f"{sender.username} envió un item al bot (no oro)")
                await self.highrise.send_whisper(sender.id, "💝 ¡Gracias por el regalo!")

    async def on_emote(self, user: User, emote_id: str, receiver: User | None) -> None:
        """Manejador de emotes: Protección de emotes mutuos"""
        try:
            # PROTECCIÓN ESPECIAL para el BOT: Solo permitir si es el bot quien los inicia o si el ID es el del bot
            if receiver:
                if user.id != self.bot_id and receiver.id != self.bot_id:
                    return

            # Aquí iría la lógica normal de emotes si fuera necesaria
            pass
        except Exception as e:
            safe_print(f"❌ Error en on_emote: {e}")

    async def on_user_move(self, user: User, destination: Position | AnchorPosition) -> None:
        """Manejador de movimiento de usuario para flashmode automático y sistema anti-escape de cárcel
        Activa flashmode cuando el usuario sube o baja desde/hacia altura Y >= 10.0 bloques
        Previene que usuarios en la cárcel escapen teletransportándolos de vuelta
        """
        # SISTEMA DE ANCLA
        if user.id == BOT_ID and IS_ANCHORED and ANCHOR_POSITION:
            # Si el bot es movido (por un usuario o sistema) y está anclado, regresarlo
            if isinstance(destination, Position):
                if destination.x != ANCHOR_POSITION.x or destination.y != ANCHOR_POSITION.y or destination.z != ANCHOR_POSITION.z:
                    await self.highrise.teleport(BOT_ID, ANCHOR_POSITION)
                    return

        def _coords(p):
            return (p.x, p.y, p.z) if isinstance(p, Position) else None

        try:
            user_id = user.id
            username = user.username
            current_time = time.time()

            if not hasattr(self, 'flashmode_cooldown'): 
                self.flashmode_cooldown = {}

            # SISTEMA ANTI-ESCAPE DE CÁRCEL
            # Si el usuario está en la cárcel y NO es admin/owner, devolverlo a la cárcel
            if user_id in JAIL_USERS:
                is_admin_or_owner = (user_id == OWNER_ID or self.is_admin(user_id))
                
                if not is_admin_or_owner:
                    # Verificar si están intentando escapar de la cárcel
                    if "carcel" in TELEPORT_POINTS:
                        jail_point = TELEPORT_POINTS["carcel"]
                        dest_xyz = _coords(destination)
                        
                        if dest_xyz:
                            # Si intentan alejarse más de 3 bloques de la cárcel, devolverlos
                            distance_from_jail = ((dest_xyz[0] - jail_point["x"])**2 + 
                                                 (dest_xyz[1] - jail_point["y"])**2 + 
                                                 (dest_xyz[2] - jail_point["z"])**2)**0.5
                            
                            if distance_from_jail > 3.0:
                                # Devolverlos a la cárcel
                                jail_position = Position(jail_point["x"], jail_point["y"], jail_point["z"])
                                await self.highrise.teleport(user_id, jail_position)
                                await self.highrise.send_whisper(user_id, "⛓️ ¡No puedes escapar de la cárcel!\n⚠️ Solo un admin puede liberarte con !unjail")
                                safe_print(f"🔒 Intento de escape bloqueado: {username} devuelto a la cárcel")
                                log_event("JAIL", f"Intento de escape bloqueado: {username}")
                                return

            last_pos = self.user_positions.get(user_id)
            if not last_pos:
                self.user_positions[user_id] = destination
                return

            last_xyz = _coords(last_pos)
            dest_xyz = _coords(destination)

            if not last_xyz or not dest_xyz:
                self.user_positions[user_id] = destination
                return

            floor_change_threshold = 1.0
            y_change = abs(dest_xyz[1] - last_xyz[1])
            minimum_height = 10.0

            if y_change >= floor_change_threshold and (dest_xyz[1] >= minimum_height or last_xyz[1] >= minimum_height):
                cooldown_time = 3.0
                if user_id in self.flashmode_cooldown:
                    time_since_last = current_time - self.flashmode_cooldown[user_id]
                    if time_since_last < cooldown_time:
                        self.user_positions[user_id] = destination
                        return

                if not self.is_in_forbidden_zone(dest_xyz[0], dest_xyz[1], dest_xyz[2], user_id):
                    if isinstance(destination, Position):
                        await self.highrise.teleport(user_id, destination)
                        self.flashmode_cooldown[user_id] = current_time
                        direction = "subió" if dest_xyz[1] > last_xyz[1] else "bajó"
                        log_event("FLASHMODE", f"Auto-flashmode {username}: Y:{last_xyz[1]:.1f}→{dest_xyz[1]:.1f}")
                        safe_print(f"⚡ FLASHMODE: {username} {direction} de/a altura >= 10 bloques ({last_xyz[1]:.1f} → {dest_xyz[1]:.1f})")
                else:
                    safe_print(f"❌ Flashmode bloqueado: {username} intentó zona prohibida")

            self.user_positions[user_id] = destination

        except Exception as e:
            safe_print(f"❌ Error en on_user_move: {e}")

    # ========================================================================
    # TAREAS EN SEGUNDO PLANO
    # ========================================================================

    async def start_announcements(self):
        """Sistema de anuncios automáticos públicos"""
        try:
            # Esperar un poco al inicio
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return
        
        announcements = [
            "👋🏼 Me alegra verte aquí ❤️‍🩹💯\nUn espacio donde cada momento cuenta ✨\n💬 Conecta, comparte y deja tu huella 👣\nCada persona que llega deja algo único… ¿qué dejarás tú?",
            "💬 Socializa y haz nuevos amigos.\n🌟 Comparte tus ideas, descubre nuevas experiencias y deja tu marca en cada interacción.\n‼️Cualquier duda o incomodidad, estamos siempre disponibles para escucharte y asegurarnos de que tu experiencia sea la mejor posible‼️",
            "🎮 Usa !help para ver la lista de todos los comandos",
            "💖 Envía corazones a amigos con !heart @username",
            "🏆 Revisa el ranking con !leaderboard",
            "🎯 Juega al medidor de amor: !love @user1 @user2",
            "💎 ¡Conviértete en VIP por 100 oro y obtén capacidades exclusivas!",
            "🚀 ¡Conviértete en VIP ahora! Escribe !sub en mi inbox y disfruta 24 horas de privilegios. 🎟️✨"
        ]
        
        index = 0
        
        while True:
            try:
                message = announcements[index]
                await self.highrise.chat(message)
                safe_print(f"📢 Anuncio automático enviado: {message[:50]}...")
                index = (index + 1) % len(announcements)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log_event("ERROR", f"Error en anuncios: {e}")
            
            try:
                # Intervalo de 4 minutos entre cada anuncio
                await asyncio.sleep(240)
            except asyncio.CancelledError:
                raise

    async def check_console_messages(self):
        """Verifica mensajes desde consola"""
        while True:
            try:
                if os.path.exists("console_message.txt"):
                    with open("console_message.txt", "r", encoding="utf-8") as f:
                        message = f.read().strip()
                    if message:
                        await self.highrise.chat(message)
                        print(f"💬 Mensaje de consola enviado: {message}")
                        os.remove("console_message.txt")
            except Exception as e:
                print(f"Error verificando mensajes de consola: {e}")
            await asyncio.sleep(1)

    async def periodic_inventory_save(self):
        """Guarda inventario periódicamente"""
        while True:
            await asyncio.sleep(300)
            try:
                # Verificar si el bot sigue conectado antes de intentar guardar
                if hasattr(self, 'highrise') and self.highrise:
                    await save_bot_inventory(self)
            except Exception as e:
                safe_print(f"⚠️ Error en guardado periódico de inventario: {e}")

    async def start_copied_emote_loop(self, emote_id: str):
        """Bucle infinito de emote copiado"""
        safe_print(f"🎭 INICIANDO BUCLE INFINITO DE EMOTE COPIADO: {emote_id}")
        log_event("BOT", f"Bucle infinito de emote copiado iniciado: {emote_id}")
        
        # Obtener duración del emote
        emote_duration = 5.0
        for e in emotes.values():
            if e["id"] == emote_id:
                emote_duration = e.get("duration", 5.0)
                break
        
        try:
            while self.bot_mode == "copied" and self.copied_emote_mode:
                try:
                    await self.highrise.send_emote(emote_id, self.bot_id)
                    await asyncio.sleep(max(0.1, emote_duration - 0.3))
                except Exception as e:
                    safe_print(f"❌ Error ejecutando emote copiado: {e}")
                    await asyncio.sleep(1.0)
                    continue
        except Exception as e:
            safe_print(f"❌ ERROR en bucle de emote copiado: {e}")
            log_event("ERROR", f"Error en bucle de emote copiado: {e}")

    async def start_auto_emote_cycle(self):
        """Ciclo automático de emotes con gestión de salud"""
        # Si estamos en modo floss, no iniciar el ciclo automático
        if self.bot_mode == "floss":
            safe_print("⏸️ Ciclo automático no iniciado: bot en modo floss")
            return
        
        await asyncio.sleep(3)
        
        # Desactivar modo de emote copiado si estaba activo
        self.copied_emote_mode = False
        self.current_copied_emote = None
        self.bot_mode = "auto"
        
        # Filtrar solo emotes gratuitos
        free_emotes = {num: data for num, data in emotes.items() if data.get("is_free", True)}
        
        safe_print(f"🎭 INICIANDO CICLO AUTOMÁTICO DE {len(free_emotes)} EMOTES GRATUITOS...")
        log_event("BOT", f"Iniciando ciclo automático de {len(free_emotes)} emotes gratuitos")
        
        consecutive_transport_errors = 0
        max_transport_errors = 3
        
        try:
            cycle_count = 0
            while True:
                cycle_count += 1
                emotes_run = 0
                emotes_skipped = 0
                
                safe_print(f"🔄 Ciclo #{cycle_count} - Iniciando secuencia de {len(free_emotes)} emotes")
                
                for number, emote_data in free_emotes.items():
                    if self.bot_mode != "auto":
                        safe_print("⏸️ Ciclo automático detenido (modo cambiado)")
                        return
                    
                    emote_id = emote_data["id"]
                    emote_name = emote_data["name"]
                    emote_duration = emote_data.get("duration", 5.0)
                    
                    # Omitir emotes deshabilitados
                    if emote_id in DISABLED_EMOTE_IDS:
                        emotes_skipped += 1
                        continue
                    
                    try:
                        # Log para el usuario (solo cada 10 para no saturar)
                        if emotes_run % 10 == 0:
                            await self.highrise.chat(f"🎭 Ciclo Auto: {emote_name} (#{number})")
                        
                        await self.highrise.send_emote(emote_id, self.bot_id)
                        consecutive_transport_errors = 0
                        emotes_run += 1
                        
                        if emotes_run % 20 == 0:
                            safe_print(f"🎭 Emote #{emotes_run}/{len(free_emotes)}: {emote_name}")
                        
                        # Minimizar pausa para transición fluida sin interrupciones (2 segundos menos)
                        await asyncio.sleep(max(0.05, emote_duration - 2))
                        
                    except Exception as e:
                        error_msg = str(e)
                        
                        # Detectar errores de transporte
                        transport_keywords = ["transport", "closing", "connection", "websocket", "disconnect", "closed", "write to closing"]
                        is_transport_error = any(keyword in error_msg.lower() for keyword in transport_keywords)
                        
                        if is_transport_error:
                            consecutive_transport_errors += 1
                            safe_print(f"🔴 Error de transporte #{consecutive_transport_errors} con emote {emote_name}: {error_msg}")
                            log_event("ERROR", f"Error de transporte con emote {emote_name}: {error_msg}")
                            
                            # Si hay demasiados errores de transporte consecutivos, abortar ciclo
                            if consecutive_transport_errors >= max_transport_errors:
                                safe_print(f"🛑 ABORTANDO CICLO: {consecutive_transport_errors} errores de transporte consecutivos")
                                log_event("ERROR", f"Ciclo abortado por {consecutive_transport_errors} errores de transporte")
                                
                                # Esperar con backoff exponencial antes de reintentar
                                backoff_time = min(2 ** consecutive_transport_errors, 60)
                                safe_print(f"⏱️ Esperando {backoff_time}s antes de reintentar...")
                                await asyncio.sleep(backoff_time)
                                
                                # Reiniciar contador para el siguiente ciclo
                                consecutive_transport_errors = 0
                                break
                        else:
                            safe_print(f"⚠️ Error con emote {emote_name}: {error_msg}")
                        
                        await asyncio.sleep(1.0)
                        continue
                
                if emotes_skipped > 0:
                    safe_print(f"⏭️ Emotes omitidos por problemas: {emotes_skipped}")
                
                safe_print(f"✅ Ciclo #{cycle_count} completado. Ejecutados: {emotes_run}, Omitidos: {emotes_skipped}")
                await asyncio.sleep(2.0)
                
        except Exception as e:
            safe_print(f"❌ ERROR CRÍTICO en ciclo automático: {e}")
            log_event("ERROR", f"Error crítico en ciclo automático: {e}")

    async def setup_initial_bot_appearance(self):
        """Configura apariencia inicial del bot"""
        try:
            # Reducir el tiempo de espera inicial para evitar que la sesión caduque
            # pero mantener la robustez con reintentos específicos
            await asyncio.sleep(5)
            
            if "bot_initial_outfit" in config:
                outfit_id = config["bot_initial_outfit"]
                # Intentar aplicar el outfit con reintentos
                for attempt in range(3):
                    try:
                        if not self.session_active: break
                        await self.change_bot_outfit(outfit_id)
                        safe_print(f"🎽 Outfit inicial configurado: {outfit_id}")
                        break
                    except Exception as e:
                        if "closing transport" in str(e).lower(): break
                        if attempt < 2:
                            await asyncio.sleep(5)
                        else:
                            safe_print(f"⚠️ Error configurando outfit inicial: {e}")
            
            if "spawn_point" in config and config["spawn_point"]:
                spawn = config["spawn_point"]
                # Reintentar el teletransporte con una estrategia más robusta
                for attempt in range(5):
                    try:
                        if not self.session_active: break
                        spawn_position = Position(spawn["x"], spawn["y"], spawn["z"])
                        await self.highrise.teleport(self.bot_id, spawn_position)
                        safe_print(f"📍 Bot teletransportado al punto de inicio: X={spawn['x']}, Y={spawn['y']}, Z={spawn['z']}")
                        log_event("BOT", f"Bot posicionado en spawn point: {spawn}")
                        break
                    except Exception as e:
                        err_msg = str(e).lower()
                        # Si es un error de "Not in room", esperar un poco
                        if "not in room" in err_msg or "not_in_room" in err_msg:
                            if attempt < 4:
                                safe_print(f"⏳ Esperando a entrar en la sala (intento {attempt+1})...")
                                await asyncio.sleep(5)
                            else:
                                safe_print(f"⚠️ Error final teletransportando al spawn: {e}")
                        elif "closing transport" in err_msg:
                            break
                        else:
                            if attempt < 4:
                                await asyncio.sleep(5)
                            else:
                                safe_print(f"⚠️ Error final teletransportando al spawn: {e}")
            
            log_event("BOT", f"Bot inicializado correctamente (ID: {self.bot_id})")
        except Exception as e:
            if "closing transport" not in str(e).lower():
                log_event("ERROR", f"Error en setup inicial: {e}")

    async def change_bot_outfit(self, outfit_id: str):
        """Cambia outfit del bot"""
        try:
            if outfit_id == "custom_nocturno":
                from highrise.models import Item
                custom_outfit = [
                    Item(type="clothing", id="shirt-n_guy_rise_par_rewards_2023_mafia_suit", amount=1),
                    Item(type="clothing", id="pants-n_room1_2019formalslacksblack", amount=1),
                    Item(type="clothing", id="glasses-n_registrationavatars2023billieglasses", amount=1),
                    Item(type="clothing", id="shoes-n_marchscavengerhunt2021knifeboots", amount=1),
                    Item(type="clothing", id="mouth-n_dailyquests2024racermouth", amount=1),
                    Item(type="clothing", id="hair_front-n_winterformaludceventrewards02_2023_nikana_maschair", amount=1),
                    Item(type="clothing", id="hat-n_fallen_angels_silks_nevs_2024_angel_halo", amount=1),
                    Item(type="clothing", id="skin-s_gray", amount=1)
                ]
                await self.highrise.set_outfit(custom_outfit)
                log_event("BOT", "Outfit NOCTURNO aplicado")
            else:
                current_outfit_response = await self.highrise.get_my_outfit()
                if not isinstance(current_outfit_response, Error):
                    await self.highrise.set_outfit(current_outfit_response.outfit)
            print(f"✅ Outfit del bot configurado para ID: {outfit_id}")
        except Exception as e:
            log_event("ERROR", f"Error cambiando outfit: {e}")

    async def delayed_restart(self):
        """Parada retrasada del bot"""
        await asyncio.sleep(3)
        print("🛑 ¡Bot detenido!")
        self.save_data()
        sys.exit(0)

    def convert_to_gold_bars(self, amount: int) -> str:
        """Convierte la cantidad de oro en barras de oro para tips"""
        bars_dictionary = {
            10000: "gold_bar_10k", 5000: "gold_bar_5000", 1000: "gold_bar_1k",
            500: "gold_bar_500", 100: "gold_bar_100", 50: "gold_bar_50",
            10: "gold_bar_10", 5: "gold_bar_5", 1: "gold_bar_1"
        }
        tip = []
        remaining_amount = amount
        for bar_value in sorted(bars_dictionary.keys(), reverse=True):
            if remaining_amount >= bar_value:
                bar_count = remaining_amount // bar_value
                remaining_amount %= bar_value
                tip.extend([bars_dictionary[bar_value]] * bar_count)
        return ",".join(tip) if tip else ""

    async def get_bot_wallet_balance(self):
        """Obtiene el balance real de la billetera del bot"""
        try:
            wallet_response = await self.highrise.get_wallet()
            if isinstance(wallet_response, Error):
                print(f"Error obteniendo wallet: {wallet_response}")
                return BOT_WALLET
            wallet = wallet_response.content
            return wallet[0].amount if wallet else BOT_WALLET
        except Exception as e:
            print(f"Error obteniendo balance de billetera: {e}")
            return BOT_WALLET

    async def show_user_info(self, user: User, public_response: bool = False, conversation_id: str = None):
        """Muestra información del jugador"""
        user_id = user.id
        username = user.username
        self.update_user_info(user_id, username)
        user_data = USER_INFO.get(user_id, {})
        total_time = self.get_user_total_time(user_id)
        messages = USER_ACTIVITY.get(user_id, {}).get("messages", 0)
        hearts = self.get_user_hearts(user_id)
        current_time_in_room = round(time.time() - USER_JOIN_TIMES.get(user_id, time.time()))
        total_time_str = self.format_time(total_time + current_time_in_room)

        if user_id == OWNER_ID: rol = "👑 Propietario"
        elif self.is_admin(user_id): rol = "🛡️ Administrador"
        elif self.is_moderator(user_id): rol = "⚖️ Moderador"
        elif self.is_vip(user_id): rol = "⭐ VIP"
        else: rol = "👤 Usuario Normal"

        followers, following, friends, account_created, crew_info = "N/A", "N/A", "N/A", "Sconosciuto", "Sin crew"
        try:
            user_info = await self.webapi.get_user(user_id) if hasattr(self, 'webapi') and self.webapi else None
            if user_info:
                account_created = user_info.user.joined_at.strftime("%d.%m.%Y %H:%M")
                USER_INFO[user_id]["account_created"] = user_info.user.joined_at.isoformat()
                followers, following, friends = str(user_info.user.num_followers), str(user_info.user.num_following), str(user_info.user.num_friends)
                if hasattr(user_info.user, 'crew') and user_info.user.crew:
                    crew_name = user_info.user.crew.name if hasattr(user_info.user.crew, 'name') else "Unknown"
                    crew_info = crew_name
            elif user_data.get("account_created"):
                try:
                    created_dt = datetime.fromisoformat(user_data["account_created"].replace('Z', '+00:00'))
                    account_created = created_dt.strftime("%d.%m.%Y %H:%M")
                except: pass
        except Exception as e: print(f"Errore Web API: {e}")

        highrise_time = "Sconosciuto"
        try:
            if account_created != "Sconosciuto":
                created_dt = datetime.strptime(account_created, "%d.%m.%Y %H:%M")
                time_diff = datetime.now() - created_dt
                days, hours, minutes = time_diff.days, time_diff.seconds // 3600, (time_diff.seconds % 3600) // 60
                highrise_time = f"{days}d, {hours}h, {minutes}m"
        except Exception as e: print(f"Errore calcolo tempo Highrise: {e}")

        info_message = f"📊 {username}'s Info:\n🎭 Rol: {rol}\n👥 Crew: {crew_info}\n📅 Registrado: {account_created}\n⏰ Tiempo en HR: {highrise_time}\n💖 Corazones: {hearts}\n💬 Mensajes: {messages}\n👥 Followers: {followers} | Following: {following} | Friends: {friends}"
        
        if conversation_id:
            await self.highrise.send_message(conversation_id, info_message)
        elif public_response:
            await self.highrise.chat(info_message)
        else:
            await self.highrise.send_whisper(user_id, info_message)

    async def show_user_info_by_username(self, username: str):
        """Muestra información de usuario por nombre de usuario"""
        target_user_id = None
        response = await self.highrise.get_room_users()
        if isinstance(response, Error):
            await self.highrise.chat("❌ Error obteniendo usuarios")
            log_event("ERROR", f"get_room_users failed: {response.message}")
            return
        users = response.content
        for u, _ in users:
            if u.username == username:
                target_user_id = u.id
                self.update_user_info(target_user_id, username)
                break
        if not target_user_id:
            await self.highrise.chat(f"❌ ¡Usuario {username} no encontrado!")
            return
        await self.show_user_info(User(id=target_user_id, username=username), public_response=True)

    async def show_user_role(self, user: User):
        """Muestra el rol del jugador actual"""
        user_id = user.id
        username = user.username
        if self.is_admin(user_id): role = "Admin"
        elif self.is_moderator(user_id): role = "Manager"
        elif self.is_vip(user_id): role = "Host"
        else: role = "Vip"
        await self.highrise.send_whisper(user_id, f"{username} Roles:[{role}]")

    async def show_user_role_by_username(self, username: str):
        """Muestra el rol de un jugador por nombre de usuario"""
        target_user_id = None
        response = await self.highrise.get_room_users()
        if isinstance(response, Error):
            await self.highrise.chat("❌ Error obteniendo usuarios")
            return
        users = response.content
        for u, _ in users:
            if u.username == username:
                target_user_id = u.id
                self.update_user_info(target_user_id, username)
                break
        if not target_user_id: await self.highrise.chat(f"❌ Giocatore @{username} non trovato"); return
        if self.is_admin(target_user_id): role = "Admin"
        elif self.is_moderator(target_user_id): role = "Manager"
        elif self.is_vip(target_user_id): role = "Host"
        else: role = "Vip"
        await self.highrise.send_whisper(target_user_id, f"🔑 {username} Roles:\nNivel: {role}")

    async def notify_admins(self, message: str):
        """Envía notificación solo a admin y propietario"""
        try:
            # Notificar al propietario
            if OWNER_ID:
                try:
                    await self.highrise.send_whisper(OWNER_ID, message)
                    safe_print(f"📨 Notificación enviada al propietario")
                except:
                    pass
            
            # Notificar a los administradores
            for admin_id in ADMIN_IDS:
                try:
                    await self.highrise.send_whisper(admin_id, message)
                    safe_print(f"📨 Notificación enviada a admin {admin_id[:8]}...")
                except:
                    pass
        except Exception as e:
            safe_print(f"❌ Error enviando notificaciones: {e}")
    
    async def get_bot_user(self):
        """Obtiene el objeto User del bot usando bot_id almacenado"""
        try:
            if not hasattr(self, 'bot_id'): log_event("ERROR", "Bot ID no disponible"); return None
            response = await self.highrise.get_room_users()
            if isinstance(response, Error):
                log_event("ERROR", f"Error obteniendo usuarios de sala: {response.message}")
                return None
            users = response.content
            bot_user = next((u for u, _ in users if u.id == self.bot_id), None)
            if bot_user: log_event("BOT", f"Bot encontrado: {bot_user.username}")
            else: log_event("WARNING", f"Bot no encontrado en sala con ID: {self.bot_id}")
            return bot_user
        except Exception as e: log_event("ERROR", f"Error obteniendo bot user: {e}"); return None

    async def console_chat_input(self):
        """Entrada de consola para enviar mensajes"""
        print("💬 Chat de consola iniciado! Ingresa 'quit' para salir.")
        while True:
            try:
                message = input("> ")
                if message.lower() == 'quit': break
                elif message.strip(): await self.highrise.chat(message); print(f"✅ Enviado: {message}")
            except KeyboardInterrupt: break
            except Exception as e: print(f"❌ Error de envío: {e}")

# ============================================================================
# MANEJADOR DE SEÑALES
# ============================================================================

def signal_handler(sig, frame):
    """Guarda datos al salir"""
    print("\n🛑 Señal de salida recibida. Guardando datos...")
    current_time = time.time()
    for user_id, join_time in USER_JOIN_TIMES.items():
        if user_id in USER_INFO:
            time_in_room = round(current_time - join_time)
            USER_INFO[user_id]["total_time_in_room"] += time_in_room
    try:
        # Guardar puntos de teletransporte
        os.makedirs("data", exist_ok=True)
        with open("data/teleport_points.txt", "w", encoding="utf-8") as f:
            f.write("# Puntos de teletransporte (nombre|x|y|z)\n")
            for name, coords in TELEPORT_POINTS.items():
                f.write(f"{name}|{coords['x']}|{coords['y']}|{coords['z']}\n")
        
        save_leaderboard_data()
        save_user_info()
        safe_print("✅ Datos guardados con éxito (incluidos puntos de teletransporte)")
    except Exception as e: print(f"❌ Error guardando datos: {e}")
    print("👋 ¡Adiós!")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

# Eliminado el bloque if __name__ == "__main__": para evitar doble conexión.
# El bot debe iniciarse usando: python -m highrise main:Bot
