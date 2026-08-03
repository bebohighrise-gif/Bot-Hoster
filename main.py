import os
import shutil
import subprocess
import asyncio
import re
from datetime import datetime
from highrise import BaseBot, User, Position, AnchorPosition
from highrise.models import SessionMetadata, CurrencyItem

from config import HOSTER_OWNER_ID, TEMPLATES_DIR, HOSTED_INSTANCES_DIR
import database as db

db.init_db()

# ── Estado en memoria ─────────────────────────────────────────────────
gift_sessions       = {}  # {user_id: {step, ...}}
buy_sessions        = {}  # {user_id: {step, category, ...}}
user_conversations  = {}  # {user_id: conversation_id}
active_announcement = {}  # {message, interval, task}
running_processes   = {}  # {bot_id: subprocess.Popen}

# ── Catálogo de categorías ────────────────────────────────────────────
CATEGORY_MAP = {
    "1": "musica", "musica": "musica",
    "3": "fiesta",  "fiesta": "fiesta",
}
CATEGORY_NAMES  = {"musica": "MÚSICA",  "fiesta": "FIESTA"}
CATEGORY_EMOJIS = {"musica": "🎵",      "fiesta": "🎉"}

DURATION_OPTIONS = {
    "musica": [
        ("1", "1d",   "24 Horas",    400),
        ("2", "7d",   "7 Días",      900),
        ("3", "15d",  "15 Días",    1600),
        ("4", "30d",  "30 Días",    3200),
        ("5", "perm", "Permanente", 12000),
    ],
    "fiesta": [
        ("1", "1d",   "24 Horas",    300),
        ("2", "7d",   "7 Días",      800),
        ("3", "15d",  "15 Días",    1500),
        ("4", "30d",  "30 Días",    6000),
        ("5", "perm", "Permanente", 10000),
    ],
}

# Precios para compra directa (!buy <cat> <tiempo> <token> <room_id>)
PRICE_MAP = {
    "musica": {"1d": 400, "7d": 900, "15d": 1600, "30d": 3200, "perm": 12000},
    "fiesta": {"1d": 300, "7d": 800, "15d": 1500, "30d": 6000, "perm": 10000},
}

LANG_NAMES = {"es": "ESPAÑOL", "en": "INGLÉS", "pt": "PORTUGUÉS"}
DIVIDER    = "<#FFFFFF>──────────────────────────────────────────"


# ── Helpers ───────────────────────────────────────────────────────────

def format_time_remaining(expires_at: str) -> str:
    """Retorna tiempo restante legible: '3 Días', '12 Horas', '45 Minutos'."""
    if not expires_at:
        return "Permanente"
    try:
        exp   = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
        delta = exp - datetime.utcnow()
        if delta.total_seconds() <= 0:
            return "Expirado"
        total = int(delta.total_seconds())
        days  = total // 86400
        hours = (total % 86400) // 3600
        mins  = (total % 3600) // 60
        if days > 0:
            return f"{days} Día{'s' if days != 1 else ''}"
        elif hours > 0:
            return f"{hours} Hora{'s' if hours != 1 else ''}"
        else:
            return f"{mins} Minuto{'s' if mins != 1 else ''}"
    except Exception:
        return expires_at


def template_exists(bot_type: str) -> bool:
    path = os.path.join(TEMPLATES_DIR, bot_type.lower())
    return os.path.isdir(path) and bool(os.listdir(path))


def _write_instance_config(instance_path: str, room_id: str, api_token: str, owner_id: str):
    config_path = os.path.join(instance_path, "config.py")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(
            "# CONFIGURACIÓN GENERADA AUTOMÁTICAMENTE POR BOT HOSTER\n"
            f'ROOM_ID = "{room_id}"\n'
            f'API_TOKEN = "{api_token}"\n'
            f'BOT_OWNER_ID = "{owner_id}"\n'
            f'HOSTER_OWNER_ID = "{HOSTER_OWNER_ID}"\n'
        )


def deploy_bot_instance(user_id: str, bot_type: str, room_id: str, api_token: str):
    """Clona la plantilla, inyecta credenciales y lanza el proceso."""
    template_path = os.path.join(TEMPLATES_DIR, bot_type.lower())
    instance_path = os.path.join(HOSTED_INSTANCES_DIR, f"user_{user_id}_{bot_type.lower()}")

    if not os.path.exists(template_path):
        print(f"❌ Plantilla '{template_path}' no existe.")
        return False, None

    if os.path.exists(instance_path):
        shutil.rmtree(instance_path)
    shutil.copytree(template_path, instance_path)
    _write_instance_config(instance_path, room_id, api_token, user_id)

    try:
        proc = subprocess.Popen(["python", "run.py"], cwd=instance_path)
        print(f"🟢 Bot {bot_type} desplegado para {user_id} (PID {proc.pid})")
        return True, proc
    except Exception as e:
        print(f"🔴 Error lanzando run.py: {e}")
        return False, None


def redeploy_bot(bot_id: int, owner_id: str, category: str, room_id: str, api_token: str):
    """Mata el proceso existente y relanza el bot (para !restart y !mover)."""
    proc = running_processes.pop(bot_id, None)
    if proc and proc.poll() is None:
        proc.terminate()

    instance_path = os.path.join(HOSTED_INSTANCES_DIR, f"user_{owner_id}_{category.lower()}")
    if not os.path.exists(instance_path):
        template_path = os.path.join(TEMPLATES_DIR, category.lower())
        if not os.path.exists(template_path):
            return False, None
        shutil.copytree(template_path, instance_path)

    _write_instance_config(instance_path, room_id, api_token, owner_id)

    try:
        proc = subprocess.Popen(["python", "run.py"], cwd=instance_path)
        running_processes[bot_id] = proc
        print(f"🔄 Bot ID {bot_id} relanzado (PID {proc.pid})")
        return True, proc
    except Exception as e:
        print(f"🔴 Error al relanzar bot {bot_id}: {e}")
        return False, None


# ── Clase principal ───────────────────────────────────────────────────

