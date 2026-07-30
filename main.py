import os
import shutil
import subprocess
import asyncio
from highrise import BaseBot, User, Position, AnchorPosition
from highrise.models import SessionMetadata, CurrencyItem

from config import HOSTER_OWNER_ID, TEMPLATES_DIR, HOSTED_INSTANCES_DIR
import database as db

db.init_db()

def deploy_bot_instance(user_id: str, bot_type: str, room_id: str, api_token: str) -> bool:
    """ Clona la carpeta plantilla del bot e inyecta las credenciales en config.py """
    template_path = os.path.join(TEMPLATES_DIR, bot_type.lower())
    instance_path = os.path.join(HOSTED_INSTANCES_DIR, f"user_{user_id}_{bot_type.lower()}")

    if not os.path.exists(template_path):
        return False

    if os.path.exists(instance_path):
        shutil.rmtree(instance_path)

    shutil.copytree(template_path, instance_path)

    config_file_path = os.path.join(instance_path, "config.py")
    config_content = f"""# CONFIGURACIÓN GENERADA AUTOMÁTICAMENTE
ROOM_ID = "{room_id}"
API_TOKEN = "{api_token}"
BOT_OWNER_ID = "{user_id}"
HOSTER_OWNER_ID = "{HOSTER_OWNER_ID}"
"""
    with open(config_file_path, "w", encoding="utf-8") as f:
        f.write(config_content)

    try:
        subprocess.Popen(["highrise", f"{instance_path}/main:Bot", room_id, api_token])
        return True
    except Exception as e:
        print(f"Error al ejecutar bot: {e}")
        return False


