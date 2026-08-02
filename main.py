import os
import shutil
import subprocess
import asyncio
import re
from highrise import BaseBot, User, Position, AnchorPosition
from highrise.models import SessionMetadata, CurrencyItem

from config import HOSTER_OWNER_ID, TEMPLATES_DIR, HOSTED_INSTANCES_DIR
import database as db

db.init_db()

# Guardado en memoria del estado paso a paso para !giftbot
gift_sessions = {}

# Flujo de compra paso a paso para usuarios: {user_id: {step, category, ...}}
buy_sessions = {}

# Constantes de categorías disponibles para compra
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

# Procesos activos en esta sesión: {bot_id: subprocess.Popen}
running_processes = {}

# Mapa de conversaciones activas: {user_id: conversation_id}
user_conversations = {}

# Anuncio recurrente activo: {"message": str, "interval": int, "task": asyncio.Task}
active_announcement = {}


def template_exists(bot_type: str) -> bool:
    """Verifica si la carpeta de plantilla existe y tiene archivos."""
    path = os.path.join(TEMPLATES_DIR, bot_type.lower())
    return os.path.isdir(path) and bool(os.listdir(path))


def deploy_bot_instance(user_id: str, bot_type: str, room_id: str, api_token: str):
    """ Clona la plantilla del bot, inyecta credenciales y ejecuta run.py """
    template_path = os.path.join(TEMPLATES_DIR, bot_type.lower())
    instance_path = os.path.join(HOSTED_INSTANCES_DIR, f"user_{user_id}_{bot_type.lower()}")

    if not os.path.exists(template_path):
        print(f"❌ La plantilla '{template_path}' no existe.")
        return False, None

    if os.path.exists(instance_path):
        shutil.rmtree(instance_path)

    shutil.copytree(template_path, instance_path)

    config_file_path = os.path.join(instance_path, "config.py")
    config_content = f"""# CONFIGURACIÓN GENERADA AUTOMÁTICAMENTE POR BOT HOSTER
ROOM_ID = "{room_id}"
API_TOKEN = "{api_token}"
BOT_OWNER_ID = "{user_id}"
HOSTER_OWNER_ID = "{HOSTER_OWNER_ID}"
"""
    with open(config_file_path, "w", encoding="utf-8") as f:
        f.write(config_content)

    try:
        proc = subprocess.Popen(["python", "run.py"], cwd=instance_path)
        print(f"🟢 Bot de {bot_type} desplegado para el usuario {user_id} (PID {proc.pid})")
        return True, proc
    except Exception as e:
        print(f"🔴 Error al ejecutar run.py del bot: {e}")
        return False, None


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
        """Revisa cada 60 segundos si hay bots expirados y los detiene."""
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
                    print(f"⏰ Bot ID {bot_id} marcado como expirado.")
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
        """Escribe console_message.txt en cada instancia activa."""
        sent = 0
        for bot_instance in db.get_active_bot_instances():
            owner_id, category = bot_instance
            ipath = os.path.join(HOSTED_INSTANCES_DIR, f"user_{owner_id}_{category.lower()}")
            if os.path.isdir(ipath):
                try:
                    with open(os.path.join(ipath, "console_message.txt"), "w", encoding="utf-8") as f:
                        f.write(message)
                    sent += 1
                except Exception as e:
                    print(f"❌ Error escribiendo a instancia {ipath}: {e}")
        return sent

    async def _announcement_loop(self, message: str, interval: int) -> None:
        """Loop que reenvía el mensaje a todos los bots alojados cada `interval` segundos."""
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

    async def _send_menu(self, user_id: str, conversation_id: str) -> None:
        """Envía el menú principal al usuario."""
        user_data = db.get_or_create_user(user_id)
        user_bots = db.get_user_bots(user_id)

        menu  = "<#FFD700>👋 ¡Hola! Bienvenido a Nex-Host (Hosting Bot 24/7).\n\n"
        menu += f"<#FFFFFF>💰 Tu Saldo: <#FFD700>{user_data['balance']} 🪙\n\n"
        menu += "<#00FFFF>📋 MENÚ DE COMANDOS:\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!menu <#FFFFFF>- Mostrar este menú\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!saldo <#FFFFFF>- Consultar balance\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!plan <#FFFFFF>- Ver categorías y precios\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!buy 1 <#FFFFFF>(Música) · <#00FF00>!buy 3 <#FFFFFF>(Fiesta) - Comprar bot\n"
        menu += "<#FFFFFF>🔹 <#00FF00>!gift <user_id> <monto> <#FFFFFF>- Regalar saldo\n"

        if len(user_bots) == 1:
            b_id, r_id, st, cat, exp = user_bots[0]
            exp_info = f"<#FFD700>(Expira: {exp})" if exp else "<#FFD700>(Permanente)"
            menu += (
                f"\n<#85E3FF>🤖 TU BOT: <#FFFFFF>ID <#00FFFF>{b_id} "
                f"<#FFFFFF>| Tipo: <#00FFFF>{cat} "
                f"<#FFFFFF>| Sala: <#00FFFF>{r_id} "
                f"<#FFFFFF>| Estado: <#2ECC71>{st} {exp_info}\n"
            )
        elif len(user_bots) > 1:
            menu += f"\n<#85E3FF>🤖 Tienes <#FFD700>{len(user_bots)} <#85E3FF>bots registrados. Usa <#00FF00>!mybots <#85E3FF>para ver la lista.\n"

        if user_id == HOSTER_OWNER_ID:
            menu += "\n<#FFD700>👑 PANEL ADMIN:\n"
            menu += "<#FFFFFF>• <#00FF00>!giftbot <#FFFFFF>- Regalar bot paso a paso\n"
            menu += "<#FFFFFF>• <#00FF00>!cancel <#FFFFFF>- Cancelar proceso activo\n"
            menu += "<#FFFFFF>• <#00FF00>!broadcast <msg> <#FFFFFF>- Anuncio a todos los usuarios\n"
            menu += "<#FFFFFF>• <#00FF00>!anuncio <msg> <tiempo> <#FFFFFF>- Anuncio recurrente a bots\n"
            menu += "<#FFFFFF>• <#00FF00>!parar <#FFFFFF>- Detener anuncio recurrente\n"
            menu += "<#FFFFFF>• <#00FF00>!addgold <user_id> <cant>\n"
            menu += "<#FFFFFF>• <#00FF00>!mantenimiento <cat> <on/off>\n"
            menu += "<#FFFFFF>• <#00FF00>!detener <#FFFFFF>/ <#00FF00>!activar <cat>"

        await self.highrise.send_message(conversation_id, menu)

    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        if not hasattr(self, 'session_metadata') or user_id == self.session_metadata.user_id:
            return

        # Guardar la conversación activa de este usuario en memoria y en DB
        user_conversations[user_id] = conversation_id
        try:
            db.save_conversation_id(user_id, conversation_id)
        except Exception as e:
            print(f"⚠️ No se pudo guardar conversation_id: {e}")

        user_data = db.get_or_create_user(user_id)

        # Notificación de regalo pendiente
        if user_data["gift_from"]:
            await self.highrise.send_message(
                conversation_id,
                f"<#FFD700>🎁 ¡Tienes un aviso! <#FFFFFF>El usuario <#00FFFF>{user_data['gift_from']} "
                f"<#FFFFFF>te ha otorgado un beneficio/saldo.")
            db.clear_pending_gift(user_id)

        # Conversación nueva → mostrar menú de bienvenida
        if is_new_conversation:
            await self._send_menu(user_id, conversation_id)
            return

        # Obtener el texto del mensaje más reciente del usuario
        try:
            msgs_resp = await self.highrise.get_messages(conversation_id)
            if not msgs_resp or not msgs_resp.messages:
                return

            text = None
            bot_id = self.session_metadata.user_id
            for msg in msgs_resp.messages:
                if msg.sender_id != bot_id:
                    text = msg.content.strip()
                    break

            if not text:
                return
        except Exception as e:
            print(f"❌ Error al obtener mensajes: {e}")
            return

        parts = text.split()
        cmd = parts[0].lower()

        # -----------------------------------------------------
        # FLUJO PASO A PASO EXCLUSIVO DEL PROPIETARIO (!giftbot)
        # -----------------------------------------------------
        if user_id == HOSTER_OWNER_ID and user_id in gift_sessions:
            if cmd == "!cancel":
                del gift_sessions[user_id]
                await self.highrise.send_message(
                    conversation_id,
                    "<#E74C3C>🚫 Proceso de regalar bot cancelado.")
                return

            step = gift_sessions[user_id]["step"]

            if step == 1:
                gift_sessions[user_id]["target_user"] = text
                gift_sessions[user_id]["step"] = 2
                await self.highrise.send_message(
                    conversation_id,
                    "<#FFFFFF>2️⃣ Escribe la <#00FFFF>Categoría <#FFFFFF>del bot (ej: musica, fiesta):")
                return

            elif step == 2:
                gift_sessions[user_id]["category"] = text.lower()
                gift_sessions[user_id]["step"] = 3
                await self.highrise.send_message(
                    conversation_id,
                    "<#FFFFFF>3️⃣ Envía el <#00FFFF>Token <#FFFFFF>del bot:")
                return

            elif step == 3:
                gift_sessions[user_id]["token"] = text
                gift_sessions[user_id]["step"] = 4
                await self.highrise.send_message(
                    conversation_id,
                    "<#FFFFFF>4️⃣ Envía la <#00FFFF>ID de la Sala <#FFFFFF>(Room ID):")
                return

            elif step == 4:
                gift_sessions[user_id]["room_id"] = text
                gift_sessions[user_id]["step"] = 5
                await self.highrise.send_message(
                    conversation_id,
                    "<#FFFFFF>5️⃣ Escribe el <#FFD700>Tiempo libre <#FFFFFF>que quieras darles:\n"
                    "<#85E3FF>👉 Usa la cantidad seguida de 'm', 'h' o 'd'\n"
                    "<#AAAAAA>Ejemplos: 15m, 45m, 3h, 10d")
                return

            elif step == 5:
                duration = text.lower().strip()
                if not re.match(r"^(\d+)([mhd])$", duration):
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>⚠️ Formato de tiempo denegado.\n"
                        "<#FFFFFF>Ingresa la cantidad seguida de <#FFD700>m<#FFFFFF>, <#FFD700>h<#FFFFFF> o <#FFD700>d<#FFFFFF>.\n"
                        "<#AAAAAA>Ejemplos válidos: 15m, 40m, 5h, 12d.")
                    return

                data = gift_sessions[user_id]
                success, proc = deploy_bot_instance(
                    data["target_user"], data["category"], data["room_id"], data["token"])
                if success:
                    bot_id, exp_date = db.create_bot_entry(
                        data["target_user"], data["category"],
                        data["room_id"], data["token"], duration_str=duration)
                    if proc:
                        running_processes[bot_id] = proc
                    db.set_pending_gift(data["target_user"], "Propietario (Bot de Regalo)")
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#2ECC71>🎉 ¡Instancia regalada correctamente!\n\n"
                        f"<#FFFFFF>👤 Usuario: <#00FFFF>{data['target_user']}\n"
                        f"<#FFFFFF>🤖 Bot ID: <#00FFFF>{bot_id}\n"
                        f"<#FFFFFF>⏱️ Tiempo asignado: <#FFD700>{duration}\n"
                        f"<#FFFFFF>📅 Expiración: <#2ECC71>{exp_date} UTC")
                else:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>❌ Error crítico al desplegar la plantilla.\n"
                        "<#FFFFFF>Verifica que la categoría y el token sean válidos.")

                del gift_sessions[user_id]
                return

        # -----------------------------------------------------
        # FLUJO PASO A PASO DE COMPRA (!buy)
        # -----------------------------------------------------
        if user_id in buy_sessions:
            session = buy_sessions[user_id]
            step = session["step"]
            cat = session["category"]

            # Bloquear cualquier comando mientras hay una compra en curso
            if text.startswith("!"):
                await self.highrise.send_message(
                    conversation_id,
                    "<#E74C3C>⛔ Tienes una compra en proceso.\n"
                    "<#FFFFFF>Responde solo a las preguntas del asistente de compra.\n"
                    "<#AAAAAA>En el paso de confirmación puedes escribir <#FFFFFF>cancelar <#AAAAAA>para salir.")
                return

            # PASO 1 — Seleccionar duración
            if step == 1:
                opts = DURATION_OPTIONS[cat]
                if text not in [o[0] for o in opts]:
                    lines = "\n".join(
                        f"<#FFFFFF>[{o[0]}] <#85E3FF>{o[2]}   <#FFFFFF>│ <#FFD700>{o[3]:,} 🪙"
                        for o in opts)
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#E74C3C>⚠️ Opción inválida.\n"
                        f"<#FFFFFF>Escribe solo el número del plan:\n\n{lines}")
                    return

                chosen = next(o for o in opts if o[0] == text)
                session["duration"]  = chosen[1]
                session["dur_label"] = chosen[2]
                session["price"]     = chosen[3]
                session["step"]      = 2

                # Verificar saldo antes de pedir confirmación
                user_data_fresh = db.get_or_create_user(user_id)
                if user_data_fresh["balance"] < chosen[3]:
                    missing = chosen[3] - user_data_fresh["balance"]
                    del buy_sessions[user_id]
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#E74C3C>🛑 Transacción denegada: Saldo insuficiente.\n\n"
                        f"<#FFFFFF>Costo del plan: <#FFD700>{chosen[3]:,} 🪙\n"
                        f"<#FFFFFF>Tu saldo actual: <#FFD700>{user_data_fresh['balance']:,} 🪙\n"
                        f"<#FFFFFF>Te faltan: <#E74C3C>{missing:,} 🪙\n\n"
                        f"<#AAAAAA>Recarga tu saldo con tips en la sala y vuelve a intentarlo.")
                    return

                await self.highrise.send_message(
                    conversation_id,
                    f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n"
                    f"<#FFD700>🛒 CONFIRMAR COMPRA\n"
                    f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n"
                    f"<#FFFFFF>{CATEGORY_EMOJIS[cat]} Categoría: <#00FFFF>{CATEGORY_NAMES[cat]}\n"
                    f"<#FFFFFF>⏱️ Duración: <#00FFFF>{chosen[2]}\n"
                    f"<#FFFFFF>💰 Precio: <#FFD700>{chosen[3]:,} 🪙\n"
                    f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"<#2ECC71>aceptar <#FFFFFF>→ Confirmar compra\n"
                    f"<#E74C3C>cancelar <#FFFFFF>→ Salir")
                return

            # PASO 2 — Confirmación (ÚNICO paso donde acepta aceptar/cancelar)
            elif step == 2:
                if text.lower() == "aceptar":
                    session["step"] = 3
                    await self.highrise.send_message(
                        conversation_id,
                        "<#2ECC71>✅ ¡Compra confirmada!\n\n"
                        "<#FFFFFF>🔑 <#00FFFF>Paso 1/2 — Token del bot:\n"
                        "<#FFFFFF>Envía el <#FFD700>API Token <#FFFFFF>del bot que quieres alojar.")
                elif text.lower() in ["cancelar", "cancel"]:
                    del buy_sessions[user_id]
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>🚫 Compra cancelada.")
                else:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#FFFFFF>Escribe <#2ECC71>aceptar <#FFFFFF>para confirmar "
                        "o <#E74C3C>cancelar <#FFFFFF>para salir.")
                return

            # PASO 3 — Token del bot
            elif step == 3:
                token_val = text.strip()
                if not re.match(r'^[a-f0-9]{64}$', token_val):
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>❌ Token inválido.\n\n"
                        "<#FFFFFF>El token debe ser una cadena de <#FFD700>64 caracteres <#FFFFFF>hexadecimales.\n"
                        "<#AAAAAA>Asegúrate de copiarlo completo desde el portal de Highrise.\n\n"
                        "<#FFFFFF>🔑 Intenta de nuevo:")
                    return
                session["token"] = token_val
                session["step"]  = 4
                await self.highrise.send_message(
                    conversation_id,
                    "<#2ECC71>✅ Token válido.\n\n"
                    "<#FFFFFF>📍 <#00FFFF>Paso 2/2 — ID de la sala:\n"
                    "<#FFFFFF>Envía el <#FFD700>Room ID <#FFFFFF>de la sala donde quieres alojar el bot.\n"
                    "<#AAAAAA>(Lo encuentras en la URL de la sala en Highrise)")
                return

            # PASO 4 — Room ID y despliegue
            elif step == 4:
                room_id_val = text.strip()
                token_val   = session["token"]
                duration    = session["duration"]
                price       = session["price"]
                dur_label   = session["dur_label"]
                del buy_sessions[user_id]

                # Re-verificar saldo y disponibilidad antes de cobrar
                user_data_fresh = db.get_or_create_user(user_id)
                if user_data_fresh["balance"] < price:
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#E74C3C>🛑 Transacción denegada: Saldo insuficiente.\n"
                        f"<#FFFFFF>Tu saldo al procesar: <#FFD700>{user_data_fresh['balance']:,} 🪙")
                    return
                info = db.get_category_info(cat)
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#E74C3C>🛑 Categoría no disponible.\n"
                        f"<#FFFFFF>La categoría <#00FFFF>{CATEGORY_NAMES[cat]} "
                        f"<#FFFFFF>se encuentra en mantenimiento o fuera de servicio.")
                    return

                await self.highrise.send_message(
                    conversation_id,
                    "<#AAAAAA>⏳ Desplegando tu bot, espera un momento...")

                duration_param = None if duration == "perm" else duration
                success, proc = deploy_bot_instance(user_id, cat, room_id_val, token_val)
                if success:
                    db.update_gold(user_id, -price)
                    bot_id, exp_date = db.create_bot_entry(
                        user_id, cat, room_id_val, token_val, duration_str=duration_param)
                    if proc:
                        running_processes[bot_id] = proc
                    exp_msg = (f"<#FFFFFF>📅 Expira: <#FFD700>{exp_date} UTC"
                               if exp_date else "<#FFFFFF>♾️ Duración: <#2ECC71>Permanente 24/7")
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n"
                        f"<#2ECC71>✅ ¡BOT DESPLEGADO CON ÉXITO!\n"
                        f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n"
                        f"<#FFFFFF>🤖 ID Bot: <#00FFFF>{bot_id}\n"
                        f"<#FFFFFF>{CATEGORY_EMOJIS[cat]} Categoría: <#00FFFF>{CATEGORY_NAMES[cat]}\n"
                        f"<#FFFFFF>🏠 Sala: <#00FFFF>{room_id_val}\n"
                        f"<#FFFFFF>⏱️ Plan: <#00FFFF>{dur_label}\n"
                        f"{exp_msg}\n"
                        f"<#FFD700>━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"<#AAAAAA>⚠️ Recuerda otorgar permisos de "
                        f"<#FFFFFF>Moderador 🛡️ <#AAAAAA>y <#FFFFFF>Diseñador 🎨 "
                        f"<#AAAAAA>al bot en tu sala.")
                else:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>❌ Error crítico al desplegar la plantilla.\n"
                        "<#FFFFFF>Verifica que el TOKEN y la ID de la sala sean válidos.\n"
                        "<#AAAAAA>Si el problema persiste, contacta al soporte.")
                return

        # -----------------------------------------------------
        # COMANDOS NORMALES
        # -----------------------------------------------------
        if cmd == "!giftbot" and user_id == HOSTER_OWNER_ID:
            gift_sessions[user_id] = {"step": 1}
            await self.highrise.send_message(
                conversation_id,
                "<#FFD700>🎁 INICIANDO ASISTENTE PARA REGALAR BOT:\n\n"
                "<#FFFFFF>1️⃣ Envía la <#00FFFF>ID del usuario <#FFFFFF>que recibirá el regalo:\n"
                "<#AAAAAA>(Escribe '!cancel' en cualquier momento para salir)")

        elif cmd == "!menu":
            await self._send_menu(user_id, conversation_id)

        elif cmd in ["!saldo", "!balance"]:
            await self.highrise.send_message(
                conversation_id,
                f"<#FFFFFF>👤 Usuario ID: <#00FFFF>{user_id}\n"
                f"<#FFFFFF>💰 Saldo actual: <#FFD700>{user_data['balance']} 🪙")

        elif cmd == "!plan":
            if len(parts) == 1:
                await self.highrise.send_message(
                    conversation_id,
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

            elif parts[1] == "1":
                info = db.get_category_info("musica")
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>🛑 Categoría no disponible.\n"
                        "<#FFFFFF>La categoría <#00FFFF>MÚSICA <#FFFFFF>se encuentra temporalmente en mantenimiento.")
                    return
                await self.highrise.send_message(
                    conversation_id,
                    "<#00FFFF>🎵 BOT DE MÚSICA:\n"
                    "<#85E3FF>24 Horas    <#FFFFFF>│ <#FFD700>400 🪙\n"
                    "<#85E3FF>7 Días      <#FFFFFF>│ <#FFD700>900 🪙\n"
                    "<#85E3FF>15 Días     <#FFFFFF>│ <#FFD700>1,600 🪙\n"
                    "<#85E3FF>30 Días     <#FFFFFF>│ <#FFD700>3,200 🪙\n"
                    "<#2ECC71>Permanente  <#FFFFFF>│ <#FFD700>12,000 🪙\n\n"
                    "<#00FF00>!buy 1 <#FFFFFF>para iniciar el proceso guiado.")

            elif parts[1] == "2":
                await self.highrise.send_message(
                    conversation_id,
                    "<#FFA500>🎮 CATEGORÍA JUEGOS:\n"
                    "<#FFFFFF>Esta categoría es personalizada.\n"
                    "<#AAAAAA>Contacta a @_Kmi.77 para cotización y disponibilidad.")

            elif parts[1] == "3":
                info = db.get_category_info("fiesta")
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>🛑 Categoría no disponible.\n"
                        "<#FFFFFF>La categoría <#00FFFF>FIESTA <#FFFFFF>se encuentra temporalmente en mantenimiento.")
                    return
                await self.highrise.send_message(
                    conversation_id,
                    "<#FF69B4>🎉 BOT DE FIESTA:\n"
                    "<#FFB6C1>24 Horas    <#FFFFFF>│ <#FFD700>300 🪙\n"
                    "<#FFB6C1>7 Días      <#FFFFFF>│ <#FFD700>800 🪙\n"
                    "<#FFB6C1>15 Días     <#FFFFFF>│ <#FFD700>1,500 🪙\n"
                    "<#FFB6C1>30 Días     <#FFFFFF>│ <#FFD700>6,000 🪙\n"
                    "<#2ECC71>Permanente  <#FFFFFF>│ <#FFD700>10,000 🪙\n\n"
                    "<#00FF00>!buy 3 <#FFFFFF>para iniciar el proceso guiado.")

            elif parts[1] == "4":
                await self.highrise.send_message(
                    conversation_id,
                    "<#FFA500>⚙️ CATEGORÍA PERSONALIZADO:\n"
                    "<#FFFFFF>Esta categoría es completamente a medida.\n"
                    "<#AAAAAA>Contacta a @_Kmi.77 para cotización y disponibilidad.")
            else:
                await self.highrise.send_message(
                    conversation_id,
                    "<#E74C3C>❌ Sintaxis de comando incorrecta.\n"
                    "<#FFFFFF>Usa: <#00FF00>!plan 1<#FFFFFF>, <#00FF00>!plan 2<#FFFFFF>, "
                    "<#00FF00>!plan 3 <#FFFFFF>o <#00FF00>!plan 4")

        elif cmd == "!buy":
            if len(parts) < 2:
                await self.highrise.send_message(
                    conversation_id,
                    "<#FFD700>🛒 COMPRAR UN BOT:\n\n"
                    "<#FFFFFF>• <#00FF00>!buy 1 <#FFFFFF>— 🎵 Bot de Música\n"
                    "<#FFFFFF>• <#00FF00>!buy 3 <#FFFFFF>— 🎉 Bot de Fiesta")
                return

            cat_input = parts[1].lower()
            if cat_input not in CATEGORY_MAP:
                await self.highrise.send_message(
                    conversation_id,
                    "<#E74C3C>❌ Sintaxis de comando incorrecta.\n\n"
                    "<#FFFFFF>• <#00FF00>!buy 1 <#FFFFFF>— 🎵 Música\n"
                    "<#FFFFFF>• <#00FF00>!buy 3 <#FFFFFF>— 🎉 Fiesta")
                return

            cat = CATEGORY_MAP[cat_input]
            info = db.get_category_info(cat)
            if not info["active"] or info["maintenance"]:
                await self.highrise.send_message(
                    conversation_id,
                    f"<#E74C3C>🛑 Categoría no disponible.\n"
                    f"<#FFFFFF>La categoría <#00FFFF>{CATEGORY_NAMES[cat]} "
                    f"<#FFFFFF>se encuentra en mantenimiento o fuera de servicio.")
                return

            opts = DURATION_OPTIONS[cat]
            lines = "\n".join(
                f"<#FFFFFF>[{o[0]}] <#85E3FF>{o[2]}   <#FFFFFF>│ <#FFD700>{o[3]:,} 🪙"
                for o in opts)
            buy_sessions[user_id] = {"step": 1, "category": cat, "duration": None,
                                     "dur_label": None, "price": None, "token": None}
            await self.highrise.send_message(
                conversation_id,
                f"<#FFD700>{CATEGORY_EMOJIS[cat]} PLANES {CATEGORY_NAMES[cat]}:\n\n"
                f"{lines}\n\n"
                f"<#FFFFFF>💰 Tu saldo: <#FFD700>{user_data['balance']:,} 🪙\n\n"
                f"<#AAAAAA>✍️ Escribe el número del plan que deseas:")

        elif cmd == "!mybots":
            user_bots = db.get_user_bots(user_id)
            if not user_bots:
                await self.highrise.send_message(
                    conversation_id,
                    "<#AAAAAA>ℹ️ No tienes ningún bot alojado.")
            else:
                msg = "<#85E3FF>🤖 TUS BOTS ALOJADOS:\n"
                for b_id, r_id, st, cat, exp in user_bots:
                    exp_info = f"<#FFD700>Expira: {exp}" if exp else "<#2ECC71>Permanente"
                    msg += (f"<#FFFFFF>• ID <#00FFFF>{b_id} "
                            f"<#FFFFFF>| <#00FFFF>{cat} "
                            f"<#FFFFFF>| Sala: <#00FFFF>{r_id} "
                            f"<#FFFFFF>| <#2ECC71>{st} "
                            f"<#FFFFFF>| {exp_info}\n")
                await self.highrise.send_message(conversation_id, msg)

        elif cmd == "!gift":
            if len(parts) != 3 or not parts[2].isdigit():
                await self.highrise.send_message(
                    conversation_id,
                    "<#E74C3C>❌ Sintaxis de comando incorrecta.\n"
                    "<#FFFFFF>Uso adecuado: <#00FF00>!gift <user_id> <monto>")
                return
            target_id, amount = parts[1], int(parts[2])
            if amount <= 0:
                await self.highrise.send_message(
                    conversation_id,
                    "<#E74C3C>⚠️ El monto debe ser mayor a 0.")
            elif user_data["balance"] < amount:
                await self.highrise.send_message(
                    conversation_id,
                    f"<#E74C3C>🛑 Transacción denegada: Saldo insuficiente.\n"
                    f"<#FFFFFF>Tu saldo: <#FFD700>{user_data['balance']} 🪙")
            else:
                db.update_gold(user_id, -amount)
                db.update_gold(target_id, amount)
                db.set_pending_gift(target_id, f"@{user_id}")
                await self.highrise.send_message(
                    conversation_id,
                    f"<#2ECC71>💸 ¡Transferencia completada!\n"
                    f"<#FFFFFF>Has enviado <#FFD700>{amount} 🪙 "
                    f"<#FFFFFF>al usuario <#00FFFF>{target_id}<#FFFFFF>.")

        # --- Comandos exclusivos del propietario (silenciosos para otros) ---
        elif cmd in ["!tex", "!anuncio", "!parar", "!broadcast",
                     "!addgold", "!mantenimiento", "!detener", "!activar", "!giftbot", "!cancel"]:
            if user_id != HOSTER_OWNER_ID:
                return  # No revelar que estos comandos existen

            if cmd == "!broadcast":
                if len(parts) < 2:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>⚠️ Uso: <#00FF00>!broadcast <mensaje>")
                else:
                    broadcast_msg = " ".join(parts[1:])
                    recipients = db.get_all_users_with_conversations()
                    sent_count = 0
                    failed_count = 0
                    for uid, conv_id in recipients:
                        if uid == HOSTER_OWNER_ID:
                            continue
                        try:
                            await self.highrise.send_message(
                                conv_id,
                                f"<#FFD700>📢 ANUNCIO:\n<#FFFFFF>{broadcast_msg}")
                            sent_count += 1
                        except Exception:
                            failed_count += 1
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#2ECC71>✅ Broadcast enviado a <#FFD700>{sent_count} <#2ECC71>usuario(s)."
                        + (f"\n<#E74C3C>⚠️ {failed_count} fallaron." if failed_count else ""))

            elif cmd == "!tex":
                if len(parts) < 2:
                    await self.highrise.send_message(
                        conversation_id, "<#E74C3C>⚠️ Uso: <#00FF00>!tex <mensaje>")
                else:
                    message_tex = " ".join(parts[1:])
                    sent = self._write_tex_to_instances(message_tex)
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#2ECC71>📢 Mensaje enviado a <#FFD700>{sent} <#2ECC71>bot(s) alojado(s).")

            elif cmd == "!anuncio":
                if len(parts) < 3:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>⚠️ Uso: <#00FF00>!anuncio <mensaje> <tiempo>\n"
                        "<#AAAAAA>Ejemplos: !anuncio Hola! 5m · !anuncio Visita la sala 30s")
                else:
                    raw_time = parts[-1].lower()
                    match = re.match(r"^(\d+)([smh])$", raw_time)
                    if not match:
                        await self.highrise.send_message(
                            conversation_id,
                            "<#E74C3C>⚠️ Formato de tiempo inválido.\n"
                            "<#FFFFFF>Usa <#FFD700>s <#FFFFFF>(segundos), <#FFD700>m <#FFFFFF>(minutos) o <#FFD700>h <#FFFFFF>(horas).\n"
                            "<#AAAAAA>Ej: 30s, 5m, 1h")
                    else:
                        value, unit = int(match.group(1)), match.group(2)
                        interval = value * {"s": 1, "m": 60, "h": 3600}[unit]
                        message_ann = " ".join(parts[1:-1])
                        if "task" in active_announcement:
                            active_announcement["task"].cancel()
                        task = asyncio.create_task(self._announcement_loop(message_ann, interval))
                        active_announcement["message"] = message_ann
                        active_announcement["interval"] = interval
                        active_announcement["task"] = task
                        tiempo_fmt = f"{value}{'seg' if unit == 's' else 'min' if unit == 'm' else 'h'}"
                        await self.highrise.send_message(
                            conversation_id,
                            f"<#2ECC71>✅ Anuncio activado cada <#FFD700>{tiempo_fmt}<#2ECC71>:\n"
                            f"<#FFFFFF>📢 {message_ann}\n\n"
                            f"<#AAAAAA>Usa !parar para detenerlo.")

            elif cmd == "!parar":
                if "task" in active_announcement:
                    active_announcement["task"].cancel()
                    active_announcement.clear()
                    await self.highrise.send_message(
                        conversation_id, "<#E74C3C>🛑 Anuncio recurrente detenido.")
                else:
                    await self.highrise.send_message(
                        conversation_id, "<#AAAAAA>ℹ️ No hay ningún anuncio activo.")

            elif cmd == "!addgold":
                if len(parts) == 3 and parts[2].isdigit():
                    db.update_gold(parts[1], int(parts[2]))
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#2ECC71>✅ Saldo actualizado correctamente.\n"
                        f"<#FFFFFF>Se han añadido <#FFD700>{parts[2]} 🪙 "
                        f"<#FFFFFF>a la cuenta de <#00FFFF>{parts[1]}<#FFFFFF>.")
                else:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>❌ Sintaxis incorrecta.\n"
                        "<#FFFFFF>Uso: <#00FF00>!addgold <user_id> <cantidad>")

            elif cmd == "!mantenimiento":
                if len(parts) == 3 and parts[2] in ["on", "off"]:
                    db.set_maintenance(parts[1], 1 if parts[2] == "on" else 0)
                    estado = "<#E74C3C>ON (en mantenimiento)" if parts[2] == "on" else "<#2ECC71>OFF (activo)"
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#2ECC71>✅ Mantenimiento de <#00FFFF>{parts[1]} <#FFFFFF>→ {estado}")
                else:
                    await self.highrise.send_message(
                        conversation_id,
                        "<#E74C3C>❌ Sintaxis incorrecta.\n"
                        "<#FFFFFF>Uso: <#00FF00>!mantenimiento <cat> <on/off>")

            elif cmd in ["!detener", "!activar"]:
                if len(parts) == 2:
                    db.set_active_status(parts[1], 0 if cmd == "!detener" else 1)
                    estado = "<#E74C3C>DETENIDA" if cmd == "!detener" else "<#2ECC71>ACTIVA"
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#2ECC71>✅ Categoría <#00FFFF>{parts[1]} <#FFFFFF>→ {estado}")
                else:
                    await self.highrise.send_message(
                        conversation_id,
                        f"<#E74C3C>❌ Sintaxis incorrecta.\n"
                        f"<#FFFFFF>Uso: <#00FF00>{cmd} <categoria>")

        else:
            await self.highrise.send_message(
                conversation_id,
                "<#E74C3C>❓ Comando no reconocido.\n"
                "<#FFFFFF>Escribe <#00FF00>!menu <#FFFFFF>para ver las opciones disponibles.")