class BotHoster(BaseBot):

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        self.session_metadata = session_metadata
        print("🤖 Bot Hoster de Nex-Host iniciado y conectado a la sala.")
        for cat in ["musica", "fiesta", "juegos", "personalizado"]:
            if not template_exists(cat):
                db.set_maintenance(cat, 1)
                print(f"⚠️  Categoría '{cat}' en mantenimiento (sin plantilla).")
        asyncio.create_task(self._expiration_loop())

    async def _expiration_loop(self) -> None:
        """Revisa cada 60 s si hay bots expirados y los termina."""
        while True:
            await asyncio.sleep(60)
            try:
                expired = db.get_expired_bots()
                for bot_id, owner_id, category in expired:
                    proc = running_processes.pop(bot_id, None)
                    if proc and proc.poll() is None:
                        proc.terminate()
                        print(f"🛑 Bot ID {bot_id} ({category}) de {owner_id} terminado por expiración.")
                    db.mark_bot_expired(bot_id)
                    conv_id = user_conversations.get(owner_id)
                    if conv_id:
                        try:
                            await self.highrise.send_message(
                                conv_id,
                                f"<#E74C3C>⏰ Tu bot de categoría <#00FFFF>{category}<#E74C3C> "
                                f"(ID <#00FFFF>{bot_id}<#E74C3C>) ha expirado y fue detenido automáticamente."
                            )
                        except Exception:
                            pass
            except Exception as e:
                print(f"❌ Error en verificador de expiración: {e}")

    def _write_tex_to_instances(self, message: str) -> int:
        sent = 0
        for owner_id, category in db.get_active_bot_instances():
            ipath = os.path.join(HOSTED_INSTANCES_DIR, f"user_{owner_id}_{category.lower()}")
            if os.path.isdir(ipath):
                try:
                    with open(os.path.join(ipath, "console_message.txt"), "w", encoding="utf-8") as f:
                        f.write(message)
                    sent += 1
                except Exception as e:
                    print(f"❌ Error en instancia {ipath}: {e}")
        return sent

    async def _announcement_loop(self, message: str, interval: int) -> None:
        try:
            while True:
                self._write_tex_to_instances(message)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    async def on_user_join(self, user: User, position: Position | AnchorPosition) -> None:
        db.get_or_create_user(user.id, user.username)

    async def on_tip_reaction(self, sender: User, receiver: User, tip: CurrencyItem) -> None:
        if receiver.id == self.session_metadata.user_id:
            db.update_gold(sender.id, tip.amount)
            user_data = db.get_or_create_user(sender.id, sender.username)
            await self.highrise.send_whisper(
                sender.id,
                f"<#2ECC71>💰 ¡Gracias por tu depósito! Recibidos <#FFD700>{tip.amount} 🪙<#2ECC71>.\n"
                f"<#FFFFFF>Tu nuevo saldo acumulado es: <#FFD700>{user_data['balance']} 🪙<#FFFFFF>.\n"
                f"<#AAAAAA>Revisa tu Inbox para abrir el menú o escribe '!plan'."
            )

    async def on_whisper(self, user: User, message: str) -> None:
        if user.id == HOSTER_OWNER_ID and message.strip().lower() == "!copy":
            try:
                outfit_resp = await self.highrise.get_user_outfit(user.id)
                if outfit_resp and hasattr(outfit_resp, 'outfit'):
                    await self.highrise.set_outfit(outfit_resp.outfit)
                    await self.highrise.send_whisper(user.id, "<#2ECC71>👕 ¡Outfit clonado y aplicado con éxito!")
            except Exception as e:
                await self.highrise.send_whisper(user.id, f"<#E74C3C>❌ Error al copiar outfit: {e}")

    # ── Menú principal ────────────────────────────────────────────────

    async def _send_menu(self, user_id: str, conversation_id: str) -> None:
        user_data = db.get_or_create_user(user_id)
        user_bots = db.get_user_bots(user_id)

        menu  = "<#FFD700>👋 ¡Hola! Bienvenido a Nex-Host (Hosting Bot 24/7).\n\n"
        menu += f"<#FFFFFF>💰 Tu Saldo: <#FFD700>{user_data['balance']} 🪙\n\n"
        menu += "<#00FFFF>📋 MENÚ DE COMANDOS:\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!menu       <#FFFFFF>- Mostrar este menú\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!saldo      <#FFFFFF>- Consultar balance\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!plan       <#FFFFFF>- Ver categorías y precios\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!buy 1<#FFFFFF>(Música)·<#00FF00>!buy 3<#FFFFFF>(Fiesta) - Comprar bot\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!mybots     <#FFFFFF>- Ver tus bots alojados\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!restart    <#FFFFFF>- Reiniciar bot\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!mover <sala><#FFFFFF>- Cambiar sala del bot\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!soporte <msg><#FFFFFF>- Enviar ticket al admin\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!gift <id> <monto><#FFFFFF>- Regalar saldo\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!lang host <es/en/pt><#FFFFFF>- Idioma del sistema\n"

        if len(user_bots) == 1:
            b_id, r_id, st, cat, exp = user_bots[0]
            time_left = format_time_remaining(exp)
            menu += (
                f"\n<#85E3FF>🤖 TU BOT: <#FFFFFF>ID <#00FFFF>{b_id} "
                f"<#FFFFFF>| Tipo: <#00FFFF>{cat.upper()} "
                f"<#FFFFFF>| Sala: <#00FFFF>{r_id} "
                f"<#FFFFFF>| Expira: <#FFD700>{time_left}\n"
            )
        elif len(user_bots) > 1:
            menu += (f"\n<#85E3FF>🤖 Tienes <#FFD700>{len(user_bots)} <#85E3FF>bots activos. "
                     f"Usa <#00FF00>!mybots <#85E3FF>para ver la lista.\n")

        if user_id == HOSTER_OWNER_ID:
            menu += "\n<#FFD700>👑 PANEL ADMIN:\n"
            menu += "<#FFFFFF>• <#00FF00>!stats               <#FFFFFF>- Estadísticas del sistema\n"
            menu += "<#FFFFFF>• <#00FF00>!id <user_id>        <#FFFFFF>- Perfil de comprador\n"
            menu += "<#FFFFFF>• <#00FF00>!tickets             <#FFFFFF>- Ver tickets de soporte\n"
            menu += "<#FFFFFF>• <#00FF00>!responder <id> <msg><#FFFFFF>- Contestar cliente\n"
            menu += "<#FFFFFF>• <#00FF00>!addtime <id> <tiempo><#FFFFFF>- Añadir tiempo a bot\n"
            menu += "<#FFFFFF>• <#00FF00>!banuser / !unbanuser <id>\n"
            menu += "<#FFFFFF>• <#00FF00>!giftbot             <#FFFFFF>- Regalar bot paso a paso\n"
            menu += "<#FFFFFF>• <#00FF00>!addgold <id> <cant>\n"
            menu += "<#FFFFFF>• <#00FF00>!mantenimiento <cat> <on/off>\n"
            menu += "<#FFFFFF>• <#00FF00>!broadcast <msg>     <#FFFFFF>· <#00FF00>!anuncio <msg> <tiempo>\n"

        await self.highrise.send_message(conversation_id, menu)

    # ── on_message ────────────────────────────────────────────────────

    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        if not hasattr(self, 'session_metadata') or user_id == self.session_metadata.user_id:
            return

        user_conversations[user_id] = conversation_id
        try:
            db.save_conversation_id(user_id, conversation_id)
        except Exception as e:
            print(f"⚠️ No se pudo guardar conversation_id: {e}")

        user_data = db.get_or_create_user(user_id)

        # ── Verificar ban ──────────────────────────────────────────
        if user_data.get("is_banned") and user_id != HOSTER_OWNER_ID:
            await self.highrise.send_message(
                conversation_id,
                "<#E74C3C>⛔ Tu acceso al sistema ha sido restringido.\n"
                "<#FFFFFF>Contacta al administrador para más información.")
            return

        # ── Regalo pendiente ───────────────────────────────────────
        if user_data["gift_from"]:
            await self.highrise.send_message(
                conversation_id,
                f"<#FFD700>🎁 ¡Tienes un aviso! <#FFFFFF>El usuario <#00FFFF>{user_data['gift_from']} "
                f"<#FFFFFF>te ha otorgado un beneficio/saldo.")
            db.clear_pending_gift(user_id)

        # ── Conversación nueva → menú de bienvenida ───────────────
        if is_new_conversation:
            await self._send_menu(user_id, conversation_id)
            return

        # ── Leer último mensaje del usuario ───────────────────────
        try:
            msgs_resp = await self.highrise.get_messages(conversation_id)
            if not msgs_resp or not msgs_resp.messages:
                return
            text = None
            bot_id_self = self.session_metadata.user_id
            for msg in msgs_resp.messages:
                if msg.sender_id != bot_id_self:
                    text = msg.content.strip()
                    break
            if not text:
                return
        except Exception as e:
            print(f"❌ Error al obtener mensajes: {e}")
            return

        parts = text.split()
        cmd   = parts[0].lower()

        # ── Flujo paso a paso: !giftbot ───────────────────────────
        if user_id == HOSTER_OWNER_ID and user_id in gift_sessions:
            if cmd == "!cancel":
                del gift_sessions[user_id]
                await self.highrise.send_message(conversation_id, "<#E74C3C>🚫 Proceso cancelado.")
                return

            step = gift_sessions[user_id]["step"]

            if step == 1:
                gift_sessions[user_id]["target_user"] = text
                gift_sessions[user_id]["step"] = 2
                await self.highrise.send_message(conversation_id,
                    "<#FFFFFF>2️⃣ Escribe la <#00FFFF>Categoría <#FFFFFF>del bot (ej: musica, fiesta):")
                return

            elif step == 2:
                gift_sessions[user_id]["category"] = text.lower()
                gift_sessions[user_id]["step"] = 3
                await self.highrise.send_message(conversation_id,
                    "<#FFFFFF>3️⃣ Envía el <#00FFFF>Token <#FFFFFF>del bot:")
                return

            elif step == 3:
                gift_sessions[user_id]["token"] = text
                gift_sessions[user_id]["step"] = 4
                await self.highrise.send_message(conversation_id,
                    "<#FFFFFF>4️⃣ Envía la <#00FFFF>ID de la Sala <#FFFFFF>(Room ID):")
                return

            elif step == 4:
                gift_sessions[user_id]["room_id"] = text
                gift_sessions[user_id]["step"] = 5
                await self.highrise.send_message(conversation_id,
                    "<#FFFFFF>5️⃣ Escribe el <#FFD700>Tiempo libre <#FFFFFF>que quieras darles:\n"
                    "<#85E3FF>👉 Usa la cantidad seguida de 'm', 'h' o 'd'\n"
                    "<#AAAAAA>Ejemplos: 15m, 45m, 3h, 10d")
                return

            elif step == 5:
                duration = text.lower().strip()
                if not re.match(r"^(\d+)([mhd])$", duration):
                    await self.highrise.send_message(conversation_id,
                        "<#E74C3C>⚠️ Formato de tiempo inválido.\n"
                        "<#FFFFFF>Ingresa cantidad + <#FFD700>m<#FFFFFF>, <#FFD700>h <#FFFFFF>o <#FFD700>d<#FFFFFF>.\n"
                        "<#AAAAAA>Ejemplos válidos: 15m, 40m, 5h, 12d.")
                    return

                data    = gift_sessions[user_id]
                success, proc = deploy_bot_instance(
                    data["target_user"], data["category"], data["room_id"], data["token"])
                if success:
                    bot_id_new, exp_date = db.create_bot_entry(
                        data["target_user"], data["category"],
                        data["room_id"], data["token"], duration_str=duration)
                    if proc:
                        running_processes[bot_id_new] = proc
                    db.set_pending_gift(data["target_user"], "Propietario (Bot de Regalo)")
                    await self.highrise.send_message(conversation_id,
                        f"<#2ECC71>🎉 ¡Instancia regalada correctamente!\n\n"
                        f"<#FFFFFF>👤 Usuario: <#00FFFF>{data['target_user']}\n"
                        f"<#FFFFFF>🤖 Bot ID: <#00FFFF>{bot_id_new}\n"
                        f"<#FFFFFF>⏱️ Tiempo: <#FFD700>{duration}\n"
                        f"<#FFFFFF>📅 Expiración: <#2ECC71>{exp_date} UTC")
                else:
                    await self.highrise.send_message(conversation_id,
                        "<#E74C3C>❌ Error al desplegar la plantilla.")
                del gift_sessions[user_id]
                return

        # ── Flujo paso a paso: !buy ───────────────────────────────
        if user_id in buy_sessions:
            session  = buy_sessions[user_id]
            step     = session["step"]
            cat      = session["category"]
            is_admin = (user_id == HOSTER_OWNER_ID)

            if text.startswith("!"):
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>⛔ Tienes una compra en proceso.\n"
                    "<#FFFFFF>Responde solo al asistente de compra.\n"
                    "<#AAAAAA>En la confirmación escribe <#FFFFFF>cancelar <#AAAAAA>para salir.")
                return

            if step == 1:
                opts = DURATION_OPTIONS[cat]
                if text not in [o[0] for o in opts]:
                    lines = "\n".join(
                        f"<#FFFFFF>[{o[0]}] <#85E3FF>{o[2]}   <#FFFFFF>│ <#FFD700>{o[3]:,} 🪙"
                        for o in opts)
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>⚠️ Opción inválida. Escribe el número del plan:\n\n{lines}")
                    return

                chosen = next(o for o in opts if o[0] == text)
                session.update(duration=chosen[1], dur_label=chosen[2],
                               price=chosen[3], step=2)

                fresh = db.get_or_create_user(user_id)
                if not is_admin and fresh["balance"] < chosen[3]:
                    missing = chosen[3] - fresh["balance"]
                    del buy_sessions[user_id]
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>🛑 TRANSACCIÓN RECHAZADA\n\n"
                        f"<#FFFFFF>├── <#85E3FF>Costo del Plan <#FFFFFF>: <#FFD700>{chosen[3]:,} Oro\n"
                        f"<#FFFFFF>├── <#85E3FF>Tu Saldo Actual<#FFFFFF>: <#FFD700>{fresh['balance']:,} Oro\n"
                        f"<#FFFFFF>└── <#E74C3C>Saldo Faltante <#FFFFFF>: <#E74C3C>{missing:,} Oro\n"
                        f"{DIVIDER}")
                    return

                await self.highrise.send_message(conversation_id,
                    f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n"
                    f"<#FFD700>🛒 CONFIRMAR COMPRA\n"
                    f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n"
                    f"<#FFFFFF>{CATEGORY_EMOJIS[cat]} Categoría: <#00FFFF>{CATEGORY_NAMES[cat]}\n"
                    f"<#FFFFFF>⏱️ Duración: <#00FFFF>{chosen[2]}\n"
                    f"<#FFFFFF>💰 Precio: <#FFD700>{chosen[3]:,} 🪙\n"
                    f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"<#2ECC71>aceptar <#FFFFFF>→ Confirmar\n"
                    f"<#E74C3C>cancelar <#FFFFFF>→ Salir")
                return

            elif step == 2:
                if text.lower() == "aceptar":
                    session["step"] = 3
                    await self.highrise.send_message(conversation_id,
                        "<#2ECC71>✅ ¡Compra confirmada!\n\n"
                        "<#FFFFFF>🔑 Paso 1/2 — <#00FFFF>Token del bot:\n"
                        "<#FFFFFF>Envía el <#FFD700>API Token <#FFFFFF>del bot que quieres alojar.")
                elif text.lower() in ["cancelar", "cancel"]:
                    del buy_sessions[user_id]
                    await self.highrise.send_message(conversation_id, "<#E74C3C>🚫 Compra cancelada.")
                else:
                    await self.highrise.send_message(conversation_id,
                        "<#FFFFFF>Escribe <#2ECC71>aceptar <#FFFFFF>o <#E74C3C>cancelar<#FFFFFF>.")
                return

            elif step == 3:
                token_val = text.strip()
                if not re.match(r'^[a-f0-9]{64}$', token_val):
                    await self.highrise.send_message(conversation_id,
                        "<#E74C3C>❌ Token inválido (64 caracteres hex).\n"
                        "<#FFFFFF>Intenta de nuevo:")
                    return
                session.update(token=token_val, step=4)
                await self.highrise.send_message(conversation_id,
                    "<#2ECC71>✅ Token válido.\n\n"
                    "<#FFFFFF>📍 Paso 2/2 — <#00FFFF>ID de la sala:\n"
                    "<#FFFFFF>Envía el <#FFD700>Room ID <#FFFFFF>de la sala.")
                return

            elif step == 4:
                room_id_val = text.strip()
                token_val   = session["token"]
                duration    = session["duration"]
                price       = session["price"]
                dur_label   = session["dur_label"]
                del buy_sessions[user_id]

                fresh = db.get_or_create_user(user_id)
                if not is_admin and fresh["balance"] < price:
                    missing = price - fresh["balance"]
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>🛑 TRANSACCIÓN RECHAZADA\n\n"
                        f"<#FFFFFF>├── <#85E3FF>Costo del Plan <#FFFFFF>: <#FFD700>{price:,} Oro\n"
                        f"<#FFFFFF>├── <#85E3FF>Tu Saldo Actual<#FFFFFF>: <#FFD700>{fresh['balance']:,} Oro\n"
                        f"<#FFFFFF>└── <#E74C3C>Saldo Faltante <#FFFFFF>: <#E74C3C>{missing:,} Oro\n"
                        f"{DIVIDER}")
                    return

                info = db.get_category_info(cat)
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>🛑 La categoría <#00FFFF>{CATEGORY_NAMES[cat]} "
                        f"<#FFFFFF>está en mantenimiento.")
                    return

                await self.highrise.send_message(conversation_id, "<#AAAAAA>⏳ Desplegando tu bot...")
                dur_param = None if duration == "perm" else duration
                success, proc = deploy_bot_instance(user_id, cat, room_id_val, token_val)
                if success:
                    if not is_admin:
                        db.update_gold(user_id, -price)
                    bot_id_new, exp_date = db.create_bot_entry(
                        user_id, cat, room_id_val, token_val, duration_str=dur_param)
                    if proc:
                        running_processes[bot_id_new] = proc
                    await self.highrise.send_message(conversation_id,
                        f"<#2ECC71>🚀 ¡BOT DESPLEGADO CON ÉXITO!\n\n"
                        f"<#FFFFFF>├── <#85E3FF>ID del Bot   <#FFFFFF>: <#00FFFF>#{bot_id_new}\n"
                        f"<#FFFFFF>└── <#85E3FF>Expiración   <#FFFFFF>: <#FFD700>"
                        f"{exp_date if exp_date else 'Permanente'} UTC\n\n"
                        f"<#FFD700>⚠️ IMPORTANTE<#FFFFFF>: Recuerda dar permisos de "
                        f"<#00FFFF>Moderador <#FFFFFF>y <#00FFFF>Diseñador <#FFFFFF>al bot en tu sala.\n"
                        f"{DIVIDER}")
                else:
                    await self.highrise.send_message(conversation_id,
                        "<#E74C3C>❌ Error crítico al desplegar. Verifica token y Room ID.")
                return

        # ─────────────────────────────────────────────────────────────
        # COMANDOS PRINCIPALES
        # ─────────────────────────────────────────────────────────────

        if cmd == "!giftbot" and user_id == HOSTER_OWNER_ID:
            gift_sessions[user_id] = {"step": 1}
            await self.highrise.send_message(conversation_id,
                "<#FFD700>🎁 INICIANDO ASISTENTE PARA REGALAR BOT:\n\n"
                "<#FFFFFF>1️⃣ Envía la <#00FFFF>ID del usuario <#FFFFFF>que recibirá el regalo:\n"
                "<#AAAAAA>(Escribe '!cancel' en cualquier momento para salir)")

        elif cmd == "!menu":
            await self._send_menu(user_id, conversation_id)

        elif cmd in ["!saldo", "!balance"]:
            await self.highrise.send_message(conversation_id,
                f"<#FFFFFF>👤 Usuario ID: <#00FFFF>{user_id}\n"
                f"<#FFFFFF>💰 Saldo actual: <#FFD700>{user_data['balance']} 🪙")

        elif cmd == "!plan":
            await self._handle_plan(conversation_id, parts)

        elif cmd == "!buy":
            await self._handle_buy(user_id, conversation_id, parts, user_data)

        elif cmd == "!mybots":
            await self._handle_mybots(user_id, conversation_id)

        elif cmd == "!mover":
            await self._handle_mover(user_id, conversation_id, parts)

        elif cmd == "!restart":
            await self._handle_restart(user_id, conversation_id, parts)

        elif cmd == "!soporte":
            await self._handle_soporte(user_id, conversation_id, parts)

        elif cmd == "!lang":
            await self._handle_lang(user_id, conversation_id, parts)

        elif cmd == "!gift":
            await self._handle_gift(user_id, conversation_id, parts, user_data)

        elif cmd in ["!tex", "!anuncio", "!parar", "!broadcast",
                     "!addgold", "!mantenimiento", "!detener", "!activar",
                     "!stats", "!id", "!tickets", "!responder", "!addtime",
                     "!banuser", "!unbanuser", "!cancel"]:
            if user_id != HOSTER_OWNER_ID:
                return  # Silencioso para no revelar comandos admin
            await self._handle_admin(user_id, conversation_id, cmd, parts)

        else:
            await self.highrise.send_message(conversation_id,
                "<#E74C3C>❓ Comando no reconocido.\n"
                "<#FFFFFF>Escribe <#00FF00>!menu <#FFFFFF>para ver las opciones disponibles.")

    # ═════════════════════════════════════════════════════════════════
    # HANDLERS DE COMANDOS
    # ═════════════════════════════════════════════════════════════════

    # ── !plan ─────────────────────────────────────────────────────────
    async def _handle_plan(self, conversation_id: str, parts: list) -> None:
        if len(parts) == 1:
            await self.highrise.send_message(conversation_id,
                "<#FFD700>🤖 NEX-HOST | TABLA DE PRECIOS 24/7\n\n"
                "<#00FFFF>🎵 BOT DE MÚSICA:\n"
                "<#85E3FF>24 Horas    <#FFFFFF>│ <#FFD700>400 🪙\n"
                "<#85E3FF>7 Días      <#FFFFFF>│ <#FFD700>900 🪙\n"
                "<#85E3FF>15 Días     <#FFFFFF>│ <#FFD700>1,600 🪙\n"
                "<#85E3FF>30 Días     <#FFFFFF>│ <#FFD700>3,200 🪙\n"
                "<#2ECC71>Permanente  <#FFFFFF>│ <#FFD700>12,000 🪙\n\n"
                "<#FF69B4>🎉 BOT DE FIESTA:\n"
                "<#FFB6C1>24 Horas    <#FFFFFF>│ <#FFD700>300 🪙\n"
                "<#FFB6C1>7 Días      <#FFFFFF>│ <#FFD700>800 🪙\n"
                "<#FFB6C1>15 Días     <#FFFFFF>│ <#FFD700>1,500 🪙\n"
                "<#FFB6C1>30 Días     <#FFFFFF>│ <#FFD700>6,000 🪙\n"
                "<#2ECC71>Permanente  <#FFFFFF>│ <#FFD700>10,000 🪙\n\n"
                "<#FFA500>⚙️ OTROS PLANES:\n"
                "<#FFFFFF>Juegos / Personalizados │ Contactar @_Kmi.77\n\n"
                "<#E74C3C>🛒 ¿CÓMO COMPRAR?\n"
                "<#00FF00>!buy 1 <#FFFFFF>(Música) · <#00FF00>!buy 3 <#FFFFFF>(Fiesta)")
            return

        sub = parts[1]
        if sub == "1":
            info = db.get_category_info("musica")
            if not info["active"] or info["maintenance"]:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>🛑 La categoría <#00FFFF>MÚSICA <#FFFFFF>está en mantenimiento.")
                return
            await self.highrise.send_message(conversation_id,
                "<#00FFFF>🎵 BOT DE MÚSICA:\n"
                "<#85E3FF>24 Horas    <#FFFFFF>│ <#FFD700>400 🪙\n"
                "<#85E3FF>7 Días      <#FFFFFF>│ <#FFD700>900 🪙\n"
                "<#85E3FF>15 Días     <#FFFFFF>│ <#FFD700>1,600 🪙\n"
                "<#85E3FF>30 Días     <#FFFFFF>│ <#FFD700>3,200 🪙\n"
                "<#2ECC71>Permanente  <#FFFFFF>│ <#FFD700>12,000 🪙\n\n"
                "<#00FF00>!buy 1 <#FFFFFF>para iniciar el proceso guiado.")
        elif sub == "2":
            await self.highrise.send_message(conversation_id,
                "<#FFA500>🎮 CATEGORÍA JUEGOS:\n"
                "<#FFFFFF>Esta categoría es personalizada.\n"
                "<#AAAAAA>Contacta a @_Kmi.77 para cotización.")
        elif sub == "3":
            info = db.get_category_info("fiesta")
            if not info["active"] or info["maintenance"]:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>🛑 La categoría <#00FFFF>FIESTA <#FFFFFF>está en mantenimiento.")
                return
            await self.highrise.send_message(conversation_id,
                "<#FF69B4>🎉 BOT DE FIESTA:\n"
                "<#FFB6C1>24 Horas    <#FFFFFF>│ <#FFD700>300 🪙\n"
                "<#FFB6C1>7 Días      <#FFFFFF>│ <#FFD700>800 🪙\n"
                "<#FFB6C1>15 Días     <#FFFFFF>│ <#FFD700>1,500 🪙\n"
                "<#FFB6C1>30 Días     <#FFFFFF>│ <#FFD700>6,000 🪙\n"
                "<#2ECC71>Permanente  <#FFFFFF>│ <#FFD700>10,000 🪙\n\n"
                "<#00FF00>!buy 3 <#FFFFFF>para iniciar el proceso guiado.")
        elif sub == "4":
            await self.highrise.send_message(conversation_id,
                "<#FFA500>⚙️ CATEGORÍA PERSONALIZADO:\n"
                "<#FFFFFF>Completamente a medida.\n"
                "<#AAAAAA>Contacta a @_Kmi.77 para cotización.")
        else:
            await self.highrise.send_message(conversation_id,
                "<#E74C3C>❌ Sintaxis incorrecta.\n"
                "<#FFFFFF>Usa: <#00FF00>!plan 1<#FFFFFF>, <#00FF00>!plan 2<#FFFFFF>, "
                "<#00FF00>!plan 3 <#FFFFFF>o <#00FF00>!plan 4")

    # ── !buy ──────────────────────────────────────────────────────────
    async def _handle_buy(self, user_id: str, conversation_id: str,
                          parts: list, user_data: dict) -> None:
        is_admin = (user_id == HOSTER_OWNER_ID)

        # ── Compra directa: !buy <cat> <tiempo> <token> <room_id> ──
        if len(parts) == 5:
            cat_input = parts[1].lower()
            duration  = parts[2].lower()
            token_val = parts[3].strip()
            room_id_v = parts[4].strip()

            if cat_input not in CATEGORY_MAP:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Categoría inválida.\n"
                    "<#FFFFFF>Usa: musica o fiesta")
                return

            cat = CATEGORY_MAP[cat_input]

            if not re.match(r'^[a-f0-9]{64}$', token_val):
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Token inválido (64 caracteres hex requeridos).")
                return

            if is_admin:
                price = 0
            else:
                price = PRICE_MAP.get(cat, {}).get(duration)
                if price is None:
                    opts = " | ".join(PRICE_MAP[cat].keys())
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>❌ Tiempo inválido para esta categoría.\n"
                        f"<#FFFFFF>Opciones disponibles: <#00FFFF>{opts}")
                    return

            info = db.get_category_info(cat)
            if not info["active"] or info["maintenance"]:
                await self.highrise.send_message(conversation_id,
                    f"<#E74C3C>🛑 La categoría <#00FFFF>{CATEGORY_NAMES[cat]} "
                    f"<#FFFFFF>está en mantenimiento.")
                return

            fresh = db.get_or_create_user(user_id)
            if not is_admin and fresh["balance"] < price:
                missing = price - fresh["balance"]
                await self.highrise.send_message(conversation_id,
                    f"<#E74C3C>🛑 TRANSACCIÓN RECHAZADA\n\n"
                    f"<#FFFFFF>├── <#85E3FF>Costo del Plan <#FFFFFF>: <#FFD700>{price:,} Oro\n"
                    f"<#FFFFFF>├── <#85E3FF>Tu Saldo Actual<#FFFFFF>: <#FFD700>{fresh['balance']:,} Oro\n"
                    f"<#FFFFFF>└── <#E74C3C>Saldo Faltante <#FFFFFF>: <#E74C3C>{missing:,} Oro\n"
                    f"{DIVIDER}")
                return

            await self.highrise.send_message(conversation_id, "<#AAAAAA>⏳ Desplegando tu bot...")
            dur_param = None if duration == "perm" else duration
            success, proc = deploy_bot_instance(user_id, cat, room_id_v, token_val)
            if success:
                if not is_admin:
                    db.update_gold(user_id, -price)
                bot_id_new, exp_date = db.create_bot_entry(
                    user_id, cat, room_id_v, token_val, duration_str=dur_param)
                if proc:
                    running_processes[bot_id_new] = proc
                await self.highrise.send_message(conversation_id,
                    f"<#2ECC71>🚀 ¡BOT DESPLEGADO CON ÉXITO!\n\n"
                    f"<#FFFFFF>├── <#85E3FF>ID del Bot   <#FFFFFF>: <#00FFFF>#{bot_id_new}\n"
                    f"<#FFFFFF>└── <#85E3FF>Expiración   <#FFFFFF>: <#FFD700>"
                    f"{exp_date if exp_date else 'Permanente'} UTC\n\n"
                    f"<#FFD700>⚠️ IMPORTANTE<#FFFFFF>: Recuerda dar permisos de "
                    f"<#00FFFF>Moderador <#FFFFFF>y <#00FFFF>Diseñador <#FFFFFF>al bot en tu sala.\n"
                    f"{DIVIDER}")
            else:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Error crítico al desplegar. Verifica token y Room ID.")
            return

        # ── Flujo guiado: !buy <cat> ───────────────────────────────
        if len(parts) < 2:
            await self.highrise.send_message(conversation_id,
                "<#FFD700>🛒 COMPRAR UN BOT:\n\n"
                "<#FFFFFF>• <#00FF00>!buy 1 <#FFFFFF>— 🎵 Bot de Música\n"
                "<#FFFFFF>• <#00FF00>!buy 3 <#FFFFFF>— 🎉 Bot de Fiesta")
            return

        cat_input = parts[1].lower()
        if cat_input not in CATEGORY_MAP:
            await self.highrise.send_message(conversation_id,
                "<#E74C3C>❌ Categoría inválida.\n\n"
                "<#FFFFFF>• <#00FF00>!buy 1 <#FFFFFF>— 🎵 Música\n"
                "<#FFFFFF>• <#00FF00>!buy 3 <#FFFFFF>— 🎉 Fiesta")
            return

        cat  = CATEGORY_MAP[cat_input]
        info = db.get_category_info(cat)
        if not info["active"] or info["maintenance"]:
            await self.highrise.send_message(conversation_id,
                f"<#E74C3C>🛑 La categoría <#00FFFF>{CATEGORY_NAMES[cat]} "
                f"<#FFFFFF>está en mantenimiento.")
            return

        opts  = DURATION_OPTIONS[cat]
        lines = "\n".join(
            f"<#FFFFFF>[{o[0]}] <#85E3FF>{o[2]}   <#FFFFFF>│ <#FFD700>{o[3]:,} 🪙"
            for o in opts)
        buy_sessions[user_id] = {"step": 1, "category": cat,
                                  "duration": None, "dur_label": None,
                                  "price": None, "token": None}
        await self.highrise.send_message(conversation_id,
            f"<#FFD700>{CATEGORY_EMOJIS[cat]} PLANES {CATEGORY_NAMES[cat]}:\n\n"
            f"{lines}\n\n"
            f"<#FFFFFF>💰 Tu saldo: <#FFD700>{user_data['balance']:,} 🪙\n\n"
            f"<#AAAAAA>✍️ Escribe el número del plan que deseas:")

    # ── !mybots ───────────────────────────────────────────────────────
    async def _handle_mybots(self, user_id: str, conversation_id: str) -> None:
        user_bots = db.get_user_bots(user_id)
        if not user_bots:
            await self.highrise.send_message(conversation_id,
                "<#AAAAAA>ℹ️ No tienes ningún bot alojado.")
            return

        if len(user_bots) == 1:
            b_id, r_id, st, cat, exp = user_bots[0]
            time_left = format_time_remaining(exp)
            await self.highrise.send_message(conversation_id,
                f"<#FFD700>🤖 NEX-HOST <#FFFFFF>│ <#00FFFF>MI BOT ALOJADO\n\n"
                f"<#FFFFFF>├── <#85E3FF>Tipo        <#FFFFFF>: <#FF69B4>{cat.upper()}\n"
                f"<#FFFFFF>├── <#85E3FF>Sala        <#FFFFFF>: <#00FFFF>{r_id}\n"
                f"<#FFFFFF>├── <#85E3FF>Expiración  <#FFFFFF>: <#FFD700>{time_left} restantes\n"
                f"<#FFFFFF>└── <#85E3FF>Estado      <#FFFFFF>: <#2ECC71>● ACTIVO\n"
                f"{DIVIDER}")
        else:
            lines = ""
            for i, (b_id, r_id, st, cat, exp) in enumerate(user_bots, 1):
                time_left = format_time_remaining(exp)
                lines += (f"<#00FFFF> [{i}] <#FFFFFF>Bot {cat.capitalize()}  "
                          f"<#85E3FF>│ Sala: {r_id} <#FFFFFF>│ Expira: <#FFD700>{time_left}\n")
            await self.highrise.send_message(conversation_id,
                f"<#FFD700>🤖 NEX-HOST <#FFFFFF>│ <#00FFFF>MIS BOTS ALOJADOS\n\n"
                f"{lines}\n"
                f"<#2ECC71>👉 Usa: <#FFFFFF>!restart <número> <#AAAAAA>o <#FFFFFF>!mover <número> <room_id>\n"
                f"{DIVIDER}")

    # ── !mover ────────────────────────────────────────────────────────
    async def _handle_mover(self, user_id: str, conversation_id: str, parts: list) -> None:
        user_bots = db.get_user_bots(user_id)
        if not user_bots:
            await self.highrise.send_message(conversation_id,
                "<#AAAAAA>ℹ️ No tienes bots alojados para mover.")
            return

        async def do_move(b_id, cat, new_room):
            bot_info = db.get_bot_by_id(b_id)
            success, _ = redeploy_bot(b_id, user_id, cat, new_room, bot_info["api_token"])
            if success:
                db.update_bot_room(b_id, new_room)
                await self.highrise.send_message(conversation_id,
                    f"<#2ECC71>🚚 BOT MOVIDO CON ÉXITO\n\n"
                    f"<#FFFFFF>├── <#85E3FF>Bot Afectado <#FFFFFF>: <#00FFFF>ID #{b_id}\n"
                    f"<#FFFFFF>└── <#85E3FF>Nueva Sala   <#FFFFFF>: <#00FFFF>{new_room}\n\n"
                    f"<#AAAAAA>El bot se ha reconectado automáticamente a la nueva sala.\n"
                    f"{DIVIDER}")
            else:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Error al mover el bot. Verifica que la plantilla exista.")

        if len(user_bots) == 1:
            # !mover <room_id>
            if len(parts) < 2:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Sintaxis: <#FFFFFF>!mover <nueva_room_id>")
                return
            b_id, r_id, st, cat, exp = user_bots[0]
            await do_move(b_id, cat, parts[1])

        elif len(parts) >= 3 and parts[1].isdigit():
            # !mover <número> <room_id>
            idx = int(parts[1]) - 1
            if idx < 0 or idx >= len(user_bots):
                await self.highrise.send_message(conversation_id,
                    f"<#E74C3C>❌ Número inválido. Tienes {len(user_bots)} bot(s).")
                return
            b_id, r_id, st, cat, exp = user_bots[idx]
            await do_move(b_id, cat, parts[2])

        else:
            # Múltiples bots sin especificar → menú de selección
            lines = "".join(
                f"<#00FFFF> [{i}] <#FFFFFF>Bot {cat.capitalize()}  <#85E3FF>│ Sala Actual: {r_id}\n"
                for i, (b_id, r_id, st, cat, exp) in enumerate(user_bots, 1))
            await self.highrise.send_message(conversation_id,
                f"<#FFD700>🚚 NEX-HOST <#FFFFFF>│ <#00FFFF>SELECCIÓN DE BOT A MOVER\n\n"
                f"<#FFFFFF>Tienes varios bots. Especifica el número y la nueva sala:\n\n"
                f"{lines}\n"
                f"<#2ECC71>👉 Usa: <#FFFFFF>!mover <número> <nueva_room_id> "
                f"<#AAAAAA>(Ejemplo: !mover 1 77abc8892)\n"
                f"{DIVIDER}")

    # ── !restart ──────────────────────────────────────────────────────
    async def _handle_restart(self, user_id: str, conversation_id: str, parts: list) -> None:
        user_bots = db.get_user_bots(user_id)
        if not user_bots:
            await self.highrise.send_message(conversation_id,
                "<#AAAAAA>ℹ️ No tienes bots alojados.")
            return

        def do_restart(b_id, r_id, cat):
            bot_info = db.get_bot_by_id(b_id)
            return redeploy_bot(b_id, user_id, cat, r_id, bot_info["api_token"])

        if len(user_bots) == 1 or (len(parts) >= 2 and parts[1].isdigit()):
            if len(user_bots) == 1:
                b_id, r_id, st, cat, exp = user_bots[0]
            else:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(user_bots):
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>❌ Número inválido. Tienes {len(user_bots)} bot(s).")
                    return
                b_id, r_id, st, cat, exp = user_bots[idx]

            await self.highrise.send_message(conversation_id,
                f"<#2ECC71>🔄 REINICIANDO BOT\n"
                f"<#FFFFFF>Procesando el reinicio de la instancia <#00FFFF>ID #{b_id}"
                f"<#FFFFFF>... Por favor espera unos segundos.\n"
                f"{DIVIDER}")
            do_restart(b_id, r_id, cat)

        else:
            # Múltiples bots sin número → menú de selección
            lines = "".join(
                f"<#00FFFF> [{i}] <#FFFFFF>Bot {cat.capitalize()}  <#85E3FF>│ Sala: {r_id}\n"
                for i, (b_id, r_id, st, cat, exp) in enumerate(user_bots, 1))
            await self.highrise.send_message(conversation_id,
                f"<#FFD700>🤖 NEX-HOST <#FFFFFF>│ <#00FFFF>SELECCIÓN DE BOT\n\n"
                f"<#FFFFFF>Tienes varios bots activos. Indica el número a reiniciar:\n\n"
                f"{lines}\n"
                f"<#2ECC71>👉 Usa: <#FFFFFF>!restart <número> <#AAAAAA>(Ejemplo: !restart 1)\n"
                f"{DIVIDER}")

    # ── !soporte ──────────────────────────────────────────────────────
    async def _handle_soporte(self, user_id: str, conversation_id: str, parts: list) -> None:
        if len(parts) < 2:
            await self.highrise.send_message(conversation_id,
                "<#E74C3C>❌ Sintaxis: <#FFFFFF>!soporte <tu mensaje al admin>")
            return
        mensaje = " ".join(parts[1:])
        try:
            user_info = await self.webapi.get_user(user_id)
            username  = user_info.username
        except Exception:
            username = user_id
        ticket_id = db.create_ticket(user_id, username, mensaje)
        await self.highrise.send_message(conversation_id,
            f"<#2ECC71>📩 TICKET REGISTRADO CON ÉXITO\n"
            f"<#FFFFFF>├── <#85E3FF>Número de Ticket<#FFFFFF>: <#00FFFF>#{ticket_id}\n"
            f"<#FFFFFF>└── <#85E3FF>Estado          <#FFFFFF>: <#FFD700>En espera de respuesta\n\n"
            f"<#AAAAAA>Un administrador responderá directamente a este chat privado.\n"
            f"{DIVIDER}")

    # ── !lang ─────────────────────────────────────────────────────────
    async def _handle_lang(self, user_id: str, conversation_id: str, parts: list) -> None:
        valid_langs = {"es", "en", "pt"}

        if len(parts) < 3:
            await self.highrise.send_message(conversation_id,
                "<#E74C3C>❌ Sintaxis:\n"
                "<#FFFFFF>!lang host <es/en/pt>     — Idioma del Bot Hoster\n"
                "<#FFFFFF>!lang bot <es/en/pt>       — Idioma de tu bot alojado")
            return

        scope = parts[1].lower()

        if scope == "host":
            lang = parts[2].lower()
            if lang not in valid_langs:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Idioma inválido. Usa: <#FFFFFF>es<#AAAAAA>, <#FFFFFF>en<#AAAAAA>, <#FFFFFF>pt")
                return
            db.set_user_host_language(user_id, lang)
            await self.highrise.send_message(conversation_id,
                f"<#2ECC71>🌐 IDIOMA DEL SISTEMA ACTUALIZADO\n"
                f"<#FFFFFF>El idioma del Bot Hoster se ha configurado en: <#00FFFF>{LANG_NAMES[lang]}\n"
                f"{DIVIDER}")
            return

        if scope == "bot":
            user_bots = db.get_user_bots(user_id)
            if not user_bots:
                await self.highrise.send_message(conversation_id,
                    "<#AAAAAA>ℹ️ No tienes bots alojados.")
                return

            # Detectar si hay número: !lang bot <num> <idioma> o !lang bot <idioma>
            if len(parts) == 4 and parts[2].isdigit():
                idx  = int(parts[2]) - 1
                lang = parts[3].lower()
            else:
                idx  = -1  # decidir abajo
                lang = parts[2].lower()

            if lang not in valid_langs:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Idioma inválido. Usa: es, en, pt")
                return

            async def apply_lang(b_id, cat):
                db.set_bot_language(b_id, lang)
                ipath = os.path.join(HOSTED_INSTANCES_DIR, f"user_{user_id}_{cat.lower()}")
                try:
                    with open(os.path.join(ipath, "lang.txt"), "w", encoding="utf-8") as f:
                        f.write(lang)
                except Exception:
                    pass
                await self.highrise.send_message(conversation_id,
                    f"<#2ECC71>🌐 IDIOMA DE INSTANCIA ACTUALIZADO\n"
                    f"<#FFFFFF>├── <#85E3FF>Bot Afectado<#FFFFFF>: <#00FFFF>ID #{b_id}\n"
                    f"<#FFFFFF>└── <#85E3FF>Nuevo Idioma<#FFFFFF>: <#00FFFF>{LANG_NAMES[lang]}\n"
                    f"{DIVIDER}")

            if len(user_bots) == 1:
                await apply_lang(user_bots[0][0], user_bots[0][3])
            elif idx >= 0:
                if idx >= len(user_bots):
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>❌ Número inválido. Tienes {len(user_bots)} bot(s).")
                    return
                await apply_lang(user_bots[idx][0], user_bots[idx][3])
            else:
                lines = "".join(
                    f"<#00FFFF> [{i}] <#FFFFFF>Bot {cat.capitalize()}  <#85E3FF>│ Sala: {r_id}\n"
                    for i, (b_id, r_id, st, cat, exp) in enumerate(user_bots, 1))
                await self.highrise.send_message(conversation_id,
                    f"<#FFD700>🌐 NEX-HOST <#FFFFFF>│ <#00FFFF>SELECCIÓN DE BOT\n\n"
                    f"<#FFFFFF>Tienes varios bots. Especifica el número:\n\n"
                    f"{lines}\n"
                    f"<#2ECC71>👉 Usa: <#FFFFFF>!lang bot <número> <idioma> "
                    f"<#AAAAAA>(Ejemplo: !lang bot 1 es)\n"
                    f"{DIVIDER}")
            return

        await self.highrise.send_message(conversation_id,
            "<#E74C3C>❌ Sintaxis: <#FFFFFF>!lang host <es/en/pt> "
            "<#AAAAAA>o <#FFFFFF>!lang bot <es/en/pt>")

    # ── !gift ─────────────────────────────────────────────────────────
    async def _handle_gift(self, user_id: str, conversation_id: str,
                           parts: list, user_data: dict) -> None:
        if len(parts) != 3 or not parts[2].isdigit():
            await self.highrise.send_message(conversation_id,
                "<#E74C3C>❌ Sintaxis: <#FFFFFF>!gift <user_id> <monto>")
            return
        target_id = parts[1]
        amount    = int(parts[2])
        if amount <= 0:
            await self.highrise.send_message(conversation_id,
                "<#E74C3C>⚠️ El monto debe ser mayor a 0.")
        elif user_data["balance"] < amount:
            await self.highrise.send_message(conversation_id,
                f"<#E74C3C>🛑 Saldo insuficiente.\n"
                f"<#FFFFFF>Tu saldo: <#FFD700>{user_data['balance']} 🪙")
        else:
            db.update_gold(user_id, -amount)
            db.update_gold(target_id, amount)
            db.set_pending_gift(target_id, f"@{user_id}")
            await self.highrise.send_message(conversation_id,
                f"<#2ECC71>💸 ¡Transferencia completada!\n"
                f"<#FFFFFF>Has enviado <#FFD700>{amount} 🪙 "
                f"<#FFFFFF>al usuario <#00FFFF>{target_id}<#FFFFFF>.")

    # ── Comandos exclusivos del administrador ─────────────────────────
    async def _handle_admin(self, user_id: str, conversation_id: str,
                            cmd: str, parts: list) -> None:

        if cmd == "!stats":
            stats = db.get_stats()
            await self.highrise.send_message(conversation_id,
                f"<#FFD700>📊 NEX-HOST <#FFFFFF>│ <#00FFFF>ESTADÍSTICAS DEL SISTEMA\n\n"
                f"<#FFFFFF>├── <#85E3FF>Bots Activos Online <#FFFFFF>: <#2ECC71>{stats['active_bots']} Instancias\n"
                f"<#FFFFFF>├── <#85E3FF>Clientes Registrados <#FFFFFF>: <#00FFFF>{stats['total_users']} Usuarios\n"
                f"<#FFFFFF>├── <#85E3FF>Tickets Pendientes  <#FFFFFF>: <#E74C3C>{stats['pending_tickets']} En Espera\n"
                f"<#FFFFFF>└── <#85E3FF>Ingresos Totales    <#FFFFFF>: <#FFD700>{stats['total_gold']:,} Oro\n"
                f"{DIVIDER}")

        elif cmd == "!id":
            if len(parts) >= 2:
                target_id   = parts[1]
                user_detail = db.get_user_detail(target_id)
                if not user_detail:
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>❌ Usuario <#00FFFF>{target_id} <#FFFFFF>no encontrado.")
                    return
                bots = db.get_user_bots(target_id)
                msg  = (
                    f"<#FFD700>👑 NEX-HOST <#FFFFFF>│ <#00FFFF>REGISTRO DE COMPRADOR\n\n"
                    f"<#85E3FF>👤 USUARIO   <#FFFFFF>: <#00FFFF>{target_id}\n"
                    f"<#FFD700>🪙 SALDO     <#FFFFFF>: <#FFD700>{user_detail['balance']:,} Oro\n"
                )
                if len(bots) == 1:
                    b_id, r_id, st, cat, exp = bots[0]
                    exp_display = exp if exp else "Permanente"
                    msg += (
                        f"\n<#85E3FF>🤖 BOT ALOJADO <#00FFFF>(ID #{b_id})\n"
                        f"<#FFFFFF>├── <#85E3FF>Tipo      <#FFFFFF>: <#FF69B4>{cat.upper()}\n"
                        f"<#FFFFFF>├── <#85E3FF>Sala      <#FFFFFF>: <#00FFFF>{r_id}\n"
                        f"<#FFFFFF>├── <#85E3FF>Expiración<#FFFFFF>: <#FFD700>{exp_display} UTC\n"
                        f"<#FFFFFF>└── <#85E3FF>Estado    <#FFFFFF>: <#2ECC71>● ACTIVO\n"
                    )
                elif len(bots) > 1:
                    msg += f"\n<#85E3FF>🤖 BOTS ALOJADOS <#FFFFFF>(<#00FFFF>{len(bots)}<#FFFFFF>):\n"
                    for i, (b_id, r_id, st, cat, exp) in enumerate(bots, 1):
                        tl = format_time_remaining(exp)
                        msg += (f"<#00FFFF> [{i}] <#FFFFFF>{cat.upper()} "
                                f"│ Sala: {r_id} │ Expira: <#FFD700>{tl}\n")
                else:
                    msg += "\n<#AAAAAA>Sin bots alojados actualmente."
                msg += f"\n{DIVIDER}"
                await self.highrise.send_message(conversation_id, msg)
            else:
                # Lista rápida de todos los compradores
                users_list = db.get_all_registered_users()
                if not users_list:
                    await self.highrise.send_message(conversation_id,
                        "<#AAAAAA>ℹ️ No hay compradores registrados aún.")
                    return
                msg = "<#FFD700>👑 NEX-HOST <#FFFFFF>│ <#00FFFF>COMPRADORES REGISTRADOS\n\n"
                for uid, uname, balance in users_list[:15]:
                    bots = db.get_user_bots(uid)
                    msg += (f"<#FFFFFF>• <#00FFFF>{uid} "
                            f"<#FFFFFF>│ <#FFD700>{balance:,} Oro "
                            f"<#FFFFFF>│ <#2ECC71>{len(bots)} bot(s)\n")
                msg += DIVIDER
                await self.highrise.send_message(conversation_id, msg)

        elif cmd == "!tickets":
            tickets = db.get_all_pending_tickets()
            if not tickets:
                await self.highrise.send_message(conversation_id,
                    "<#2ECC71>✅ No hay tickets pendientes. ¡Todo en orden!")
            else:
                await self.highrise.send_message(conversation_id,
                    f"<#FFD700>📩 NEX-HOST <#FFFFFF>│ <#FF69B4>TICKETS PENDIENTES "
                    f"<#FFFFFF>({len(tickets)})\n"
                    f"<#AAAAAA>Usa <#FFFFFF>!responder <#ticket> <mensaje> <#AAAAAA>para responder.")
                for t in tickets:
                    await self.highrise.send_message(conversation_id,
                        f"<#00FFFF>━━━ Ticket #{t['id']} ━━━\n"
                        f"<#85E3FF>👤 Usuario  <#FFFFFF>: <#00FFFF>{t['user_id']}\n"
                        f"<#85E3FF>📅 Fecha    <#FFFFFF>: <#AAAAAA>{t['created_at']} UTC\n"
                        f"<#85E3FF>💬 Mensaje  <#FFFFFF>:\n"
                        f"<#FFFFFF>» <#85E3FF>{t['message']}\n"
                        f"<#2ECC71>↩ !responder {t['id']} <tu respuesta>\n"
                        f"{DIVIDER}")

        elif cmd == "!responder":
            if len(parts) < 3 or not parts[1].isdigit():
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Sintaxis: <#FFFFFF>!responder <#ticket> <mensaje>\n"
                    "<#AAAAAA>Ejemplo: !responder 3 Tu bot ya está listo.")
                return
            ticket_id    = int(parts[1])
            response_msg = " ".join(parts[2:])
            ticket = db.get_ticket_by_id(ticket_id)
            if not ticket:
                await self.highrise.send_message(conversation_id,
                    f"<#E74C3C>❌ Ticket <#00FFFF>#{ticket_id} <#FFFFFF>no encontrado.")
                return
            if ticket["status"] != "pending":
                await self.highrise.send_message(conversation_id,
                    f"<#E74C3C>⚠️ El ticket <#00FFFF>#{ticket_id} <#FFFFFF>ya fue resuelto.")
                return
            target_id = ticket["user_id"]
            db.mark_ticket_resolved(ticket_id)
            # Obtener nombre de usuario real
            try:
                user_info = await self.webapi.get_user(target_id)
                display_name = user_info.username
            except Exception:
                display_name = target_id
            conv_id = user_conversations.get(target_id) or db.get_conversation_id(target_id)
            if conv_id:
                try:
                    import random
                    _cierres = [
                        "<#FFD700>✨ ¡Tu tranquilidad y tus salas son nuestra prioridad!",
                        "<#FFD700>🌟 Gracias por confiar en Nex-Host. ¡Estamos para servirte!",
                        "<#FFD700>💫 Recuerda que puedes escribir <#FFFFFF>!soporte<#FFD700> cuando lo necesites.",
                        "<#FFD700>🛡️ Nex-Host — Hosting premium, servicio de calidad.",
                        "<#FFD700>⚡ ¡Tu experiencia es lo que nos impulsa a mejorar cada día!",
                        "<#FFD700>🎯 Siempre estaremos aquí para apoyarte. ¡Hasta pronto!",
                        "<#FFD700>💎 En Nex-Host tu satisfacción es nuestra misión.",
                    ]
                    await self.highrise.send_message(conv_id,
                        f"<#FFD700>🛡️ [ NEX-HOST ] ── SYSTEM SUPPORT\n\n"
                        f"<#00FFFF>Estimado/a @{display_name}:\n\n"
                        f"<#FFFFFF>├── <#85E3FF>Estado<#FFFFFF>: <#2ECC71>Atendido\n"
                        f"<#FFFFFF>└── <#FF69B4>Detalle<#FFFFFF>: {response_msg}\n\n"
                        f"{random.choice(_cierres)}")
                    await self.highrise.send_message(conversation_id,
                        f"<#2ECC71>✅ Ticket <#00FFFF>#{ticket_id} <#2ECC71>resuelto. "
                        f"Respuesta enviada a <#00FFFF>@{display_name}<#2ECC71>.")
                except Exception as e:
                    await self.highrise.send_message(conversation_id,
                        f"<#E74C3C>❌ Error al enviar respuesta: {e}")
            else:
                await self.highrise.send_message(conversation_id,
                    f"<#E74C3C>⚠️ No hay conversación activa con <#00FFFF>{target_id}<#FFFFFF>.\n"
                    f"<#AAAAAA>El usuario debe enviar un mensaje primero.\n"
                    f"<#AAAAAA>(Ticket <#00FFFF>#{ticket_id} <#AAAAAA>marcado como resuelto de todas formas.)")

        elif cmd == "!addtime":
            if len(parts) != 3:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Sintaxis: <#FFFFFF>!addtime <bot_id> <tiempo>\n"
                    "<#AAAAAA>Ej: !addtime 1 15m · !addtime 1 3h · !addtime 1 7d")
                return
            try:
                target_bot_id = int(parts[1])
            except ValueError:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ El ID del bot debe ser un número.")
                return
            duration_str = parts[2].lower()
            new_exp = db.extend_bot_time(target_bot_id, duration_str)
            if new_exp is None:
                await self.highrise.send_message(conversation_id,
                    f"<#E74C3C>❌ Bot ID <#00FFFF>{target_bot_id} <#FFFFFF>no encontrado "
                    f"o formato de tiempo inválido.\n<#AAAAAA>Formato: 15m, 3h, 7d")
                return
            m = re.match(r"^(\d+)([mhd])$", duration_str)
            val, unit = m.group(1), m.group(2)
            unit_label = {"m": "Minuto(s)", "h": "Hora(s)", "d": "Día(s)"}[unit]
            await self.highrise.send_message(conversation_id,
                f"<#2ECC71>✅ TIEMPO AÑADIDO CON ÉXITO\n"
                f"<#FFFFFF>├── <#85E3FF>Bot Afectado    <#FFFFFF>: <#00FFFF>ID #{target_bot_id}\n"
                f"<#FFFFFF>├── <#85E3FF>Tiempo Sumado   <#FFFFFF>: <#FFD700>+{val} {unit_label}\n"
                f"<#FFFFFF>└── <#85E3FF>Nueva Expiración<#FFFFFF>: <#FFD700>{new_exp} UTC\n"
                f"{DIVIDER}")

        elif cmd == "!banuser":
            if len(parts) < 2:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Sintaxis: <#FFFFFF>!banuser <user_id>")
                return
            target_id = parts[1]
            db.ban_user(target_id)
            await self.highrise.send_message(conversation_id,
                f"<#E74C3C>⛔ ACCESO RESTRINGIDO\n"
                f"<#FFFFFF>El usuario <#00FFFF>{target_id} <#FFFFFF>ha sido suspendido del sistema.\n"
                f"{DIVIDER}")

        elif cmd == "!unbanuser":
            if len(parts) < 2:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Sintaxis: <#FFFFFF>!unbanuser <user_id>")
                return
            target_id = parts[1]
            db.unban_user(target_id)
            await self.highrise.send_message(conversation_id,
                f"<#2ECC71>✅ ACCESO RESTAURADO\n"
                f"<#FFFFFF>El usuario <#00FFFF>{target_id} <#FFFFFF>ha sido desbloqueado del sistema.\n"
                f"{DIVIDER}")

        elif cmd == "!broadcast":
            if len(parts) < 2:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>⚠️ Uso: <#00FF00>!broadcast <mensaje>")
            else:
                broadcast_msg = " ".join(parts[1:])
                recipients    = db.get_all_users_with_conversations()
                sent_count = failed_count = 0
                for uid, conv_id in recipients:
                    if uid == HOSTER_OWNER_ID:
                        continue
                    try:
                        await self.highrise.send_message(conv_id,
                            f"<#FFD700>📢 ANUNCIO:\n<#FFFFFF>{broadcast_msg}")
                        sent_count += 1
                    except Exception:
                        failed_count += 1
                await self.highrise.send_message(conversation_id,
                    f"<#2ECC71>✅ Broadcast enviado a <#FFD700>{sent_count} <#2ECC71>usuario(s)."
                    + (f"\n<#E74C3C>⚠️ {failed_count} fallaron." if failed_count else ""))

        elif cmd == "!tex":
            if len(parts) < 2:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>⚠️ Uso: <#00FF00>!tex <mensaje>")
            else:
                message_tex = " ".join(parts[1:])
                sent = self._write_tex_to_instances(message_tex)
                await self.highrise.send_message(conversation_id,
                    f"<#2ECC71>📢 Mensaje enviado a <#FFD700>{sent} <#2ECC71>bot(s) alojado(s).")

        elif cmd == "!anuncio":
            if len(parts) < 3:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>⚠️ Uso: <#00FF00>!anuncio <mensaje> <tiempo>\n"
                    "<#AAAAAA>Ej: !anuncio Hola! 5m")
            else:
                raw_time = parts[-1].lower()
                match    = re.match(r"^(\d+)([smh])$", raw_time)
                if not match:
                    await self.highrise.send_message(conversation_id,
                        "<#E74C3C>⚠️ Formato inválido. Usa s, m o h. Ej: 30s, 5m, 1h")
                else:
                    value, unit = int(match.group(1)), match.group(2)
                    interval    = value * {"s": 1, "m": 60, "h": 3600}[unit]
                    message_ann = " ".join(parts[1:-1])
                    if "task" in active_announcement:
                        active_announcement["task"].cancel()
                    task = asyncio.create_task(self._announcement_loop(message_ann, interval))
                    active_announcement.update(message=message_ann, interval=interval, task=task)
                    tiempo_fmt = f"{value}{'seg' if unit == 's' else 'min' if unit == 'm' else 'h'}"
                    await self.highrise.send_message(conversation_id,
                        f"<#2ECC71>✅ Anuncio activado cada <#FFD700>{tiempo_fmt}<#2ECC71>:\n"
                        f"<#FFFFFF>📢 {message_ann}\n\n"
                        f"<#AAAAAA>Usa !parar para detenerlo.")

        elif cmd == "!parar":
            if "task" in active_announcement:
                active_announcement["task"].cancel()
                active_announcement.clear()
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>🛑 Anuncio recurrente detenido.")
            else:
                await self.highrise.send_message(conversation_id,
                    "<#AAAAAA>ℹ️ No hay ningún anuncio activo.")

        elif cmd == "!addgold":
            if len(parts) == 3 and parts[2].isdigit():
                db.update_gold(parts[1], int(parts[2]))
                await self.highrise.send_message(conversation_id,
                    f"<#2ECC71>✅ Saldo actualizado correctamente.\n"
                    f"<#FFFFFF>Se han añadido <#FFD700>{parts[2]} 🪙 "
                    f"<#FFFFFF>a la cuenta de <#00FFFF>{parts[1]}<#FFFFFF>.")
            else:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Sintaxis: <#FFFFFF>!addgold <user_id> <cantidad>")

        elif cmd == "!mantenimiento":
            if len(parts) == 3 and parts[2] in ["on", "off"]:
                db.set_maintenance(parts[1], 1 if parts[2] == "on" else 0)
                estado = "<#E74C3C>ON (en mantenimiento)" if parts[2] == "on" else "<#2ECC71>OFF (activo)"
                await self.highrise.send_message(conversation_id,
                    f"<#2ECC71>✅ Mantenimiento de <#00FFFF>{parts[1]} <#FFFFFF>→ {estado}")
            else:
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>❌ Sintaxis: <#FFFFFF>!mantenimiento <cat> <on/off>")

        elif cmd in ["!detener", "!activar"]:
            if len(parts) == 2:
                db.set_active_status(parts[1], 0 if cmd == "!detener" else 1)
                estado = "<#E74C3C>DETENIDA" if cmd == "!detener" else "<#2ECC71>ACTIVA"
                await self.highrise.send_message(conversation_id,
                    f"<#2ECC71>✅ Categoría <#00FFFF>{parts[1]} <#FFFFFF>→ {estado}")
            else:
                await self.highrise.send_message(conversation_id,
                    f"<#E74C3C>❌ Sintaxis: <#FFFFFF>{cmd} <categoria>")

        elif cmd == "!cancel":
            if user_id in gift_sessions:
                del gift_sessions[user_id]
                await self.highrise.send_message(conversation_id,
                    "<#E74C3C>🚫 Proceso de !giftbot cancelado.")
            else:
                await self.highrise.send_message(conversation_id,
                    "<#AAAAAA>ℹ️ No hay proceso activo para cancelar.")