class BotHoster(BaseBot):

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        print("🤖 Bot Hoster de Nex-Host iniciado y conectado a la sala.")

    # Recarga de saldo por Tips en la sala
    async def on_tip_reaction(self, sender: User, receiver: User, tip: CurrencyItem) -> None:
        if receiver.id == self.session_metadata.user_id:
            db.update_gold(sender.id, tip.amount)
            user_data = db.get_or_create_user(sender.id, sender.username)
            await self.highrise.send_whisper(
                sender.id,
                f"💰 ¡Gracias por tu depósito! Recibidos {tip.amount} 🪙.\n"
                f"Tu saldo acumulado es de: {user_data['balance']} 🪙.\n"
                f"Revisa tu Inbox para ver el menú o usa '!plan'."
            )

    # Copiar outfit (Whisper en Sala exclusivo para el Propietario)
    async def on_whisper(self, user: User, message: str) -> None:
        if user.id == HOSTER_OWNER_ID and message.strip().lower() == "!copy":
            try:
                outfit_resp = await self.highrise.get_user_outfit(user.id)
                if outfit_resp and hasattr(outfit_resp, 'outfit'):
                    await self.highrise.set_outfit(outfit_resp.outfit)
                    await self.highrise.send_whisper(user.id, "👕 ¡Outfit copiado con éxito!")
            except Exception as e:
                await self.highrise.send_whisper(user.id, f"❌ Error al copiar outfit: {e}")

    # Atención Principal por INBOX (Mensajes Directos)
    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        if user_id == self.session_metadata.user_id:
            return

        user_data = db.get_or_create_user(user_id)
        user_bots = db.get_user_bots(user_id)

        # Regalo pendiente
        if user_data["gift_from"]:
            await self.highrise.send_message(
                conversation_id,
                f"🎁 ¡Tienes un regalo pendiente! El usuario {user_data['gift_from']} te transfirió saldo.\n"
                f"Tu saldo actual es de: {user_data['balance']} 🪙."
            )
            db.clear_pending_gift(user_id)

        menu = f"👋 ¡Hola! Bienvenido al Servicio de Hosting Bot (Nex-Host).\n\n"
        menu += f"💰 **Tu Saldo:** {user_data['balance']} 🪙\n"
        
        if not user_data["free_trial"]:
            menu += "🎁 ¡Tienes disponible 1 Prueba Gratuita!\n"

        menu += "\n📋 **Menú de Comandos:**\n"
        menu += "🔹 `!menu` - Mostrar este menú\n"
        menu += "🔹 `!saldo` - Consultar balance\n"
        menu += "🔹 `!plan` - Ver categorías y precios\n"
        
        if not user_data["free_trial"]:
            menu += "🔹 `!free <CATEGORIA> <TOKEN> <ROOM_ID>` - Activar prueba gratis\n"
            
        menu += "🔹 `!buy <CATEGORIA> <TOKEN> <ROOM_ID>` - Comprar bot\n"
        menu += "🔹 `!gift <ID_USUARIO> <MONTO>` - Regalar saldo\n"

        # Lógica: Si el usuario tiene un solo bot, no se muestra lista, solo el estado directo
        if len(user_bots) == 1:
            b_id, r_id, st, cat = user_bots[0]
            menu += f"\n🤖 **Tu Bot:** ID `{b_id}` | Tipo: `{cat}` | Sala: `{r_id}` | Estado: `{st}`\n"
        elif len(user_bots) > 1:
            menu += f"\n🤖 Tienes {len(user_bots)} bots registrados. Usa `!mybots` para ver la lista.\n"

        if user_id == HOSTER_OWNER_ID:
            menu += "\n👑 **Panel Admin:** `!addgold`, `!mantenimiento`, `!detener`, `!activar`"

        await self.highrise.send_message(conversation_id, menu)

    # Procesamiento de comandos por Inbox
    async def on_message_response(self, user_id: str, conversation_id: str, message: str) -> None:
        parts = message.strip().split()
        if not parts:
            return

        cmd = parts[0].lower()
        user_data = db.get_or_create_user(user_id)

        if cmd in ["!saldo", "!balance"]:
            await self.highrise.send_message(conversation_id, f"💰 Tu saldo acumulado es: {user_data['balance']} 🪙.")

        elif cmd == "!plan":
            msg_plan = (
                "🤖 **SELECCIONA EL TIPO DE BOT:**\n\n"
                "[1] 🎵 MÚSICA\n"
                "[2] 🎮 JUEGOS (Contactar @_Kmi.77)\n"
                "[3] 🎉 FIESTA\n"
                "[4] ⚙️ PERSONALIZADO (Contactar @_Kmi.77)\n\n"
                "Escribe '!plan 1' o '!plan 3' para ver precios."
            )
            await self.highrise.send_message(conversation_id, msg_plan)

        elif cmd == "!plan 1":
            info = db.get_category_info("musica")
            if not info["active"]:
                await self.highrise.send_message(conversation_id, "🛑 El servicio de MÚSICA está deshabilitado.")
                return
            if info["maintenance"]:
                await self.highrise.send_message(conversation_id, "🛠️ La categoría MÚSICA está en mantenimiento.")
                return
            await self.highrise.send_message(conversation_id, "🎵 **MÚSICA:** Plan Base: 500 🪙.\nUsa: `!buy musica <TOKEN> <ROOM_ID>`")

        elif cmd == "!free":
            if user_data["free_trial"]:
                await self.highrise.send_message(conversation_id, "❌ Ya has utilizado tu prueba gratuita anteriormente.")
                return
            if len(parts) < 4:
                await self.highrise.send_message(conversation_id, "⚠️ Uso: `!free <musica/fiesta> <TOKEN> <ROOM_ID>`")
                return

            cat, token, room_id = parts[1].lower(), parts[2], parts[3]
            info = db.get_category_info(cat)
            if not info["active"] or info["maintenance"]:
                await self.highrise.send_message(conversation_id, f"🛑 La categoría {cat} no está disponible actualmente.")
                return

            success = deploy_bot_instance(user_id, cat, room_id, token)
            if success:
                db.mark_free_trial_used(user_id)
                bot_id = db.create_bot_entry(user_id, cat, room_id, token)
                await self.highrise.send_message(
                    conversation_id,
                    f"🎉 ¡Prueba gratis activada!\n🤖 Bot ID: `{bot_id}`.\n\n"
                    f"⚠️ **RECORDATORIO OBLIGATORIO:** Asigna permisos de MODERADOR 🛡️ y DISEÑADOR 🎨 a la cuenta del bot en tu sala para permitir su ingreso mediante el SDK."
                )
            else:
                await self.highrise.send_message(conversation_id, "❌ Error al desplegar la plantilla del bot.")

        elif cmd == "!buy":
            if len(parts) < 4:
                await self.highrise.send_message(conversation_id, "⚠️ Uso: `!buy <musica/fiesta> <TOKEN> <ROOM_ID>`")
                return
            cat, token, room_id = parts[1].lower(), parts[2], parts[3]
            price = 500
            if user_data["balance"] < price:
                missing = price - user_data["balance"]
                await self.highrise.send_message(conversation_id, f"🛑 Saldo insuficiente. Te faltan {missing} 🪙. Envíalos en la sala.")
                return

            info = db.get_category_info(cat)
            if not info["active"] or info["maintenance"]:
                await self.highrise.send_message(conversation_id, f"🛑 La categoría {cat} no está disponible actualmente.")
                return

            success = deploy_bot_instance(user_id, cat, room_id, token)
            if success:
                db.update_gold(user_id, -price)
                bot_id = db.create_bot_entry(user_id, cat, room_id, token)
                await self.highrise.send_message(
                    conversation_id,
                    f"✅ ¡Bot comprado y desplegado!\n🤖 ID: `{bot_id}`.\n\n"
                    f"⚠️ **RECORDATORIO OBLIGATORIO:** Asigna permisos de MODERADOR 🛡️ y DISEÑADOR 🎨 a la cuenta del bot en la sala `{room_id}` para permitir su ingreso mediante el SDK."
                )

        elif cmd == "!gift":
            if len(parts) == 3 and parts[2].isdigit():
                target_id, amount = parts[1], int(parts[2])
                if user_data["balance"] < amount:
                    await self.highrise.send_message(conversation_id, "🛑 Saldo insuficiente.")
                else:
                    db.update_gold(user_id, -amount)
                    db.update_gold(target_id, amount)
                    db.set_pending_gift(target_id, f"@{user_id}")
                    await self.highrise.send_message(conversation_id, f"✅ Has regalado {amount} 🪙 a la ID `{target_id}`.")

        # --- COMANDOS DE CONTROL DE PROPIETARIO ---
        elif cmd == "!addgold" and user_id == HOSTER_OWNER_ID:
            if len(parts) == 3 and parts[2].isdigit():
                db.update_gold(parts[1], int(parts[2]))
                await self.highrise.send_message(conversation_id, f"✅ Añadidos {parts[2]} 🪙 a la ID `{parts[1]}`.")

        elif cmd == "!mantenimiento" and user_id == HOSTER_OWNER_ID:
            if len(parts) == 3 and parts[2] in ["on", "off"]:
                db.set_maintenance(parts[1], 1 if parts[2] == "on" else 0)
                await self.highrise.send_message(conversation_id, f"✅ Mantenimiento de '{parts[1]}' actualizado.")

        elif cmd in ["!detener", "!activar"] and user_id == HOSTER_OWNER_ID:
            if len(parts) == 2:
                db.set_active_status(parts[1], 0 if cmd == "!detener" else 1)
                await self.highrise.send_message(conversation_id, f"✅ Estado de '{parts[1]}' actualizado.")
                
