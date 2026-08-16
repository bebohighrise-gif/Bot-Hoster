"""
Bot de Highrise con radio DJ integrada.
Las solicitudes de YouTube se reproducen desde una URL temporal de audio;
no se descargan ni se guardan como archivos locales.
"""
from highrise import BaseBot, User
import asyncio
import threading
import os
import json
from typing import Any
from radio import RadioStation, format_seconds

USERS_FILE      = "users.json"
FAVORITES_FILE  = "favorites.json"
CONFIG_FILE     = "config.json"
BANNED_FILE     = "banned.json"


# ── JSON helpers ─────────────────────────────────────────────────────────────
def load_json(file):
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {file}: {e}")

# ── User helpers ─────────────────────────────────────────────────────────────
def get_user_data(user_id):
    data = load_json(USERS_FILE)
    if user_id not in data:
        data[user_id] = {"gold": 0, "requests": 3, "history": []}
        save_json(USERS_FILE, data)
    if "history" not in data[user_id]:
        data[user_id]["history"] = []
        save_json(USERS_FILE, data)
    return data[user_id]

def get_favorites(user_id):
    return load_json(FAVORITES_FILE).get(user_id, [])

def save_favorite(user_id, song_name):
    data = load_json(FAVORITES_FILE)
    if user_id not in data:
        data[user_id] = []
    if song_name not in data[user_id]:
        data[user_id].append(song_name)
        save_json(FAVORITES_FILE, data)
        return True
    return False

def clear_favorites(user_id):
    data = load_json(FAVORITES_FILE)
    if user_id in data:
        data[user_id] = []
        save_json(FAVORITES_FILE, data)

def add_to_history(user_id, song_name):
    data = load_json(USERS_FILE)
    if user_id not in data:
        data[user_id] = {"gold": 0, "requests": 3, "history": []}
    if "history" not in data[user_id]:
        data[user_id]["history"] = []
    data[user_id]["history"].append(song_name)
    if len(data[user_id]["history"]) > 50:
        data[user_id]["history"] = data[user_id]["history"][-50:]
    save_json(USERS_FILE, data)

def is_banned(user_id):
    return user_id in load_json(BANNED_FILE).get("banned", [])

def ban_user(user_id):
    data = load_json(BANNED_FILE)
    if "banned" not in data:
        data["banned"] = []
    if user_id not in data["banned"]:
        data["banned"].append(user_id)
        save_json(BANNED_FILE, data)

def is_admin(user_id, radio):
    conf = load_json(CONFIG_FILE)
    return user_id == getattr(radio, "owner_id", None) or user_id in conf.get("admins", [])

# ── Streaming de música solicitada ───────────────────────────────────────────
def _ytdlp_stream_info(query):
    """
    Obtiene título, duración y URL temporal del audio sin descargarlo.

    La URL la consume FFmpeg mientras la canción está al aire. YouTube puede
    hacerla expirar, por eso se extrae de nuevo en cada pedido.
    """
    try:
        from yt_dlp import YoutubeDL

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "noplaylist": True,
            "skip_download": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            entry = info["entries"][0] if info and info.get("entries") else info
            if not entry:
                return None

            # Algunos extractores devuelven primero una referencia a la página.
            # Resolverla una segunda vez garantiza una URL de media reproducible.
            stream_url = entry.get("url")
            if entry.get("_type") == "url" or not stream_url:
                page_url = entry.get("webpage_url") or entry.get("url")
                if not page_url:
                    return None
                entry = ydl.extract_info(page_url, download=False)
                stream_url = entry.get("url")

            if not stream_url:
                return None

            return {
                "stream_url": stream_url,
                "source_url": entry.get("webpage_url") or query,
                "name": entry.get("title") or query,
                "duration": int(entry.get("duration") or 0),
            }
    except Exception as e:
        print(f"[STREAM] ⚠️ No se pudo obtener el stream ({query[:80]}): {e}")
        return None


def buscar_y_stream(song_or_link):
    """
    Busca una canción y devuelve una referencia de streaming.

    No crea archivos ni activa ningún modo de descarga. El audio se obtiene
    cuando RadioStation inicia la reproducción.
    """
    try:
        print(f"[STREAM] 🔄 Buscando fuente: {song_or_link}")
        query = song_or_link if song_or_link.startswith("http") else f"ytsearch1:{song_or_link}"
        track = _ytdlp_stream_info(query)
        if not track:
            print(f"[STREAM] ❌ No se encontró: {song_or_link}")
            return None

        print(f"[STREAM] ✅ Fuente lista: {track['name']}")
        return track
    except Exception as e:
        print(f"[STREAM] ❌ Error: {str(e)[:200]}")
        return None


