import json
import os

class I18n:
    _instance = None
    _translations = {
        "es": {
            "help_header": "👑 COMANDOS PROPIETARIO/ADMIN:",
            "info_desc": "!info - Tu información",
            "role_desc": "!role - Tu rol",
            "stats_desc": "!stats - Estadísticas sala",
            "online_desc": "!online - Usuarios online",
            "test_response": "✅ Bot activo! Hola @{username}",
            "error_admin_only": "❌ ¡Solo el propietario o administradores pueden usar esto!",
            "drink_served": "🍺 Aquí tienes tu {drink}, @{username}",
            "no_balance": "❌ No tienes saldo suficiente",
            "unknown_command": "❓ Comando desconocido. Usa !help",
            "lang_success": "✅ Idioma cambiado a {lang}",
            "lang_error": "❌ Idioma no soportado (es, en)",
            "aliases": {
                "help": ["!ayuda", "!help", "!comandos", "!menu"],
                "info": ["!info", "!informacion", "!acerca"],
                "stats": ["!stats", "!estadisticas", "!sala"],
                "online": ["!online", "!enlinea", "!quien"],
                "role": ["!role", "!rol", "!rango"],
                "kick": ["!kick", "!patear", "!sacar", "!expulsar"],
                "ban": ["!ban", "!banear", "!bloquear"],
                "mute": ["!mute", "!mutear", "!silenciar"],
                "trago": ["!trago", "!drink", "!bebida", "!beber", "!copa"],
                "menu": ["!menu", "!carta", "!drinks", "!bebidas"],
                "heart": ["!heart", "!corazon", "!dar"],
                "heartall": ["!heartall", "!corazones", "!todos"],
                "jail": ["!jail", "!carcel", "!encerrar"],
                "unjail": ["!unjail", "!liberar", "!sacar_carcel"],
                "bring": ["!bring", "!traer", "!ven"],
                "goto": ["!goto", "!ir", "!ve"],
                "tele": ["!tele", "!tp", "!lugar"],
                "vip": ["!vip", "!darvip", "!premiar"],
                "stop": ["!stop", "!parar", "!detener"],
                "addmsg": ["!addmsg", "!anadirmensaje", "!nuevomensaje"],
                "delmsg": ["!delmsg", "!borrarmensaje", "!eliminarmensaje"],
                "editmsg": ["!editmsg", "!editarmensaje"],
                "listmsg": ["!listmsg", "!listarmensajes", "!mensajes"],
                "game": ["!game", "!juego"],
                "flash": ["!flash", "!salto"],
                "trackme": ["!trackme", "!seguirme"],
                "inventory": ["!inventory", "!inventario"],
                "wallet": ["!wallet", "!billetera", "!cartera"],
                "follow": ["!follow", "!seguir"],
                "bot": ["!bot", "!config"]
            }
        },
        "en": {
            "help_header": "👑 OWNER/ADMIN COMMANDS:",
            "info_desc": "!info - Your information",
            "role_desc": "!role - Your role",
            "stats_desc": "!stats - Room statistics",
            "online_desc": "!online - Online users",
            "test_response": "✅ Bot active! Hello @{username}",
            "error_admin_only": "❌ Only the owner or admins can use this!",
            "drink_served": "🍺 Here is your {drink}, @{username}",
            "no_balance": "❌ You don't have enough balance",
            "unknown_command": "❓ Unknown command. Use !help",
            "lang_success": "✅ Language set to {lang}",
            "lang_error": "❌ Language not supported (es, en)",
            "aliases": {
                "help": ["!help", "!ayuda", "!commands", "!menu"],
                "info": ["!info", "!information", "!about"],
                "stats": ["!stats", "!statistics", "!room"],
                "online": ["!online", "!onlineusers", "!who"],
                "role": ["!role", "!rank", "!status"],
                "kick": ["!kick", "!remove", "!eject", "!boot"],
                "ban": ["!ban", "!block", "!restrict"],
                "mute": ["!mute", "!silence", "!quiet"],
                "trago": ["!drink", "!trago", "!beverage", "!glass"],
                "menu": ["!menu", "!list", "!drinks", "!carta"],
                "heart": ["!heart", "!love", "!give"],
                "heartall": ["!heartall", "!loveall", "!everyone"],
                "jail": ["!jail", "!prison", "!lock"],
                "unjail": ["!unjail", "!free", "!release"],
                "bring": ["!bring", "!summon", "!come"],
                "goto": ["!goto", "!visit", "!move"],
                "tele": ["!tele", "!tp", "!location"],
                "vip": ["!vip", "!givevip", "!reward"],
                "stop": ["!stop", "!halt", "!end"]
            }
        }
    }

    def normalize_command(self, message, user_id=None):
        lang = self.user_langs.get(str(user_id), self.default_lang)
        aliases = self._translations.get(lang, self._translations[self.default_lang]).get("aliases", {})
        
        msg_lower = message.lower().strip()
        for cmd, alias_list in aliases.items():
            for alias in alias_list:
                if msg_lower.startswith(alias):
                    # Replace the alias with the standard command
                    return msg_lower.replace(alias, "!" + cmd, 1)
        return message

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(I18n, cls).__new__(cls)
            cls._instance.default_lang = "es"
            cls._instance.user_langs = {}
            cls._instance.load_user_langs()
        return cls._instance

    def load_user_langs(self):
        if os.path.exists("data/user_langs.json"):
            try:
                with open("data/user_langs.json", "r") as f:
                    self.user_langs = json.load(f)
            except:
                self.user_langs = {}

    def save_user_langs(self):
        os.makedirs("data", exist_ok=True)
        with open("data/user_langs.json", "w") as f:
            json.dump(self.user_langs, f)

    def set_user_lang(self, user_id, lang):
        if lang in self._translations:
            self.user_langs[str(user_id)] = lang
            self.save_user_langs()
            return True
        return False

    def get_text(self, key, user_id=None, **kwargs):
        lang = self.user_langs.get(str(user_id), self.default_lang)
        text = self._translations.get(lang, self._translations[self.default_lang]).get(key, key)
        return text.format(**kwargs)

i18n = I18n()
