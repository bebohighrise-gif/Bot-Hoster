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

# Procesos activos en esta sesión: {bot_id: subprocess.Popen}
running_processes = {}


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
        run_file_path = os.path.join(instance_path, "run.py")
        proc = subprocess.Popen(["python", run_file_path])
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
            except Exception as e:
                print(f"❌ Error en verificador de expiración: {e}")

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
        menu += "🔹 `!buy <CATEGORIA> <TOKEN> <ROOM_ID>` - Comprar bot\n"
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
            menu += "• `!addgold <USER_ID> <CANTIDAD>`\n"
            menu += "• `!mantenimiento <CAT> <on/off>`\n"
            menu += "• `!detener / !activar <CAT>`"

        await self.highrise.send_message(conversation_id, menu, type="text")

    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        if not hasattr(self, 'session_metadata') or user_id == self.session_metadata.user_id:
            return

        user_data = db.get_or_create_user(user_id)

        # Notificación de regalo pendiente
        if user_data["gift_from"]:
            await self.highrise.send_message(
                conversation_id,
                f"🎁 ¡Tienes un aviso! El usuario {user_data['gift_from']} te ha otorgado un beneficio/saldo.", type="text")
            db.clear_pending_gift(user_id)

        # Conversación nueva → mostrar menú de bienvenida y esperar siguiente mensaje
        if is_new_conversation:
            await self._send_menu(user_id, conversation_id)
            return

        # Obtener el texto del mensaje más reciente enviado por el usuario
        try:
            msgs_resp = await self.highrise.get_messages(conversation_id)
            if not msgs_resp or not msgs_resp.messages:
                return
            text = None
            for msg in msgs_resp.messages:
                if msg.user_id != self.session_metadata.user_id:
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
                await self.highrise.send_message(conversation_id, "🚫 Proceso de regalar bot cancelado.", type="text")
                return

            step = gift_sessions[user_id]["step"]

            if step == 1:
                gift_sessions[user_id]["target_user"] = text
                gift_sessions[user_id]["step"] = 2
                await self.highrise.send_message(conversation_id, "2️⃣ Escribe la **Categoría** del bot (ej: musica, fiesta):", type="text")
                return

            elif step == 2:
                gift_sessions[user_id]["category"] = text.lower()
                gift_sessions[user_id]["step"] = 3
                await self.highrise.send_message(conversation_id, "3️⃣ Envía el **Token** del bot:", type="text")
                return

            elif step == 3:
                gift_sessions[user_id]["token"] = text
                gift_sessions[user_id]["step"] = 4
                await self.highrise.send_message(conversation_id, "4️⃣ Envía la **ID de la Sala** (Room ID):", type="text")
                return

            elif step == 4:
                gift_sessions[user_id]["room_id"] = text
                gift_sessions[user_id]["step"] = 5
                await self.highrise.send_message(
                    conversation_id,
                    "5️⃣ Escribe el **Tiempo libre** que quieras darles:\n"
                    "👉 Usa la cantidad que quieras seguida de 'm', 'h' o 'd' (Ejemplos: `15m`, `45m`, `3h`, `10d`):", type="text")
                return

            elif step == 5:
                duration = text.lower().strip()
                if not re.match(r"^(\d+)([mhd])$", duration):
                    await self.highrise.send_message(
                        conversation_id,
                        "⚠️ Formato inválido. Ingresa la cantidad que quieras seguida de m, h o d.\n"
                        "Ejemplos válidos: `15m`, `40m`, `5h`, `12d`.\n"
                        "Inténtalo de nuevo:", type="text")
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
                        f"📅 Expiración: `{exp_date}` UTC", type="text")
                else:
                    await self.highrise.send_message(conversation_id, "❌ Error al desplegar la plantilla. Revisa la categoría.", type="text")

                del gift_sessions[user_id]
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
                "(Escribe `!cancel` en cualquier momento para salir)", type="text")

        elif cmd == "!menu":
            await self._send_menu(user_id, conversation_id)

        elif cmd in ["!saldo", "!balance"]:
            await self.highrise.send_message(
                conversation_id,
                f"👤 **Usuario ID:** `{user_id}`\n💰 **Saldo actual:** {user_data['balance']} 🪙.", type="text")

        elif cmd == "!plan":
            if len(parts) == 1:
                msg_plan = (
                    "🤖 **SELECCIONA EL TIPO DE BOT:**\n\n"
                    "[1] 🎵 MÚSICA\n"
                    "[2] 🎮 JUEGOS (Contactar @_Kmi.77)\n"
                    "[3] 🎉 FIESTA\n"
                    "[4] ⚙️ PERSONALIZADO (Contactar @_Kmi.77)\n\n"
                    "✍️ Responde '!plan 1' o '!plan 3' para ver precios."
                )
                await self.highrise.send_message(conversation_id, msg_plan, type="text")
            elif parts[1] == "1":
                info = db.get_category_info("musica")
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(conversation_id, "🛑 La categoría MÚSICA no está disponible temporalmente.", type="text")
                    return
                await self.highrise.send_message(
                    conversation_id,
                    "🎵 **CATEGORÍA MÚSICA:**\n• Plan Base: 500 🪙\n\nComprar: `!buy musica <TOKEN> <ROOM_ID>`", type="text")
            elif parts[1] == "3":
                info = db.get_category_info("fiesta")
                if not info["active"] or info["maintenance"]:
                    await self.highrise.send_message(conversation_id, "🛑 La categoría FIESTA no está disponible temporalmente.", type="text")
                    return
                await self.highrise.send_message(
                    conversation_id,
                    "🎉 **CATEGORÍA FIESTA:**\n• Plan Base: 300 🪙\n\nComprar: `!buy fiesta <TOKEN> <ROOM_ID>`", type="text")

        elif cmd == "!buy":
            if len(parts) < 4:
                await self.highrise.send_message(conversation_id, "⚠️ Uso correcto: `!buy <CATEGORIA> <TOKEN> <ROOM_ID>`", type="text")
                return

            cat, token, room_id = parts[1].lower(), parts[2], parts[3]
            price = 500

            if user_data["balance"] < price:
                missing = price - user_data["balance"]
                await self.highrise.send_message(conversation_id, f"🛑 Saldo insuficiente. Te faltan {missing} 🪙.", type="text")
                return

            info = db.get_category_info(cat)
            if not info["active"] or info["maintenance"]:
                await self.highrise.send_message(conversation_id, f"🛑 La categoría '{cat}' no está disponible.", type="text")
                return

            success, proc = deploy_bot_instance(user_id, cat, room_id, token)
            if success:
                db.update_gold(user_id, -price)
                bot_id, _ = db.create_bot_entry(user_id, cat, room_id, token)
                if proc:
                    running_processes[bot_id] = proc
                await self.highrise.send_message(
                    conversation_id,
                    f"✅ ¡Bot comprado y desplegado con éxito!\n🤖 ID: `{bot_id}`.\n\n"
                    f"⚠️ Asigna permisos de MODERADOR 🛡️ y DISEÑADOR 🎨 al bot en la sala `{room_id}`.", type="text")

        elif cmd == "!mybots":
            user_bots = db.get_user_bots(user_id)
            if not user_bots:
                await self.highrise.send_message(conversation_id, "ℹ️ No tienes ningún bot alojado.", type="text")
            else:
                msg = "🤖 **Tus Bots Alojados:**\n"
                for b_id, r_id, st, cat, exp in user_bots:
                    exp_info = f" | Expira: `{exp}`" if exp else " | Permanente"
                    msg += f"• ID `{b_id}` | Tipo: `{cat}` | Sala: `{r_id}` | Estado: `{st}`{exp_info}\n"
                await self.highrise.send_message(conversation_id, msg, type="text")

        elif cmd == "!gift":
            if len(parts) == 3 and parts[2].isdigit():
                target_id, amount = parts[1], int(parts[2])
                if user_data["balance"] < amount:
                    await self.highrise.send_message(conversation_id, "🛑 Saldo insuficiente.", type="text")
                else:
                    db.update_gold(user_id, -amount)
                    db.update_gold(target_id, amount)
                    db.set_pending_gift(target_id, f"@{user_id}")
                    await self.highrise.send_message(conversation_id, f"✅ Has regalado {amount} 🪙 a `{target_id}`.", type="text")

        elif cmd == "!addgold" and user_id == HOSTER_OWNER_ID:
            if len(parts) == 3 and parts[2].isdigit():
                db.update_gold(parts[1], int(parts[2]))
                await self.highrise.send_message(conversation_id, f"✅ Añadidos {parts[2]} 🪙 a `{parts[1]}`.", type="text")

        elif cmd == "!mantenimiento" and user_id == HOSTER_OWNER_ID:
            if len(parts) == 3 and parts[2] in ["on", "off"]:
                db.set_maintenance(parts[1], 1 if parts[2] == "on" else 0)
                await self.highrise.send_message(conversation_id, f"✅ Mantenimiento de '{parts[1]}' a {parts[2]}.", type="text")

        elif cmd in ["!detener", "!activar"] and user_id == HOSTER_OWNER_ID:
            if len(parts) == 2:
                db.set_active_status(parts[1], 0 if cmd == "!detener" else 1)
                await self.highrise.send_message(conversation_id, f"✅ Estado de '{parts[1]}' actualizado.", type="text")

        else:
            await self.highrise.send_message(
                conversation_id,
                "❓ Comando no reconocido. Escribe `!menu` para ver las opciones disponibles.", type="text")
                