# ── Highrise Bot ─────────────────────────────────────────────────────────────
class HighriseBot(BaseBot):
    _initialized = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, "radio") or self.radio is None:
            self.radio = RadioStation()
        self.radio.bot_instance = self
        self.loop = None

    async def auto_messages_loop(self):
        while True:
            await asyncio.sleep(300)
            try:
                conf = load_json(CONFIG_FILE)
                msgs = conf.get("auto_messages", [])
                if msgs:
                    import random
                    await self.highrise.chat(f"🔁 {random.choice(msgs)}")
                else:
                    await self.highrise.chat("🤖 Soy el DJ automático. Usa /help para ver mis comandos.")
            except Exception as e:
                print(f"[BOT] Error en auto_messages_loop: {e}")

    async def emote_loop(self):
        while True:
            try:
                await self.highrise.send_emote("dance-handsup")
            except Exception as e:
                print(f"[BOT] Error enviando emote: {e}")
            await asyncio.sleep(23.18)

    async def on_start(self, session_metadata: Any) -> None:
        try:
            self.radio.bot_id = session_metadata.user_id
            print(f"[BOT] 🤖 Bot iniciado. ID: {self.radio.bot_id}")

            conf  = load_json(CONFIG_FILE)
            spawn = conf.get("spawn_position")
            if spawn:
                from highrise.models import Position
                pos = Position(spawn["x"], spawn["y"], spawn["z"], spawn.get("facing", "FrontRight"))
                await self.highrise.teleport(self.radio.bot_id, pos)
                print("[BOT] 📍 Teletransportado a posición inicial.")

            if not HighriseBot._initialized:
                HighriseBot._initialized = True
                asyncio.create_task(self.auto_messages_loop())
                asyncio.create_task(self.emote_loop())
                print("[BOT] 🔁 Bucles de mensajes y emotes iniciados.")
        except Exception as e:
            print(f"[BOT] Error en on_start: {e}")

    async def on_user_join(self, user: User, position: Any) -> None:
        async def send_welcome():
            for i in range(3):
                try:
                    conf    = load_json(CONFIG_FILE)
                    tmpl    = conf.get("welcome_message", "👋 Bienvenido @user")
                    msg     = tmpl.replace("@user", f"@{user.username}")
                    await self.highrise.send_whisper(user.id, msg)
                    print(f"[BOT] ✅ Bienvenida enviada a @{user.username}")
                    break
                except Exception as e:
                    print(f"[BOT] ⚠️ Error bienvenida ({i+1}): {e}")
                    await asyncio.sleep(2 * (i + 1))
        asyncio.create_task(send_welcome())

    async def on_chat(self, user: User, message: str) -> None:
        try:
            self.loop = asyncio.get_event_loop()

            if is_banned(user.id):
                return

            admin = is_admin(user.id, self.radio)

            # /stream — URL de la radio
            if message.startswith("/stream") and admin:
                host = (os.environ.get("REPLIT_DEV_DOMAIN") or
                        os.environ.get("REPLIT_DOMAINS") or
                        os.environ.get("PUBLIC_DOMAIN") or
                        os.environ.get("HOSTNAME"))
                if host:
                    url = host if host.startswith("http") else f"https://{host}"
                    url = url.rstrip("/") + "/stream"
                    await self.highrise.send_whisper(user.id, f"🌐 Radio: {url}")
                else:
                    await self.highrise.send_whisper(user.id, "❌ No se pudo determinar el host.")

            # /play
            elif message.startswith("/play"):
                song = message.split(" ", 1)[1].strip() if " " in message else ""
                if not song:
                    await self.highrise.chat("🎵 Usa: /play <nombre o link>")
                    return

                user_data = get_user_data(user.id)

                if not admin and user_data["requests"] <= 0:
                    await self.highrise.send_whisper(
                        user.id,
                        "<#FF0000>⛔:Límite alcanzado.\n🎟️:Pedidos disponibles: 0\n"
                        "<#FFFFFF>🪙:Envía mínimo 10 de oro para obtener más pedidos."
                    )
                    return

                await self.highrise.send_whisper(user.id, f"<#FFD580>⏳:Procesando pedido...\n🎵:{song}")

                # Buscar primero en la librería local
                local_match = None
                for track in self.radio.queue_local:
                    if song.lower() in track["name"].lower():
                        local_match = track
                        break

                if local_match:
                    track_data = {**local_match, "username": user.username, "user_id": user.id}
                    self.radio.add_to_queue(track_data)
                    duration_str = format_seconds(local_match.get("duration", 0))
                    await self.highrise.send_whisper(
                        user.id,
                        f"<#90EE90>✅:Pedido aceptado (librería local):\n"
                        f"<#90EE90>🔊:{local_match['name']}\n"
                        f"<#FF69B4>⏱️:{duration_str}\n"
                        f"<#FF69B4>👤:Requested by: @{user.username}"
                    )
                    return

                threading.Thread(
                    target=self.cmd_play_thread,
                    args=(user, song, self.loop),
                    daemon=True
                ).start()

            # /fav list
            elif message.startswith("/fav list"):
                favs = get_favorites(user.id)
                if favs:
                    await self.highrise.send_whisper(user.id, "⭐ Tus favoritos:\n" + "\n".join(f"• {f}" for f in favs[:10]))
                else:
                    await self.highrise.send_whisper(user.id, "⭐ No tienes favoritos aún.")

            # /fav <song>
            elif message.startswith("/fav "):
                song_name = message.split(" ", 1)[1].strip()
                if save_favorite(user.id, song_name):
                    await self.highrise.send_whisper(user.id, f"⭐ '{song_name}' añadido a favoritos.")
                else:
                    await self.highrise.send_whisper(user.id, f"⭐ '{song_name}' ya está en favoritos.")

            # /profile
            elif message.startswith("/profile"):
                history = get_user_data(user.id).get("history", [])
                if history:
                    for song in history[-10:]:
                        await self.highrise.send_whisper(user.id, f"👤 🎵 {song}")
                else:
                    await self.highrise.send_whisper(user.id, "👤 No has pedido canciones aún.")

            # /q — cola actual
            elif message.startswith("/q"):
                cola    = list(self.radio.queue_requests.queue) if hasattr(self.radio.queue_requests, "queue") else []
                current = self.radio.current_track
                if current:
                    await self.highrise.chat(f"🎵 Sonando: {current.get('name','?')}")
                if cola:
                    msg = "👣 Cola:\n" + "\n".join(
                        f"{i+1}. {t.get('name','?')} (@{t.get('username','?')})"
                        for i, t in enumerate(cola[:10])
                    )
                    await self.highrise.chat(msg)
                elif not current:
                    await self.highrise.chat("👣 La cola está vacía.")

            # /pedidos
            elif message.startswith("/pedidos"):
                user_data = get_user_data(user.id)
                restantes = "∞" if admin else user_data["requests"]
                await self.highrise.send_whisper(user.id, f"📋 Tienes {restantes} pedidos disponibles.")

            # /help
            elif message.strip().lower() == "/help":
                if admin:
                    await self.highrise.send_whisper(user.id,
                        "📖 COMANDOS ADMIN:\n"
                        "• /stop - Detener reproducción\n"
                        "• /next - Siguiente canción\n"
                        "• /pause - Pausar música\n"
                        "• /resume - Reanudar música\n"
                        "• /stream - URL de la radio\n"
                        "• /delete @user - Bloquear usuario\n"
                    )
                await self.highrise.send_whisper(user.id,
                    "📖 COMANDOS:\n"
                    "• /play <nombre> - Pedir canción\n"
                    "• /q - Ver cola de pedidos\n"
                    "• /fav <canción> - Guardar favorito\n"
                    "• /fav list - Ver favoritos\n"
                    "• /profile - Ver historial\n"
                    "• /pedidos - Ver pedidos disponibles\n"
                )

            # Comandos admin
            elif admin:
                if message.startswith("/next"):
                    self.radio.skip_current = True
                    await self.highrise.chat("⏭️ Saltando a siguiente canción...")
                elif message.startswith("/stop"):
                    self.radio.running = False
                    await self.highrise.chat("⏹️ Radio detenida.")
                elif message.startswith("/pause"):
                    self.radio.paused = True
                    await self.highrise.chat("⏸️ Radio en pausa.")
                elif message.startswith("/resume"):
                    self.radio.paused = False
                    await self.highrise.chat("▶️ Radio reanudada.")
                elif message.startswith("/delete "):
                    target = message.split(" ", 1)[1].strip().lstrip("@")
                    await self.highrise.chat(f"🚫 Usuario @{target} bloqueado.")

        except Exception as e:
            print(f"[BOT] Error en on_chat: {e}")

    def cmd_play_thread(self, user, song, loop):
        """Obtiene una fuente de streaming y encola la canción."""
        try:
            import time
            time.sleep(1.5)
            asyncio.run_coroutine_threadsafe(
                self.highrise.send_whisper(user.id, f"<#FFD580>🖥️:Buscando stream...\n🎵:{song}"),
                loop
            )
            time.sleep(1.0)

            track = buscar_y_stream(song)
            if track:
                track["username"] = user.username
                duration_str = format_seconds(track.get("duration", 0))

                asyncio.run_coroutine_threadsafe(
                    self.highrise.send_whisper(
                        user.id,
                        f"<#90EE90>📡:Stream listo:\n<#FFFFFF>🎵:{track['name']}\n<#90EE90>⏳:Duración: ({duration_str})"
                    ),
                    loop
                )

                user_data = get_user_data(user.id)
                admin     = is_admin(user.id, self.radio)
                if not admin:
                    user_data["requests"] -= 1
                    all_data         = load_json(USERS_FILE)
                    all_data[user.id] = user_data
                    save_json(USERS_FILE, all_data)

                restantes = "∞" if admin else user_data["requests"]
                asyncio.run_coroutine_threadsafe(
                    self.highrise.send_whisper(user.id, f"🎟️: Pedidos restantes: {restantes}"),
                    loop
                )

                self.radio.add_to_queue(track)
                add_to_history(user.id, track["name"])
            else:
                asyncio.run_coroutine_threadsafe(
                    self.highrise.send_whisper(
                        user.id,
                        f"❌:<#FF0000>No encontré un stream para:\n🔊:<#FFFFFF>{song}"
                    ),
                    loop
                )
        except Exception as e:
            print(f"[BOT] Error en cmd_play_thread: {e}")
            asyncio.run_coroutine_threadsafe(
                self.highrise.send_whisper(user.id, "❌:<#FF0000>Error procesando tu pedido."),
                loop
            )


class Bot(HighriseBot):
    pass