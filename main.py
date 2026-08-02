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
        ("1", "1d",   "24 Horas",   400),
        ("2", "7d",   "7 Días",     900),
        ("3", "15d",  "15 Días",   1600),
        ("4", "30d",  "30 Días",   3200),
        ("5", "perm", "Permanente",12000),
    ],
    "fiesta": [
        ("1", "1d",   "24 Horas",   300),
        ("2", "7d",   "7 Días",     800),
        ("3", "15d",  "15 Días",   1500),
        ("4", "30d",  "30 Días",   6000),
        ("5", "perm", "Permanente",10000),
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
        return False

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
        # Correr desde la carpeta de la instancia para que console_message.txt
        # sea único por bot y no compartido entre todos.
        proc = subprocess.Popen(["python", "run.py"], cwd=instance_path)
        print(f"🟢 Bot de {bot_type} desplegado con éxito para el usuario {user_id} (PID {proc.pid})")
        return True, proc
    except Exception as e:
        print(f"🔴 Error al ejecutar run.py del bot: {e}")
        return False, None


class BotHoster(BaseBot):

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        self.session_metadata = session_metadata
        print("🤖 Bot Hoster de Nex-Host iniciado y conectado a la sala.")
        # Auto-mantenimiento para categorías sin plantilla
        for cat in ["musica", "fiesta", "juegos", "personalizado"]:
            if not template_exists(cat):
                db.set_maintenance(cat, 1)
                print(f"⚠️  Categoría '{cat}' en mantenimiento (sin plantilla).")
        # Verificador de bots expirados en segundo plano
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
                    # Notificar al usuario si tiene una conversación activa
                    conv_id = user_conversations.get(owner_id)
                    if conv_id:
                        try:
                            await self.highrise.send_message(
                                conv_id,
                                f"⏰ Tu bot de categoría `{category}` (ID `{bot_id}`) ha expirado y fue detenido."
                            )
                        except Exception:
                            pass  # La conversación puede haber cerrado; no es crítico
            except Exception as e:
                print(f"❌ Error en verificador de expiración: {e}")

    def _write_tex_to_instances(self, message: str) -> int:
        """Escribe console_message.txt en cada instancia activa. Devuelve cuántas recibieron el mensaje."""
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
                f"💰 ¡Gracias por tu depósito! Recibidos {tip.amount} 🪙.\n"
                f"Tu saldo acumulado es de: {user_data['balance']} 🪙.\n"
                f"Revisa tu Inbox para ver el menú o escribe '!plan'."
            )

    async def on_whisper(self, user: User, message: str) -> None:
        if user.id == HOSTER_OWNER_ID and message.strip().lower() == "!copy":
            try:
                outfit_resp = await self.highrise.get_user_outfit(user.id)
                if outfit_resp and hasattr(outfit_resp, 'outfit'):
                    await self.highrise.set_outfit(outfit_resp.outfit)
                    await self.highrise.send_whisper(user.id, "👕 ¡Outfit copiado con éxito!")
            except Exception as e:
                await self.highrise.send_whisper(user.id, f"❌ Error al copiar outfit: {e}")

    async def _send_menu(self, user_id: str, conversation_id: str) -> None:
        """Envía el menú principal al usuario."""
        user_data = db.get_or_create_user(user_id)
        user_bots = db.get_user_bots(user_id)

        menu = "👋 ¡Hola! Bienvenido al Servicio de Hosting Bot (Nex-Host).\n\n"
        menu += f"💰 **Tu Saldo:** {user_data['balance']} 🪙\n\n"
        menu += "📋 **Menú de Comandos:**\n"
        menu += "🔹 `!menu` - Mostrar este menú\n"
        menu += "🔹 `!saldo` - Consultar balance\n"
        menu += "🔹 `!plan` - Ver categorías y precios\n"
        menu += "🔹 `!buy 1` (Música) · `!buy 3` (Fiesta) - Comprar bot\n"
        menu += "🔹 `!gift <ID_USUARIO> <MONTO>` - Regalar saldo\n"

        if len(user_bots) == 1:
            b_id, r_id, st, cat, exp = user_bots[0]
            exp_info = f" (Expira: {exp})" if exp else " (Permanente)"
            menu += f"\n🤖 **Tu Bot:** ID `{b_id}` | Tipo: `{cat}` | Sala: `{r_id}` | Estado: `{st}`{exp_info}\n"
        elif len(user_bots) > 1:
            menu += f"\n🤖 Tienes {len(user_bots)} bots registrados. Usa `!mybots` para ver la lista.\n"

        if user_id == HOSTER_OWNER_ID:
            menu += "\n👑 **Panel Admin:**\n"
            menu += "• `!giftbot` - Regalar bot paso a paso (ej: 15m, 3h, 30d)\n"
            menu += "• `!cancel` - Cancelar el proceso paso a paso\n"
            menu += "• `!broadcast <MSG>` - Anuncio a todos los usuarios\n"
            menu += "• `!anuncio <MSG> <TIEMPO>` - Anuncio recurrente a bots (ej: 5m)\n"
            menu += "• `!parar` - Detener anuncio recurrente\n"
            menu += "• `!addgold <USER_ID> <CANTIDAD>`\n"
            menu += "• `!mantenimiento <CAT> <on/off>`\n"
            menu += "• `!detener / !activar <CAT>`"

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
                f"🎁 ¡Tienes un aviso! El usuario {user_data['gift_from']} te ha otorgado un beneficio/saldo.")
            db.clear_pending_gift(user_id)

        # Conversación nueva → mostrar menú de bienvenida y esperar siguiente mensaje
        if is_new_conversation:
            await self._send_menu(user_id, conversation_id)
            return

        # Obtener el texto del mensaje más reciente enviado por el usuario.
        # SDK 25.x: get_messages devuelve GetMessagesResponse con .messages (list[Message]).
        # Message tiene .sender_id y .content.
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
                await self.highrise.send_message(conversation_id, "🚫 Proceso de regalar bot cancelado.")
                return

            step = gift_sessions[user_id]["step"]

            if step == 1:
                gift_sessions[user_id]["target_user"] = text
                gift_sessions[user_id]["step"] = 2
                await self.highrise.send_message(conversation_id, "2️⃣ Escribe la **Categoría** del bot (ej: musica, fiesta):")
                return

            elif step == 2:
                gift_sessions[user_id]["category"] = text.lower()
                gift_sessions[user_id]["step"] = 3
                await self.highrise.send_message(conversation_id, "3️⃣ Envía el **Token** del bot:")
                return

            elif step == 3:
                gift_sessions[user_id]["token"] = text
                gift_sessions[user_id]["step"] = 4
                await self.highrise.send_message(conversation_id, "4️⃣ Envía la **ID de la Sala** (Room ID):")
                return

            elif step == 4:
                gift_sessions[user_id]["room_id"] = text
                gift_sessions[user_id]["step"] = 5
                await self.highrise.send_message(
                    conversation_id,
                    "5️⃣ Escribe el **Tiempo libre** que quieras darles:\n"
                    "👉 Usa la cantidad que quieras seguida de 'm', 'h' o 'd' (Ejemplos: `15m`, `45m`, `3h`, `10d`):")
                return

            elif step == 5:
                duration = text.lower().strip()
                if not re.match(r"^(\d+)([mhd])$", duration):
                    await self.highrise.send_message(
                        conversation_id,
                        "⚠️ Formato inválido. Ingresa la cantidad que quieras seguida de m, h o d.\n"
                        "Ejemplos válidos: `15m`, `40m`, `5h`, `12d`.\n"
                        "Inténtalo de nuevo:")
                    return

                data = gift_sessions[user_id]

                success, proc = deploy_bot_instance(data["target_user"], data["category"], data["room_id"], data["token"])
                if success:
                    bot_id, exp_date = db.create_bot_entry(
                        data["target_user"],
                        data["category"],
                        data["room_id"],
                        data["token"],
                        duration_str=duration
                    )
                    if proc:
                        running_processes[bot_id] = proc
                    db.set_pending_gift(data["target_user"], "Propietario (Bot de Regalo)")

                    await self.highrise.send_message(
                        conversation_id,
                        f"🎉 ¡Instancia regalada con éxito!\n\n"
                        f"👤 Usuario: `{data['target_user']}`\n"
                        f"🤖 Bot ID: `{bot_id}`\n"
                        f"⏱️ Tiempo asignado: `{duration}`\n"
                        f"📅 Expiración: `{exp_date}` UTC")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Error al desplegar la plantilla. Revisa la categoría.")

                del gift_sessions[user_id]
                return

        # -----------------------------------------------------
        # FLUJO PASO A PASO DE COMPRA (!buy)
        # -----------------------------------------------------
        if user_id in buy_sessions:
            session = buy_sessions[user_id]
            step = session["step"]
            cat = session["category"]

            # PASO 1 — Seleccionar duración
            if step == 1:
                opts = DURATION_OPTIONS[cat]
                if text not in [o[0] for o in opts]:
                    lines = "\n".join(f"[{o[0]}] {o[2]}: {o[3]:,} 🪙" for o in opts)
                    await self.highrise.send_message(
                        conversation_id,
                        f"⚠️ Opción inválida. Escribe solo el número del plan:\n\n{lines}")
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
                        f"🛑 **Saldo insuficiente.**\n\n"
                        f"• Plan seleccionado: {chosen[2]} — {chosen[3]:,} 🪙\n"
                        f"• Tu saldo: {user_data_fresh['balance']:,} 🪙\n"
                        f"• Te faltan: {missing:,} 🪙\n\n"
                        f"Recarga tu saldo con tips/donaciones en la sala y vuelve a intentarlo.")
                    return
                await self.highrise.send_message(
                    conversation_id,
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🛒 **CONFIRMAR COMPRA**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"{CATEGORY_EMOJIS[cat]} Categoría: **{CATEGORY_NAMES[cat]}**\n"
                    f"⏱️ Duración: **{chosen[2]}**\n"
                    f"💰 Precio: **{chosen[3]:,} 🪙**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Escribe **aceptar** para confirmar o **cancelar** para salir.")
                return

            # PASO 2 — Confirmación
            elif step == 2:
                if text.lower() == "aceptar":
                    session["step"] = 3
                    await self.highrise.send_message(
                        conversation_id,
                        "✅ ¡Compra confirmada!\n\n"
                        "🔑 **Paso 1/2 — Token del bot:**\n"
                        "Envía el **API Token** del bot que quieres alojar.")
                elif text.lower() in ["cancelar", "cancel"]:
                    del buy_sessions[user_id]
                    await self.highrise.send_message(
                        conversation_id, "🚫 Compra cancelada.")
                else:
                    await self.highrise.send_message(
                        conversation_id,
                        "⚠️ Responde **aceptar** para confirmar la compra o **cancelar** para salir.")
                return

            # PASO 3 — Token del bot
            elif step == 3:
                token_val = text.strip()
                # Validación de formato: token de Highrise = 64 caracteres hex
                if not re.match(r'^[a-f0-9]{64}$', token_val):
                    await self.highrise.send_message(
                        conversation_id,
                        "❌ **Token inválido.**\n\n"
                        "El token debe ser una cadena de **64 caracteres** en formato hexadecimal.\n"
                        "Asegúrate de copiarlo completo desde el portal de Highrise.\n\n"
                        "🔑 Intenta de nuevo o escribe **cancelar** para salir:")
                    return
                session["token"] = token_val
                session["step"]  = 4
                await self.highrise.send_message(
                    conversation_id,
                    "✅ Token válido.\n\n"
                    "📍 **Paso 2/2 — ID de la sala:**\n"
                    "Envía el **Room ID** de la sala donde quieres que el bot esté activo.\n\n"
                    "_(Lo encuentras en la URL de la sala en Highrise)_")
                return

            # PASO 4 — Room ID y despliegue
            elif step == 4:
                room_id_val = text.strip()
                cat        = session["category"]
                token_val  = session["token"]
                duration   = session["duration"]
                price      = session["price"]
                dur_label  = session["dur_label"]
                del buy_sessions[user_id]

                # Re-verificar saldo y disponibilidad antes de cobrar
                user_data_fresh = db.get_or_create_user(user_id)
                if user_data_fresh["balance"] < price:
                    await self.highrise.send_message(
                        conversation_id,
                        f"🛑 Saldo insuficiente al momento de procesar. Tu saldo es {user_data_fresh['balance']:,} 🪙.")
                    return
                info = db.get_category_info(cat)
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(
                        conversation_id,
                        f"🛑 La categoría **{CATEGORY_NAMES[cat]}** no está disponible en este momento.")
                    return

                await self.highrise.send_message(
                    conversation_id, "⏳ Desplegando tu bot, espera un momento...")

                duration_param = None if duration == "perm" else duration
                success, proc = deploy_bot_instance(user_id, cat, room_id_val, token_val)
                if success:
                    db.update_gold(user_id, -price)
                    bot_id, exp_date = db.create_bot_entry(
                        user_id, cat, room_id_val, token_val, duration_str=duration_param)
                    if proc:
                        running_processes[bot_id] = proc
                    exp_msg = f"📅 Expira: `{exp_date}` UTC" if exp_date else "♾️ Duración: **Permanente 24/7**"
                    await self.highrise.send_message(
                        conversation_id,
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ **¡BOT DESPLEGADO CON ÉXITO!**\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"{CATEGORY_EMOJIS[cat]} Categoría: **{CATEGORY_NAMES[cat]}**\n"
                        f"🤖 Bot ID: `{bot_id}`\n"
                        f"🏠 Sala: `{room_id_val}`\n"
                        f"⏱️ Plan: **{dur_label}**\n"
                        f"{exp_msg}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"⚠️ **Acción requerida:**\n"
                        f"Asigna permisos de **MODERADOR** 🛡️ y **DISEÑADOR** 🎨 al bot en la sala `{room_id_val}` para que funcione correctamente.")
                else:
                    await self.highrise.send_message(
                        conversation_id,
                        "❌ Hubo un error al desplegar el bot. Verifica que la categoría tenga plantilla activa y vuelve a intentarlo.\n"
                        "Si el problema persiste, contacta al soporte.")
                return

        # -----------------------------------------------------
        # COMANDOS NORMALES
        # -----------------------------------------------------
        if cmd == "!giftbot" and user_id == HOSTER_OWNER_ID:
            gift_sessions[user_id] = {"step": 1}
            await self.highrise.send_message(
                conversation_id,
                "🎁 **Iniciando Asistente para Regalar Bot:**\n\n"
                "1️⃣ Envía la **ID del usuario** que recibirá el regalo:\n"
                "(Escribe `!cancel` en cualquier momento para salir)")

        elif cmd == "!menu":
            await self._send_menu(user_id, conversation_id)

        elif cmd in ["!saldo", "!balance"]:
            await self.highrise.send_message(
                conversation_id,
                f"👤 **Usuario ID:** `{user_id}`\n💰 **Saldo actual:** {user_data['balance']} 🪙.")

        elif cmd == "!plan":
            if len(parts) == 1:
                msg_plan = (
                    "🤖 **SELECCIONA EL TIPO DE BOT:**\n\n"
                    "[1] 🎵 MÚSICA\n"
                    "[2] 🎮 JUEGOS (Contactar @_Kmi.77)\n"
                    "[3] 🎉 FIESTA\n"
                    "[4] ⚙️ PERSONALIZADO (Contactar @_Kmi.77)\n\n"
                    "✍️ Responde `!plan 1`, `!plan 2`, `!plan 3` o `!plan 4` para más info."
                )
                await self.highrise.send_message(conversation_id, msg_plan)
            elif parts[1] == "1":
                info = db.get_category_info("musica")
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(conversation_id, "🛑 La categoría MÚSICA no está disponible temporalmente.")
                    return
                await self.highrise.send_message(
                    conversation_id,
                    "🎵 **PLANES BOT DE MÚSICA:**\n"
                    "• `1d` (24 Horas): 400 🪙\n"
                    "• `7d` (7 Días): 900 🪙\n"
                    "• `15d` (15 Días): 1,600 🪙\n"
                    "• `30d` (30 Días): 3,200 🪙\n"
                    "• `perm` (Permanente): 12,000 🪙\n\n"
                    "Comprar: `!buy 1` para iniciar el proceso guiado.")
            elif parts[1] == "2":
                await self.highrise.send_message(
                    conversation_id,
                    "🎮 **CATEGORÍA JUEGOS:**\nEsta categoría es personalizada.\nContacta a @_Kmi.77 para cotización y disponibilidad.")
            elif parts[1] == "3":
                info = db.get_category_info("fiesta")
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(conversation_id, "🛑 La categoría FIESTA no está disponible temporalmente.")
                    return
                await self.highrise.send_message(
                    conversation_id,
                    "🎉 **PLANES BOT DE FIESTA:**\n"
                    "• `1d` (24 Horas): 300 🪙\n"
                    "• `7d` (7 Días): 800 🪙\n"
                    "• `15d` (15 Días): 1,500 🪙\n"
                    "• `30d` (30 Días): 6,000 🪙\n"
                    "• `perm` (Permanente): 10,000 🪙\n\n"
                    "Comprar: `!buy 3` para iniciar el proceso guiado.")
            elif parts[1] == "4":
                await self.highrise.send_message(
                    conversation_id,
                    "⚙️ **CATEGORÍA PERSONALIZADO:**\nEsta categoría es completamente a medida.\nContacta a @_Kmi.77 para cotización y disponibilidad.")
            else:
                await self.highrise.send_message(conversation_id, "⚠️ Opción inválida. Usa `!plan 1`, `!plan 2`, `!plan 3` o `!plan 4`.")

        elif cmd == "!buy":
            # Inicio del flujo de compra paso a paso
            if len(parts) < 2:
                await self.highrise.send_message(
                    conversation_id,
                    "🛒 **Comprar un bot:**\n\n"
                    "• `!buy 1` — 🎵 Bot de Música\n"
                    "• `!buy 3` — 🎉 Bot de Fiesta\n\n"
                    "Escribe el comando con el número de categoría para iniciar.")
                return

            cat_input = parts[1].lower()
            if cat_input not in CATEGORY_MAP:
                await self.highrise.send_message(
                    conversation_id,
                    "⚠️ Categoría no válida.\n\n"
                    "• `!buy 1` — 🎵 Música\n"
                    "• `!buy 3` — 🎉 Fiesta")
                return

            cat = CATEGORY_MAP[cat_input]
            info = db.get_category_info(cat)
            if not info["active"] or info["maintenance"]:
                await self.highrise.send_message(
                    conversation_id,
                    f"🛑 La categoría **{CATEGORY_NAMES[cat]}** no está disponible temporalmente.")
                return

            # Mostrar opciones de duración y arrancar el flujo
            opts = DURATION_OPTIONS[cat]
            lines = "\n".join(f"[{o[0]}] {o[2]}: **{o[3]:,} 🪙**" for o in opts)
            buy_sessions[user_id] = {"step": 1, "category": cat, "duration": None,
                                     "dur_label": None, "price": None, "token": None}
            await self.highrise.send_message(
                conversation_id,
                f"{CATEGORY_EMOJIS[cat]} **PLANES {CATEGORY_NAMES[cat]}:**\n\n"
                f"{lines}\n\n"
                f"💰 Tu saldo: **{user_data['balance']:,} 🪙**\n\n"
                f"✍️ Escribe el **número del plan** que deseas o **cancelar** para salir:")

        elif cmd == "!mybots":
            user_bots = db.get_user_bots(user_id)
            if not user_bots:
                await self.highrise.send_message(conversation_id, "ℹ️ No tienes ningún bot alojado.")
            else:
                msg = "🤖 **Tus Bots Alojados:**\n"
                for b_id, r_id, st, cat, exp in user_bots:
                    exp_info = f" | Expira: `{exp}`" if exp else " | Permanente"
                    msg += f"• ID `{b_id}` | Tipo: `{cat}` | Sala: `{r_id}` | Estado: `{st}`{exp_info}\n"
                await self.highrise.send_message(conversation_id, msg)

        elif cmd == "!gift":
            if len(parts) != 3 or not parts[2].isdigit():
                await self.highrise.send_message(conversation_id, "⚠️ Uso correcto: `!gift <ID_USUARIO> <MONTO>`")
                return
            target_id, amount = parts[1], int(parts[2])
            if amount <= 0:
                await self.highrise.send_message(conversation_id, "⚠️ El monto debe ser mayor a 0.")
            elif user_data["balance"] < amount:
                await self.highrise.send_message(conversation_id, "🛑 Saldo insuficiente.")
            else:
                db.update_gold(user_id, -amount)
                db.update_gold(target_id, amount)
                db.set_pending_gift(target_id, f"@{user_id}")
                await self.highrise.send_message(conversation_id, f"✅ Has regalado {amount} 🪙 a `{target_id}`.")

        # --- Comandos exclusivos del propietario (silenciosos para otros usuarios) ---
        elif cmd in ["!tex", "!anuncio", "!parar", "!broadcast", "!addgold", "!mantenimiento", "!detener", "!activar", "!giftbot", "!cancel"]:
            if user_id != HOSTER_OWNER_ID:
                return  # No revelar que estos comandos existen
            if cmd == "!broadcast":
                # Envía un mensaje de inbox a TODOS los usuarios registrados
                if len(parts) < 2:
                    await self.highrise.send_message(
                        conversation_id,
                        "⚠️ Uso: `!broadcast <mensaje>`\nEnvía el mensaje a todos los usuarios que hayan escrito al bot.")
                else:
                    broadcast_msg = " ".join(parts[1:])
                    recipients = db.get_all_users_with_conversations()
                    sent_count = 0
                    failed_count = 0
                    for uid, conv_id in recipients:
                        if uid == HOSTER_OWNER_ID:
                            continue  # No enviarse a sí mismo
                        try:
                            await self.highrise.send_message(conv_id, f"📢 **Anuncio:**\n{broadcast_msg}")
                            sent_count += 1
                        except Exception:
                            failed_count += 1
                    await self.highrise.send_message(
                        conversation_id,
                        f"✅ Broadcast enviado a {sent_count} usuario(s)."
                        + (f"\n⚠️ {failed_count} fallaron." if failed_count else ""))

            elif cmd == "!tex":
                if len(parts) < 2:
                    await self.highrise.send_message(conversation_id, "⚠️ Uso: `!tex <mensaje>`")
                else:
                    message_tex = " ".join(parts[1:])
                    sent = self._write_tex_to_instances(message_tex)
                    await self.highrise.send_message(
                        conversation_id,
                        f"📢 Mensaje enviado a {sent} bot(s) alojado(s).")

            elif cmd == "!anuncio":
                # Uso: !anuncio <mensaje> <tiempo>  → ej: !anuncio Hola 5m / 30s / 2h
                if len(parts) < 3:
                    await self.highrise.send_message(
                        conversation_id,
                        "⚠️ Uso: `!anuncio <mensaje> <tiempo>`\nEjemplos: `!anuncio Hola! 5m` · `!anuncio Visita la sala 30s` · `!anuncio Info 1h`")
                else:
                    raw_time = parts[-1].lower()
                    match = re.match(r"^(\d+)([smh])$", raw_time)
                    if not match:
                        await self.highrise.send_message(
                            conversation_id,
                            "⚠️ Formato de tiempo inválido. Usa `s` (segundos), `m` (minutos) o `h` (horas).\nEj: `30s`, `5m`, `1h`")
                    else:
                        value, unit = int(match.group(1)), match.group(2)
                        interval = value * {"s": 1, "m": 60, "h": 3600}[unit]
                        message_ann = " ".join(parts[1:-1])

                        # Cancelar anuncio anterior si existía
                        if "task" in active_announcement:
                            active_announcement["task"].cancel()

                        task = asyncio.create_task(self._announcement_loop(message_ann, interval))
                        active_announcement["message"] = message_ann
                        active_announcement["interval"] = interval
                        active_announcement["task"] = task

                        tiempo_fmt = f"{value}{'seg' if unit == 's' else 'min' if unit == 'm' else 'h'}"
                        await self.highrise.send_message(
                            conversation_id,
                            f"✅ Anuncio activado cada **{tiempo_fmt}**:\n📢 `{message_ann}`\n\nUsa `!parar` para detenerlo.")

            elif cmd == "!parar":
                if "task" in active_announcement:
                    active_announcement["task"].cancel()
                    active_announcement.clear()
                    await self.highrise.send_message(conversation_id, "🛑 Anuncio recurrente detenido.")
                else:
                    await self.highrise.send_message(conversation_id, "ℹ️ No hay ningún anuncio activo.")

            elif cmd == "!addgold":
                if len(parts) == 3 and parts[2].isdigit():
                    db.update_gold(parts[1], int(parts[2]))
                    await self.highrise.send_message(conversation_id, f"✅ Añadidos {parts[2]} 🪙 a `{parts[1]}`.")
                else:
                    await self.highrise.send_message(conversation_id, "⚠️ Uso: `!addgold <USER_ID> <CANTIDAD>`")
            elif cmd == "!mantenimiento":
                if len(parts) == 3 and parts[2] in ["on", "off"]:
                    db.set_maintenance(parts[1], 1 if parts[2] == "on" else 0)
                    await self.highrise.send_message(conversation_id, f"✅ Mantenimiento de '{parts[1]}' a {parts[2]}.")
                else:
                    await self.highrise.send_message(conversation_id, "⚠️ Uso: `!mantenimiento <CAT> <on/off>`")
            elif cmd in ["!detener", "!activar"]:
                if len(parts) == 2:
                    db.set_active_status(parts[1], 0 if cmd == "!detener" else 1)
                    await self.highrise.send_message(conversation_id, f"✅ Estado de '{parts[1]}' actualizado.")
                else:
                    await self.highrise.send_message(conversation_id, f"⚠️ Uso: `{cmd} <CATEGORIA>`")

        else:
            await self.highrise.send_message(
                conversation_id,
                "❓ Comando no reconocido. Escribe `!menu` para ver las opciones disponibles.")
                
