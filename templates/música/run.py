"""
Nocturno DJ Bot Pro - Enhanced Edition
Sistema de radio streaming profesional con integración Highrise
Version: 7.0
"""
import sys

# pkg_resources es parte de setuptools; en algunos entornos (Python 3.11+)
# puede faltar. Lo instalamos automáticamente antes de importar highrise.
try:
    import pkg_resources  # noqa: F401
except ModuleNotFoundError:
    # nexhost y algunos entornos no tienen setuptools instalado.
    # highrise solo usa pkg_resources para verificar versiones, así que
    # inyectamos un stub mínimo para que el import no falle.
    import types as _types
    _stub = _types.ModuleType("pkg_resources")
    class _FakeDist:
        version = "0.0.0"
    def _get_distribution(name):
        return _FakeDist()
    _stub.get_distribution = _get_distribution
    _stub.DistributionNotFound = Exception
    _stub.require = lambda *a, **kw: None
    sys.modules["pkg_resources"] = _stub
    import pkg_resources  # noqa: F401

from radio import RadioStation
import threading
import asyncio
import json
import time
import traceback
import os
import logging
from datetime import datetime
from queue import Queue
from flask import Flask, Response, render_template_string, request, redirect, url_for, session, jsonify
from functools import wraps
from werkzeug.utils import secure_filename
from typing import Optional, Dict, Any

# ================== CONFIGURACIÓN PROFESIONAL ==================
PASSWORD = os.environ.get("DJ_PASSWORD", "070927")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.opus'}
TEMP_UPLOAD_FOLDER = "temp_uploads"
JINGLES_FOLDER = "jingles"
LOGS_FOLDER = "logs"
BACKUP_FOLDER = "backups"

# ================== LOGGING PROFESIONAL ==================
LOGIN_LOGGER_NAME = 'NocturnoDJ.Login'

def setup_logging():
    """Configura logging: solo errores y eventos de login"""
    os.makedirs(LOGS_FOLDER, exist_ok=True)

    # Logger principal — solo errores
    logger = logging.getLogger('NocturnoDJ')
    logger.setLevel(logging.ERROR)

    log_filename = os.path.join(LOGS_FOLDER, f"nocturno_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s'))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(levelname)s | %(message)s'))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Logger de login — captura INFO+
    login_logger = logging.getLogger(LOGIN_LOGGER_NAME)
    login_logger.setLevel(logging.INFO)
    login_logger.propagate = False

    login_log_filename = os.path.join(LOGS_FOLDER, f"login_{datetime.now().strftime('%Y%m%d')}.log")
    login_file_handler = logging.FileHandler(login_log_filename, encoding='utf-8')
    login_file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s'))

    login_console_handler = logging.StreamHandler(sys.stdout)
    login_console_handler.setFormatter(logging.Formatter('LOGIN | %(message)s'))

    login_logger.addHandler(login_file_handler)
    login_logger.addHandler(login_console_handler)

    return logger

def get_login_logger():
    return logging.getLogger(LOGIN_LOGGER_NAME)

logger = setup_logging()

# ================== UTILIDADES PROFESIONALES ==================
def format_duration(seconds: int) -> str:
    """Formatea duración en formato MM:SS"""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"

def get_file_size_mb(file_path: str) -> float:
    """Obtiene el tamaño de un archivo en MB"""
    return os.path.getsize(file_path) / (1024 * 1024)

if not os.path.exists(JINGLES_FOLDER):
    os.makedirs(JINGLES_FOLDER)

if not os.path.exists(TEMP_UPLOAD_FOLDER):
    os.makedirs(TEMP_UPLOAD_FOLDER)

if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER)

# ================== VARIABLES GLOBALES PARA TRACKING ==================
radio_start_time = None
reconnect_count = 0

# ================== RADIO SINGLETON ==================
radio = RadioStation()

def start_radio():
    global radio_start_time
    pass  # log suprimido
    radio_start_time = datetime.now()
    radio.start()
    pass  # log suprimido

def get_radio_uptime() -> str:
    """Calcula el tiempo de actividad de la radio"""
    if not radio_start_time:
        return "N/A"
    delta = datetime.now() - radio_start_time
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return f"{delta.days}d {hours}h {minutes}m"

radio_thread = threading.Thread(target=start_radio, daemon=True)
radio_thread.start()

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def run_highrise_bot():
    """Lanza el bot de Highrise con reconexión automática."""
    import asyncio
    from main import Bot
    from highrise.__main__ import main as highrise_main, BotDefinition

    conf    = load_json("config.json")
    room_id = conf.get("room_id", "")
    token   = conf.get("api_token", "")

    if not room_id or not token:
        print("[BOT] ❌ Faltan room_id o api_token en config.json")
        return

    print(f"[BOT] 🚀 Conectando a sala: {room_id}")
    backoff = 5
    while True:
        try:
            definition = BotDefinition(bot=Bot(), room_id=room_id, api_token=token)
            asyncio.run(highrise_main([definition]))
        except Exception as e:
            print(f"[BOT] ⚠️ Desconectado: {e}. Reconectando en {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)

# ================== FLASK APP ==================
app = Flask(__name__)
app.secret_key = "nocturno_dj_secret_key_2024_ultra_pro"

def allowed_file(filename):
    ext = os.path.splitext(filename.lower())[1]
    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.m4v', '.3gp'}
    if ext in VIDEO_EXTENSIONS:
        return False
    return ext in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ================== TEMPLATES HTML ==================
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nocturno DJ | Acceso</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&family=Orbitron:wght@700;900&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

        @keyframes bgPulse {
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        @keyframes scanline {
            0% { transform: translateY(-100vh); }
            100% { transform: translateY(100vh); }
        }
        @keyframes cardIn {
            from { opacity:0; transform: translateY(40px) scale(0.96); }
            to   { opacity:1; transform: translateY(0)    scale(1); }
        }
        @keyframes logoPulse {
            0%,100% { transform: scale(1);    filter: drop-shadow(0 0 18px rgba(102,126,234,0.7)); }
            50%     { transform: scale(1.06); filter: drop-shadow(0 0 35px rgba(102,126,234,1)); }
        }
        @keyframes titleGlow {
            0%,100% { text-shadow: 0 0 12px rgba(102,126,234,.9), 0 0 30px rgba(118,75,162,.6); }
            50%     { text-shadow: 0 0 22px rgba(102,126,234,1), 0 0 55px rgba(118,75,162,.9), 0 0 80px rgba(255,0,110,.4); }
        }
        @keyframes barDance {
            0%,100% { height: 8px; }
            50%     { height: 28px; }
        }
        @keyframes floatOrb {
            0%,100% { transform: translateY(0) scale(1); opacity:.35; }
            50%     { transform: translateY(-30px) scale(1.15); opacity:.55; }
        }
        @keyframes inputFocusLine {
            from { width:0; left:50%; }
            to   { width:100%; left:0; }
        }
        @keyframes btnShimmer {
            0%   { background-position: -200% center; }
            100% { background-position:  200% center; }
        }
        @keyframes errorShake {
            0%,100% { transform: translateX(0); }
            20%,60% { transform: translateX(-8px); }
            40%,80% { transform: translateX(8px); }
        }

        body {
            font-family: 'Poppins', sans-serif;
            min-height: 100vh;
            background: linear-gradient(-45deg, #050510, #0d0d1f, #120828, #07091a);
            background-size: 400% 400%;
            animation: bgPulse 18s ease infinite;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
        }

        /* scanline sutil */
        body::before {
            content:'';
            position:fixed; inset:0;
            background: repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(102,126,234,.025) 3px, rgba(102,126,234,.025) 4px);
            pointer-events:none; z-index:0;
        }
        /* luz de barrido */
        body::after {
            content:'';
            position:fixed; left:0; right:0; height:3px;
            background: linear-gradient(90deg, transparent, rgba(102,126,234,.6), transparent);
            animation: scanline 8s linear infinite;
            pointer-events:none; z-index:1;
        }

        /* Orbes de fondo */
        .orb {
            position:fixed; border-radius:50%;
            background: radial-gradient(circle, rgba(102,126,234,.25), transparent 70%);
            filter: blur(60px);
            animation: floatOrb ease-in-out infinite;
            pointer-events:none; z-index:0;
        }

        /* ---- CARD ---- */
        .card {
            position: relative; z-index:10;
            width: min(420px, 92vw);
            padding: 52px 44px 48px;
            background: rgba(255,255,255,.028);
            border: 1px solid rgba(102,126,234,.22);
            border-radius: 28px;
            backdrop-filter: blur(28px);
            box-shadow:
                0 0 0 1px rgba(255,255,255,.05) inset,
                0 30px 80px rgba(0,0,0,.55),
                0 0 60px rgba(102,126,234,.12);
            animation: cardIn .8s cubic-bezier(.22,1,.36,1) both;
            text-align: center;
        }
        /* borde brillante superior */
        .card::before {
            content:'';
            position:absolute; top:0; left:15%; right:15%; height:1px;
            background: linear-gradient(90deg, transparent, rgba(102,126,234,.9), rgba(255,0,110,.7), rgba(102,126,234,.9), transparent);
            border-radius:2px;
        }

        /* ---- LOGO SVG ---- */
        .logo-wrap {
            width:80px; height:80px;
            margin: 0 auto 24px;
            display:flex; align-items:center; justify-content:center;
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-radius:22px;
            animation: logoPulse 3s ease-in-out infinite;
            box-shadow: 0 8px 30px rgba(102,126,234,.4);
        }
        .logo-wrap svg { width:42px; height:42px; fill:#fff; }

        /* ---- TITLE ---- */
        .brand {
            font-family:'Orbitron', sans-serif;
            font-size:26px; font-weight:900; letter-spacing:4px;
            background: linear-gradient(135deg, #a78bfa, #667eea, #ff006e);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            background-clip:text;
            animation: titleGlow 3.5s ease-in-out infinite;
            margin-bottom:6px;
        }
        .subtitle {
            color:rgba(255,255,255,.42);
            font-size:12px; letter-spacing:2.5px; text-transform:uppercase;
            font-weight:500; margin-bottom:36px;
        }

        /* ---- EQ BARS DECORATIVAS ---- */
        .eq-deco {
            display:flex; gap:4px; justify-content:center;
            align-items:flex-end; height:32px;
            margin-bottom:30px;
        }
        .eq-deco span {
            width:4px; border-radius:2px;
            background: linear-gradient(180deg, #667eea, #ff006e);
            animation: barDance ease-in-out infinite;
        }

        /* ---- INPUT GROUP ---- */
        .input-group {
            position:relative; margin-bottom:20px;
        }
        .input-group input {
            width:100%;
            padding:17px 52px 17px 20px;
            background:rgba(255,255,255,.045);
            border:1px solid rgba(255,255,255,.1);
            border-radius:14px;
            color:#fff; font-size:15px;
            font-family:'Poppins',sans-serif;
            outline:none;
            transition: border-color .3s, background .3s;
        }
        .input-group input::placeholder { color:rgba(255,255,255,.28); }
        .input-group input:focus {
            border-color:rgba(102,126,234,.7);
            background:rgba(102,126,234,.07);
        }
        /* línea animada bajo input */
        .input-group::after {
            content:'';
            position:absolute; bottom:0; left:50%; width:0; height:2px;
            background: linear-gradient(90deg, #667eea, #ff006e);
            border-radius:1px;
            transition:none;
        }
        .input-group:focus-within::after {
            animation: inputFocusLine .35s ease forwards;
        }
        /* ojo contraseña */
        .eye-btn {
            position:absolute; right:16px; top:50%; transform:translateY(-50%);
            background:none; border:none; cursor:pointer; color:rgba(255,255,255,.35);
            padding:4px; line-height:0;
            transition:color .25s;
        }
        .eye-btn:hover { color:rgba(102,126,234,.9); }
        .eye-btn svg { width:20px; height:20px; fill:currentColor; }

        /* ---- BUTTON ---- */
        .btn-access {
            width:100%; padding:17px;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 40%, #ff006e 70%, #667eea 100%);
            background-size:300% 100%;
            color:#fff; border:none; border-radius:14px;
            font-size:15px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase;
            cursor:pointer;
            transition: transform .2s, box-shadow .3s;
            animation: btnShimmer 4s linear infinite;
            box-shadow: 0 6px 28px rgba(102,126,234,.35);
        }
        .btn-access:hover {
            transform:translateY(-3px);
            box-shadow: 0 12px 40px rgba(102,126,234,.55), 0 0 60px rgba(255,0,110,.25);
        }
        .btn-access:active { transform:translateY(0); }

        /* ---- ERROR ---- */
        .error-box {
            background:rgba(255,70,70,.09);
            border:1px solid rgba(255,70,70,.3);
            color:#ff7a7a;
            padding:13px 16px; border-radius:12px;
            font-size:13px; margin-bottom:18px;
            animation: errorShake .45s ease;
            display:flex; align-items:center; gap:10px; text-align:left;
        }
        .error-box svg { width:18px; height:18px; fill:#ff7a7a; flex-shrink:0; }

        /* ---- FOOTER ---- */
        .footer-line {
            margin-top:26px;
            color:rgba(255,255,255,.2); font-size:11px; letter-spacing:1px;
        }
    </style>
</head>
<body>
    <!-- Orbes -->
    <div class="orb" style="width:400px;height:400px;top:-100px;left:-100px;animation-duration:14s;animation-delay:0s;"></div>
    <div class="orb" style="width:300px;height:300px;bottom:-80px;right:-80px;animation-duration:11s;animation-delay:3s;"></div>
    <div class="orb" style="width:200px;height:200px;top:40%;left:60%;animation-duration:9s;animation-delay:1.5s;"></div>

    <div class="card">
        <!-- Logo -->
        <div class="logo-wrap">
            <svg viewBox="0 0 24 24">
                <path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"/>
            </svg>
        </div>

        <div class="brand">NOCTURNO</div>
        <div class="subtitle">DJ Control Panel</div>

        <!-- EQ decorativa animada -->
        <div class="eq-deco" id="eqDeco"></div>

        {% if error %}
        <div class="error-box">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
            <span>{{ error }}</span>
        </div>
        {% endif %}

        <form method="POST" autocomplete="off">
            <div class="input-group">
                <input type="password" name="password" id="passInput" placeholder="Contraseña de acceso" required autofocus>
                <button type="button" class="eye-btn" id="eyeBtn" onclick="togglePass()">
                    <svg id="eyeIcon" viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zm0 12.5a5 5 0 1 1 0-10 5 5 0 0 1 0 10zm0-8a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"/></svg>
                </button>
            </div>
            <button type="submit" class="btn-access">Acceder</button>
        </form>

        <div class="footer-line">NOCTURNO DJ &copy; 2025 &mdash; v7.0 PRO</div>
    </div>

    <script>
        // EQ bars dinámicas
        const deco = document.getElementById('eqDeco');
        const barCount = 18;
        const delays = [0, .2, .4, .1, .3, .5, .15, .35, .25, .45, .05, .55, .2, .4, .1, .3, .0, .5];
        const heights = [12,22,16,28,10,24,18,30,14,20,26,8,22,16,28,12,24,18];
        for (let i = 0; i < barCount; i++) {
            const s = document.createElement('span');
            s.style.animationDelay = delays[i] + 's';
            s.style.animationDuration = (.6 + Math.random() * .6) + 's';
            s.style.height = heights[i] + 'px';
            deco.appendChild(s);
        }

        // Toggle contraseña
        function togglePass() {
            const inp = document.getElementById('passInput');
            const icon = document.getElementById('eyeIcon');
            if (inp.type === 'password') {
                inp.type = 'text';
                icon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-5 0-9.27-3.11-11-7.5a10.07 10.07 0 0 1 2.32-3.54M6.53 6.53A9.94 9.94 0 0 1 12 4.5c5 0 9.27 3.11 11 7.5a10 10 0 0 1-4.13 5.12M1 1l22 22"/>';
            } else {
                inp.type = 'password';
                icon.innerHTML = '<path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zm0 12.5a5 5 0 1 1 0-10 5 5 0 0 1 0 10zm0-8a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"/>';
            }
        }
    </script>
</body>
</html>
"""

# ================== TEMPLATE PRINCIPAL MEJORADO ==================
MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Nocturno DJ | Player Pro</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&family=Orbitron:wght@700;900&display=swap" rel="stylesheet">
    <style>
        * { 
            margin: 0; 
            padding: 0; 
            box-sizing: border-box; 
            -webkit-tap-highlight-color: transparent;
        }
        
        /* ========== VARIABLES CSS ========== */
        :root {
            --primary: #667eea;
            --secondary: #764ba2;
            --dark-1: #0a0a0f;
            --dark-2: #1a1a2e;
            --dark-3: #16213e;
            --dark-4: #0f3460;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }
        
        /* ========== FONDO ANIMADO PRO ========== */
        @keyframes gradientAnimation {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        
        @keyframes floatingParticles {
            0%, 100% { transform: translateY(0) rotate(0deg) scale(1); opacity: 0.4; }
            50% { transform: translateY(-30px) rotate(180deg) scale(1.2); opacity: 0.7; }
        }
        
        @keyframes stars {
            0%, 100% { opacity: 0.3; transform: scale(1); }
            50% { opacity: 1; transform: scale(1.5); }
        }
        
        body {
            font-family: 'Poppins', sans-serif;
            background: linear-gradient(-45deg, var(--dark-1), var(--dark-2), var(--dark-3), var(--dark-4));
            background-size: 400% 400%;
            animation: gradientAnimation 20s ease infinite;
            color: #fff;
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
        }
        
        /* Partículas mejoradas */
        .particle {
            position: fixed;
            background: radial-gradient(circle, rgba(102, 126, 234, 0.4), transparent);
            border-radius: 50%;
            pointer-events: none;
            animation: floatingParticles 10s ease-in-out infinite;
            z-index: 0;
            filter: blur(2px);
        }
        
        /* Estrellas de fondo */
        .star {
            position: fixed;
            width: 2px;
            height: 2px;
            background: white;
            border-radius: 50%;
            pointer-events: none;
            animation: stars 3s ease-in-out infinite;
            z-index: 0;
        }
        
        /* ========== HEADER MEJORADO ========== */
        .header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 70px;
            background: rgba(15, 15, 20, 0.98);
            backdrop-filter: blur(30px);
            border-bottom: 1px solid rgba(102, 126, 234, 0.2);
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 25px;
            z-index: 1000;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.3);
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .header-logo {
            width: 45px;
            height: 45px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }
        
        /* ========== EFECTOS ESPECIALES PARA "NOCTURNO" ========== */
        @keyframes neonGlow {
            0%, 100% { 
                text-shadow: 0 0 10px rgba(102, 126, 234, 0.8),
                             0 0 20px rgba(102, 126, 234, 0.6),
                             0 0 30px rgba(102, 126, 234, 0.4),
                             0 0 40px rgba(118, 75, 162, 0.3);
            }
            50% { 
                text-shadow: 0 0 20px rgba(102, 126, 234, 1),
                             0 0 30px rgba(102, 126, 234, 0.8),
                             0 0 40px rgba(102, 126, 234, 0.6),
                             0 0 60px rgba(118, 75, 162, 0.5),
                             0 0 80px rgba(118, 75, 162, 0.3);
            }
        }
        
        @keyframes glitchEffect {
            0% { transform: translate(0); }
            20% { transform: translate(-2px, 2px); }
            40% { transform: translate(-2px, -2px); }
            60% { transform: translate(2px, 2px); }
            80% { transform: translate(2px, -2px); }
            100% { transform: translate(0); }
        }
        
        @keyframes colorShift {
            0%, 100% { filter: hue-rotate(0deg); }
            50% { filter: hue-rotate(20deg); }
        }
        
        .header-title {
            font-size: 22px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary), var(--secondary), #ff006e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            background-size: 200% 200%;
            animation: neonGlow 3s ease-in-out infinite, colorShift 5s ease-in-out infinite;
            position: relative;
            letter-spacing: 2px;
            font-family: 'Audiowide', 'Orbitron', cursive;
        }
        
        .header-title:hover {
            animation: neonGlow 1s ease-in-out infinite, glitchEffect 0.3s ease-in-out;
        }
        
        .header-title::before {
            content: attr(data-text);
            position: absolute;
            left: -2px;
            text-shadow: -2px 0 #ff006e;
            opacity: 0;
            animation: glitch1 4s infinite;
            z-index: -1;
        }
        
        .header-title::after {
            content: attr(data-text);
            position: absolute;
            left: 2px;
            text-shadow: 2px 0 #00fff9;
            opacity: 0;
            animation: glitch2 4s infinite;
            z-index: -1;
        }
        
        @keyframes glitch1 {
            0%, 100% { opacity: 0; }
            2%, 5% { opacity: 0.8; left: -2px; }
            6% { opacity: 0; }
        }
        
        @keyframes glitch2 {
            0%, 100% { opacity: 0; }
            3%, 7% { opacity: 0.7; left: 2px; }
            8% { opacity: 0; }
        }
        
        .header-subtitle {
            font-size: 11px;
            color: rgba(255,255,255,0.5);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .header-button {
            width: 45px;
            height: 45px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            color: #fff;
            font-size: 20px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .header-button:hover {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border-color: transparent;
            transform: scale(1.05);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        
        /* ========== PLAYER PRINCIPAL ULTRA MEJORADO ========== */
        .player-container {
            padding: 90px 20px 140px;
            max-width: 650px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
        }
        
        /* Contenedor del álbum con efecto glow */
        .album-container {
            position: relative;
            margin-bottom: 35px;
        }
        
        @keyframes albumPulse {
            0%, 100% { 
                transform: scale(1);
                box-shadow: 
                    0 25px 70px rgba(102, 126, 234, 0.4),
                    0 0 80px rgba(118, 75, 162, 0.2),
                    inset 0 0 60px rgba(102, 126, 234, 0.1);
            }
            50% { 
                transform: scale(1.03);
                box-shadow: 
                    0 30px 90px rgba(102, 126, 234, 0.6),
                    0 0 120px rgba(118, 75, 162, 0.4),
                    inset 0 0 80px rgba(102, 126, 234, 0.2);
            }
        }
        
        @keyframes albumRotate {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        @keyframes ripple {
            0% {
                transform: scale(0.8);
                opacity: 0;
            }
            50% {
                opacity: 0.6;
            }
            100% {
                transform: scale(1.4);
                opacity: 0;
            }
        }
        
        /* ========== ECUALIZADOR CIRCULAR ALREDEDOR DEL ÁLBUM ========== */
        .equalizer-ring {
            position: absolute;
            inset: -30px;
            pointer-events: none;
            z-index: 1;
        }
        
        .eq-bar {
            position: absolute;
            width: 4px;
            height: 20px;
            background: linear-gradient(180deg, 
                rgba(102, 126, 234, 0.9), 
                rgba(255, 0, 110, 0.9),
                transparent);
            border-radius: 10px;
            transform-origin: center calc(50% + 120px);
            left: 50%;
            top: 0;
            transform: translateX(-50%) rotate(calc(var(--i) * 30deg));
            opacity: 0;
            transition: opacity 0.3s;
        }
        
        .album-art.playing ~ .album-glow ~ * .eq-bar,
        .album-container:has(.album-art.playing) .eq-bar {
            opacity: 1;
            animation: equalizerPulse 0.8s ease-in-out infinite;
            animation-delay: calc(var(--i) * 0.1s);
        }
        
        @keyframes equalizerPulse {
            0%, 100% { 
                height: 15px;
                filter: blur(0px);
            }
            50% { 
                height: 35px;
                filter: blur(1px);
            }
        }
        
        .album-art {
            width: 100%;
            aspect-ratio: 1;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #ff006e 75%, #667eea 100%);
            background-size: 300% 300%;
            border-radius: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 130px;
            position: relative;
            overflow: hidden;
            transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
            border: 3px solid rgba(255,255,255,0.1);
            transform-style: preserve-3d;
            perspective: 1000px;
        }
        
        .album-art.playing {
            animation: albumPulse 4s ease-in-out infinite, albumRotate3D 20s linear infinite;
            background-position: 100% 100%;
            box-shadow: 0 20px 60px rgba(102, 126, 234, 0.5),
                        0 0 100px rgba(118, 75, 162, 0.3);
        }
        
        @keyframes albumRotate3D {
            0% { transform: rotateY(0deg) rotateX(0deg); }
            25% { transform: rotateY(5deg) rotateX(-5deg); }
            50% { transform: rotateY(0deg) rotateX(0deg); }
            75% { transform: rotateY(-5deg) rotateX(5deg); }
            100% { transform: rotateY(0deg) rotateX(0deg); }
        }
        
        /* Resplandor interior rotativo con partículas */
        .album-art::before {
            content: '';
            position: absolute;
            inset: -50%;
            background: 
                radial-gradient(circle at 30% 30%, rgba(255,255,255,0.6) 0%, transparent 3%),
                radial-gradient(circle at 70% 40%, rgba(102, 126, 234,0.6) 0%, transparent 3%),
                radial-gradient(circle at 40% 70%, rgba(255, 0, 110,0.6) 0%, transparent 3%),
                radial-gradient(circle at 60% 80%, rgba(0, 255, 249,0.6) 0%, transparent 3%),
                radial-gradient(circle at center, rgba(255,255,255,0.3), transparent 60%);
            background-size: 200% 200%;
            animation: albumRotate 25s linear infinite, particleFloat 15s ease-in-out infinite;
            opacity: 0.8;
        }
        
        @keyframes particleFloat {
            0%, 100% { background-position: 0% 0%, 100% 0%, 0% 100%, 100% 100%, 50% 50%; }
            25% { background-position: 100% 100%, 0% 100%, 100% 0%, 0% 0%, 50% 50%; }
            50% { background-position: 50% 50%, 50% 50%, 50% 50%, 50% 50%, 50% 50%; }
            75% { background-position: 0% 100%, 100% 0%, 100% 100%, 0% 0%, 50% 50%; }
        }
        
        /* Efecto de ondas al cambiar canción */
        .album-art::after {
            content: '';
            position: absolute;
            inset: 0;
            border: 4px solid rgba(255, 255, 255, 0.6);
            border-radius: 30px;
            opacity: 0;
        }
        
        .album-art.track-change::after {
            animation: ripple 1s ease-out;
        }
        
        /* Emoji con transición mejorada */
        #albumEmoji {
            position: relative;
            z-index: 2;
            transition: all 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55);
            filter: drop-shadow(0 10px 30px rgba(0,0,0,0.4));
        }
        
        .album-art.track-change #albumEmoji {
            transform: scale(0.3) rotate(360deg);
            opacity: 0;
        }
        
        /* Overlay de brillo */
        .album-glow {
            position: absolute;
            inset: -20px;
            background: radial-gradient(circle, rgba(102, 126, 234, 0.3), transparent 70%);
            filter: blur(30px);
            opacity: 0;
            transition: opacity 0.5s;
            pointer-events: none;
        }
        
        .album-art.playing ~ .album-glow {
            opacity: 1;
        }
        
        /* Track info con animaciones */
        .track-info {
            text-align: center;
            margin-bottom: 40px;
            position: relative;
        }
        
        @keyframes fadeInSlideUp {
            from {
                opacity: 0;
                transform: translateY(15px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .track-title {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 10px;
            color: #fff;
            text-shadow: 0 3px 15px rgba(0, 0, 0, 0.4);
            animation: fadeInSlideUp 0.8s ease-out;
            line-height: 1.3;
        }
        
        .track-artist {
            font-size: 17px;
            color: rgba(255,255,255,0.6);
            animation: fadeInSlideUp 0.8s ease-out 0.1s backwards;
            font-weight: 500;
        }
        
        /* Barra de progreso premium */
        .progress-container {
            margin-bottom: 35px;
        }
        
        .progress-bar {
            width: 100%;
            height: 8px;
            background: rgba(255,255,255,0.08);
            border-radius: 4px;
            margin-bottom: 12px;
            position: relative;
            overflow: hidden;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3);
            cursor: pointer;
        }
        
        @keyframes progressShine {
            0% { left: -100%; }
            100% { left: 100%; }
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--primary), var(--secondary), var(--primary));
            background-size: 200% 100%;
            border-radius: 4px;
            width: 0%;
            transition: width 0.3s ease;
            position: relative;
            overflow: hidden;
            box-shadow: 0 0 15px rgba(102, 126, 234, 0.5);
        }
        
        .progress-fill::after {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, 
                transparent, 
                rgba(255,255,255,0.4), 
                transparent
            );
            animation: progressShine 2.5s ease-in-out infinite;
        }
        
        .time-info {
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            color: rgba(255,255,255,0.5);
            font-weight: 500;
        }
        
        /* ========== CONTROLES PRINCIPALES CON BOTONES SVG ========== */
        .playback-controls {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 20px;
            margin-bottom: 30px;
        }
        
        /* Botones base con SVG */
        .control-btn {
            width: 65px;
            height: 65px;
            background: rgba(255,255,255,0.06);
            border: 2px solid rgba(255,255,255,0.1);
            border-radius: 50%;
            color: #fff;
            cursor: pointer;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
        }
        
        .control-btn::before {
            content: '';
            position: absolute;
            inset: -5px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            opacity: 0;
            transition: opacity 0.4s;
            z-index: 0;
        }
        
        .control-btn:hover::before {
            opacity: 0.3;
        }
        
        .control-btn svg {
            width: 28px;
            height: 28px;
            position: relative;
            z-index: 1;
            fill: currentColor;
            transition: all 0.3s;
        }
        
        .control-btn:hover {
            transform: translateY(-3px) scale(1.08) rotate(5deg);
            border-color: var(--primary);
            background: rgba(102, 126, 234, 0.15);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3),
                        0 0 40px rgba(102, 126, 234, 0.2);
        }
        
        .control-btn:hover svg {
            transform: scale(1.15);
            filter: drop-shadow(0 0 8px rgba(255, 255, 255, 0.5));
        }
        
        .control-btn:active {
            transform: translateY(0) scale(0.95);
        }
        
        /* Botón play/pause especial */
        .control-btn.play-pause {
            width: 85px;
            height: 85px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border: none;
            box-shadow: 0 10px 40px rgba(102, 126, 234, 0.4);
        }
        
        .control-btn.play-pause svg {
            width: 36px;
            height: 36px;
            fill: white;
        }
        
        @keyframes playingPulse {
            0%, 100% {
                box-shadow: 
                    0 10px 40px rgba(102, 126, 234, 0.5),
                    0 0 0 0 rgba(102, 126, 234, 0.8);
                transform: scale(1);
            }
            50% {
                box-shadow: 
                    0 15px 50px rgba(102, 126, 234, 0.7),
                    0 0 0 12px rgba(102, 126, 234, 0);
                transform: scale(1.03);
            }
        }
        
        .control-btn.play-pause.playing {
            animation: playingPulse 2.5s ease-in-out infinite;
        }
        
        .control-btn.play-pause:hover {
            transform: translateY(-3px) scale(1.1);
            box-shadow: 0 15px 50px rgba(102, 126, 234, 0.6);
        }
        
        /* ========== PANEL DE ESTADÍSTICAS MEJORADO ========== */
        @keyframes statAppear {
            from {
                opacity: 0;
                transform: translateY(25px) scale(0.9);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
            }
        }
        
        .stats-panel {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin: 0 0 30px 0;
        }
        
        .stat-card {
            background: rgba(255,255,255,0.04);
            border-radius: 20px;
            padding: 25px 15px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.08);
            transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
            animation: statAppear 0.8s ease-out backwards;
            position: relative;
            overflow: hidden;
            backdrop-filter: blur(10px);
        }
        
        .stat-card:nth-child(1) { animation-delay: 0.1s; }
        .stat-card:nth-child(2) { animation-delay: 0.2s; }
        .stat-card:nth-child(3) { animation-delay: 0.3s; }
        
        .stat-card::before {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            opacity: 0;
            transition: opacity 0.4s;
        }
        
        .stat-card:hover {
            background: rgba(255,255,255,0.08);
            transform: translateY(-8px);
            border-color: rgba(102, 126, 234, 0.5);
            box-shadow: 
                0 15px 40px rgba(102, 126, 234, 0.3),
                inset 0 1px 0 rgba(255,255,255,0.1);
        }
        
        .stat-card:hover::before {
            opacity: 0.15;
        }
        
        @keyframes iconFloat {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-6px); }
        }
        
        .stat-icon {
            font-size: 32px;
            display: block;
            margin-bottom: 10px;
            position: relative;
            z-index: 1;
            animation: iconFloat 4s ease-in-out infinite;
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
        }
        
        .stat-value {
            font-size: 26px;
            font-weight: 800;
            display: block;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 6px;
            position: relative;
            z-index: 1;
        }
        
        .stat-label {
            font-size: 11px;
            color: rgba(255,255,255,0.5);
            display: block;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
            position: relative;
            z-index: 1;
        }
        
        /* ========== VISUALIZADOR ULTRA MEJORADO ========== */
        .visualizer-container {
            width: 100%;
            height: 120px;
            background: rgba(255,255,255,0.03);
            border-radius: 20px;
            margin-bottom: 25px;
            overflow: hidden;
            position: relative;
            border: 1px solid rgba(255,255,255,0.06);
            box-shadow: 
                inset 0 2px 10px rgba(0, 0, 0, 0.4),
                0 4px 20px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(10px);
        }
        
        #audioVisualizer {
            width: 100%;
            height: 100%;
            display: block;
        }
        
        @keyframes visualizerGlow {
            0%, 100% { 
                left: -100%; 
                opacity: 0.3;
            }
            50% { 
                left: 50%; 
                opacity: 0.6;
            }
            100% {
                left: 200%;
                opacity: 0.3;
            }
        }
        
        .visualizer-container::after {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, 
                transparent, 
                rgba(102, 126, 234, 0.3), 
                transparent
            );
            animation: visualizerGlow 4s ease-in-out infinite;
            pointer-events: none;
        }
        
        /* ========== CONTROLES AVANZADOS MEJORADOS ========== */
        .advanced-controls {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin: 0 0 25px 0;
        }
        
        .adv-btn {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 18px;
            color: #fff;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            font-family: 'Poppins', sans-serif;
            position: relative;
            overflow: hidden;
            backdrop-filter: blur(10px);
        }
        
        .adv-btn::before {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            opacity: 0;
            transition: opacity 0.4s;
        }
        
        .adv-btn svg {
            width: 20px;
            height: 20px;
            position: relative;
            z-index: 1;
            fill: currentColor;
            transition: all 0.3s;
        }
        
        .adv-btn span {
            position: relative;
            z-index: 1;
        }
        
        .adv-btn:hover {
            background: rgba(255,255,255,0.08);
            border-color: var(--primary);
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.25);
        }
        
        .adv-btn:hover::before {
            opacity: 0.15;
        }
        
        .adv-btn:hover svg {
            transform: scale(1.1);
        }
        
        .adv-btn:active {
            transform: translateY(0);
        }
        
        .adv-btn.active {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border-color: transparent;
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
        }
        
        .adv-btn.active::before {
            opacity: 0;
        }
        
        /* ========== VOLUME CONTROL ========== */
        .volume-control {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 20px;
            background: rgba(255,255,255,0.04);
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.08);
            margin-bottom: 25px;
            backdrop-filter: blur(10px);
        }
        
        .volume-icon {
            width: 24px;
            height: 24px;
            color: var(--primary);
        }
        
        .volume-slider {
            flex: 1;
            height: 6px;
            -webkit-appearance: none;
            appearance: none;
            background: rgba(255,255,255,0.1);
            border-radius: 3px;
            outline: none;
            transition: all 0.3s;
        }
        
        .volume-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 18px;
            height: 18px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 2px 10px rgba(102, 126, 234, 0.5);
            transition: all 0.3s;
        }
        
        .volume-slider::-webkit-slider-thumb:hover {
            transform: scale(1.2);
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.7);
        }
        
        .volume-slider::-moz-range-thumb {
            width: 18px;
            height: 18px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border-radius: 50%;
            cursor: pointer;
            border: none;
            box-shadow: 0 2px 10px rgba(102, 126, 234, 0.5);
        }
        
        .volume-value {
            min-width: 40px;
            text-align: right;
            font-weight: 600;
            color: var(--primary);
            font-size: 14px;
        }
        
        /* ========== MENU DE CONFIGURACIÓN ========== */
        .settings-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.85);
            backdrop-filter: blur(15px);
            z-index: 2000;
            display: none;
            opacity: 0;
            transition: opacity 0.4s;
        }
        
        .settings-overlay.active {
            display: block;
            opacity: 1;
        }
        
        .settings-panel {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 30px 30px 0 0;
            padding: 30px 25px 45px;
            max-height: 90vh;
            overflow-y: auto;
            transform: translateY(100%);
            transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
            border-top: 2px solid rgba(102, 126, 234, 0.3);
            box-shadow: 0 -10px 60px rgba(0, 0, 0, 0.5);
        }
        
        .settings-overlay.active .settings-panel {
            transform: translateY(0);
        }
        
        .settings-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid rgba(255,255,255,0.1);
        }
        
        .settings-title {
            font-size: 26px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .close-settings {
            width: 40px;
            height: 40px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            color: #fff;
            font-size: 22px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .close-settings:hover {
            background: rgba(239, 68, 68, 0.2);
            border-color: var(--danger);
            transform: rotate(90deg);
        }
        
        .settings-section {
            margin-bottom: 30px;
        }
        
        .section-title {
            font-size: 13px;
            color: rgba(255,255,255,0.5);
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 15px;
            font-weight: 600;
        }
        
        .setting-button {
            width: 100%;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 20px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            transition: all 0.4s;
            color: #fff;
            position: relative;
            overflow: hidden;
        }
        
        .setting-button::before {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            opacity: 0;
            transition: opacity 0.3s;
        }
        
        .setting-button:hover {
            background: rgba(255,255,255,0.08);
            border-color: var(--primary);
            transform: translateX(5px);
        }
        
        .setting-button:hover::before {
            opacity: 0.1;
        }
        
        .setting-button:active {
            transform: translateX(0) scale(0.98);
        }
        
        .setting-left {
            display: flex;
            align-items: center;
            gap: 18px;
            position: relative;
            z-index: 1;
        }
        
        .setting-icon {
            width: 50px;
            height: 50px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }
        
        .setting-text h3 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .setting-text p {
            font-size: 13px;
            color: rgba(255,255,255,0.5);
        }
        
        .setting-value {
            font-size: 15px;
            color: var(--primary);
            font-weight: 600;
            position: relative;
            z-index: 1;
        }
        
        .setting-arrow {
            font-size: 20px;
            color: rgba(255,255,255,0.3);
            position: relative;
            z-index: 1;
        }
        
        /* ========== NOTIFICATIONS MEJORADAS ========== */
        @keyframes notificationSlide {
            0% {
                opacity: 0;
                transform: translate(-50%, -40px);
            }
            100% {
                opacity: 1;
                transform: translate(-50%, 0);
            }
        }
        
        .notification {
            position: fixed;
            top: 90px;
            left: 50%;
            transform: translateX(-50%);
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: #fff;
            padding: 18px 30px;
            border-radius: 16px;
            z-index: 9999;
            animation: notificationSlide 0.5s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 
                0 10px 40px rgba(0,0,0,0.4), 
                0 0 30px rgba(102, 126, 234, 0.5);
            font-weight: 600;
            font-size: 15px;
            border: 1px solid rgba(255,255,255,0.2);
        }
        
        /* ========== RESPONSIVE ========== */
        @media (max-width: 480px) {
            .header {
                height: 65px;
                padding: 0 20px;
            }
            
            .header-logo {
                width: 40px;
                height: 40px;
                font-size: 20px;
            }
            
            .header-title {
                font-size: 18px;
            }
            
            .player-container {
                padding: 80px 15px 120px;
            }
            
            .album-art {
                font-size: 100px;
            }
            
            .track-title {
                font-size: 22px;
            }
            
            .control-btn {
                width: 55px;
                height: 55px;
            }
            
            .control-btn.play-pause {
                width: 75px;
                height: 75px;
            }
            
            .control-btn svg {
                width: 24px;
                height: 24px;
            }
            
            .control-btn.play-pause svg {
                width: 32px;
                height: 32px;
            }
            
            .stats-panel {
                gap: 10px;
            }
            
            .stat-card {
                padding: 20px 10px;
            }
            
            .stat-icon {
                font-size: 26px;
            }
            
            .stat-value {
                font-size: 22px;
            }
            
            .visualizer-container {
                height: 100px;
            }
        }
        
        /* ========== NOCTURNO WAVE ANIMATION ========== */
        @keyframes nocturnoDrift {
            0%   { opacity:0; transform: scale(2.5) translateZ(80px); letter-spacing: 0.6em; filter: blur(12px); }
            30%  { opacity:1; transform: scale(1.08) translateZ(10px); letter-spacing: 0.18em; filter: blur(0px); }
            70%  { opacity:1; transform: scale(1) translateZ(0px); letter-spacing: 0.12em; filter: blur(0px); }
            100% { opacity:.85; transform: scale(0.85) translateZ(-40px); letter-spacing: 0.05em; filter: blur(3px); }
        }

        .nocturno-wave {
            display: inline-block;
            font-family: 'Orbitron', 'Poppins', sans-serif;
            font-size: 28px;
            font-weight: 900;
            letter-spacing: 0.15em;
            background: linear-gradient(135deg, #fff 0%, #a78bfa 40%, #667eea 70%, #ff006e 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: nocturnoDrift 3.5s cubic-bezier(.22,1,.36,1) infinite alternate;
            text-shadow: none;
            transform-style: preserve-3d;
        }

        /* ========== UNIQUE PRO FEATURE: Waveform cursor ========== */
        @keyframes cursorWave {
            0%,100% { height:6px; }
            50% { height:22px; }
        }
        .waveform-cursor {
            position:fixed; bottom:0; left:0; right:0; height:32px;
            display:flex; align-items:flex-end; gap:2px; padding:0 0 4px 0;
            pointer-events:none; z-index:999; overflow:hidden;
        }
        .wf-bar {
            flex:1; border-radius:2px 2px 0 0;
            background: linear-gradient(180deg, rgba(102,126,234,.55), rgba(255,0,110,.4));
            animation: cursorWave ease-in-out infinite;
        }

    </style>

</head>
<body>
    <!-- Partículas de fondo mejoradas -->
    <div class="waveform-cursor" id="waveformCursor"></div>
    <div class="particle" style="width: 200px; height: 200px; top: 8%; left: 3%; animation-delay: 0s; animation-duration: 12s;"></div>
    <div class="particle" style="width: 150px; height: 150px; top: 55%; left: 82%; animation-delay: 2s; animation-duration: 14s;"></div>
    <div class="particle" style="width: 180px; height: 180px; top: 75%; left: 10%; animation-delay: 4s; animation-duration: 10s;"></div>
    <div class="particle" style="width: 120px; height: 120px; top: 25%; left: 88%; animation-delay: 1s; animation-duration: 13s;"></div>
    <div class="particle" style="width: 100px; height: 100px; top: 45%; left: 5%; animation-delay: 3s; animation-duration: 11s;"></div>
    
    <!-- Estrellas decorativas -->
    <div class="star" style="top: 15%; left: 20%; animation-delay: 0s;"></div>
    <div class="star" style="top: 25%; left: 70%; animation-delay: 0.5s;"></div>
    <div class="star" style="top: 40%; left: 30%; animation-delay: 1s;"></div>
    <div class="star" style="top: 60%; left: 85%; animation-delay: 1.5s;"></div>
    <div class="star" style="top: 80%; left: 40%; animation-delay: 2s;"></div>
    <div class="star" style="top: 70%; left: 15%; animation-delay: 2.5s;"></div>
    <div class="star" style="top: 90%; left: 75%; animation-delay: 3s;"></div>
    
    <!-- HEADER MEJORADO -->
    <div class="header">
        <div class="header-left">
            <div class="header-logo">🎵</div>
            <div>
                <div class="header-title" data-text="NOCTURNO DJ">Nocturno DJ</div>
                <div class="header-subtitle">Pro Player v7.2 ✨</div>
            </div>
        </div>
        <button class="header-button" onclick="openSettings()">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61 l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41 h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87 C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58 c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54 c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96 c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6 s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/>
            </svg>
        </button>
    </div>
    
    <!-- PLAYER PRINCIPAL -->
    <div class="player-container">
        <!-- Album Art con glow y ecualizador -->
        <div class="album-container">
            <div class="equalizer-ring" id="equalizerRing">
                <div class="eq-bar" style="--i:1"></div>
                <div class="eq-bar" style="--i:2"></div>
                <div class="eq-bar" style="--i:3"></div>
                <div class="eq-bar" style="--i:4"></div>
                <div class="eq-bar" style="--i:5"></div>
                <div class="eq-bar" style="--i:6"></div>
                <div class="eq-bar" style="--i:7"></div>
                <div class="eq-bar" style="--i:8"></div>
                <div class="eq-bar" style="--i:9"></div>
                <div class="eq-bar" style="--i:10"></div>
                <div class="eq-bar" style="--i:11"></div>
                <div class="eq-bar" style="--i:12"></div>
            </div>
            <div class="album-art" id="albumArtContainer">
                <div id="albumEmoji"><span class="nocturno-wave">NOCTURNO</span></div>
            </div>
            <div class="album-glow"></div>
        </div>
        
        <!-- Track Info -->
        <div class="track-info">
            <div class="track-title" id="trackTitle">Cargando...</div>
            <div class="track-artist" id="trackArtist">Nocturno DJ</div>
        </div>
        
        <!-- Progress Bar -->
        <div class="progress-container">
            <div class="progress-bar" onclick="seekTo(event)">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            <div class="time-info">
                <span id="currentTime">0:00</span>
                <span id="totalTime">0:00</span>
            </div>
        </div>
        
        <!-- Playback Controls con SVG -->
        <div class="playback-controls">
            <!-- Botón Previous -->
            <button class="control-btn" onclick="previousTrack()" title="Anterior">
                <svg viewBox="0 0 24 24">
                    <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>
                </svg>
            </button>
            
            <!-- Botón Play/Pause -->
            <button class="control-btn play-pause" onclick="togglePlay()" id="playPauseBtn" title="Reproducir/Pausar">
                <svg viewBox="0 0 24 24" id="playIcon">
                    <path d="M8 5v14l11-7z"/>
                </svg>
                <svg viewBox="0 0 24 24" id="pauseIcon" style="display:none;">
                    <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
                </svg>
            </button>
            
            <!-- Botón Next -->
            <button class="control-btn" onclick="nextTrack()" title="Siguiente">
                <svg viewBox="0 0 24 24">
                    <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>
                </svg>
            </button>
        </div>
        
        <!-- Control de Volumen -->
        <div class="volume-control">
            <svg class="volume-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
            <input type="range" class="volume-slider" id="volumeSlider" min="0" max="100" value="100" oninput="changeVolume(this.value)">
            <span class="volume-value" id="volumeValue">100%</span>
        </div>
        
        <!-- PANEL DE ESTADÍSTICAS -->
        <div class="stats-panel">
            <div class="stat-card">
                <span class="stat-icon">🎵</span>
                <span class="stat-value" id="statTotalSongs">0</span>
                <span class="stat-label">Canciones</span>
            </div>
            <div class="stat-card">
                <span class="stat-icon">📻</span>
                <span class="stat-value" id="statListeners">0</span>
                <span class="stat-label">Oyentes</span>
            </div>
            <div class="stat-card">
                <span class="stat-icon">📝</span>
                <span class="stat-value" id="statQueue">0</span>
                <span class="stat-label">En Cola</span>
            </div>
        </div>
        
        <!-- VISUALIZADOR DE AUDIO -->
        <div class="visualizer-container">
            <canvas id="audioVisualizer"></canvas>
        </div>
        
        <!-- CONTROLES AVANZADOS -->
        <div class="advanced-controls">
            <button class="adv-btn" onclick="toggleLoop()" id="loopBtn" title="Activar/Desactivar Loop">
                <svg viewBox="0 0 24 24">
                    <path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/>
                </svg>
                <span>Loop</span>
            </button>
            
            <button class="adv-btn" onclick="toggleShuffle()" id="shuffleBtn" title="Activar/Desactivar Shuffle">
                <svg viewBox="0 0 24 24">
                    <path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/>
                </svg>
                <span>Shuffle</span>
            </button>
            
            <button class="adv-btn" onclick="stopMusic()" id="stopBtn" title="Detener reproducción">
                <svg viewBox="0 0 24 24">
                    <path d="M6 6h12v12H6z"/>
                </svg>
                <span>Stop</span>
            </button>
            
            <button class="adv-btn" onclick="downloadCurrent()" title="Descargar canción actual">
                <svg viewBox="0 0 24 24">
                    <path d="M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2z"/>
                </svg>
                <span>Descargar</span>
            </button>
        </div>
        
        <!-- REPRODUCTOR DE AUDIO OCULTO -->
        <audio id="radioPlayer" preload="none" style="display: none;">
            <source src="/stream" type="audio/mpeg">
        </audio>
    </div>
    
    <!-- MENÚ DE CONFIGURACIÓN -->
    <div class="settings-overlay" id="settingsOverlay" onclick="closeSettingsOnOverlay(event)">
        <div class="settings-panel" onclick="event.stopPropagation()">
            <div class="settings-header">
                <h2 class="settings-title">⚙️ Configuración</h2>
                <button class="close-settings" onclick="closeSettings()">✕</button>
            </div>
            
            <!-- Sección: Stream -->
            <div class="settings-section">
                <div class="section-title">📡 Stream de Radio</div>
                
                <button class="setting-button" onclick="showStreamLink()">
                    <div class="setting-left">
                        <div class="setting-icon">📡</div>
                        <div class="setting-text">
                            <h3>Link del Stream</h3>
                            <p>Copiar URL de la radio</p>
                        </div>
                    </div>
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="rgba(255,255,255,.5)" style="position:relative;z-index:1;flex-shrink:0;"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
                </button>
            </div>
            
            <!-- Sección: Configuración de Audio -->
            <div class="settings-section">
                <div class="section-title">🎚️ Configuración de Audio</div>
                
                <button class="setting-button" onclick="let s=prompt('Segundos de Crossfade:', '20'); if(s!==null) updateCrossfade(s);">
                    <div class="setting-left">
                        <div class="setting-icon">🎚️</div>
                        <div class="setting-text">
                            <h3>Crossfade</h3>
                            <p>Tiempo de mezcla entre canciones</p>
                        </div>
                    </div>
                    <span class="setting-value" id="crossfadeDisplay">20s</span>
                </button>
            </div>
            
            <!-- Sección: Gestión de Música -->
            <div class="settings-section">
                <div class="section-title">🎵 Gestión de Música</div>

                <!-- File upload -->
                <div class="setting-button" style="flex-direction:column;align-items:stretch;gap:10px;cursor:default;">
                    <div class="setting-left">
                        <div class="setting-icon">📁</div>
                        <div class="setting-text">
                            <h3>Subir Archivos</h3>
                            <p>MP3, WAV, FLAC, OGG, M4A…</p>
                        </div>
                    </div>
                    <div style="display:flex;gap:8px;width:100%;">
                        <input id="musicFileInput" type="file" multiple accept=".mp3,.wav,.flac,.ogg,.m4a,.aac,.opus"
                            style="flex:1;padding:8px;border-radius:10px;border:1px solid rgba(102,126,234,0.4);
                                   background:rgba(255,255,255,0.07);color:#fff;font-size:13px;">
                        <button onclick="uploadMusicFiles()"
                            style="padding:10px 18px;border-radius:10px;border:none;
                                   background:linear-gradient(135deg,#10b981,#059669);
                                   color:#fff;font-weight:600;cursor:pointer;white-space:nowrap;">
                            ⬆ Subir
                        </button>
                    </div>
                    <div id="uploadStatus" style="font-size:13px;color:rgba(255,255,255,0.7);min-height:18px;padding:0 2px;"></div>
                </div>

                <button class="setting-button" onclick="reloadPlaylist()">
                    <div class="setting-left">
                        <div class="setting-icon">🔄</div>
                        <div class="setting-text">
                            <h3>Recargar Playlist</h3>
                            <p>Actualizar la biblioteca de música</p>
                        </div>
                    </div>
                    <span class="setting-arrow">›</span>
                </button>
            </div>
            
            <!-- Sección: Sistema -->
            <div class="settings-section">
                <div class="section-title">ℹ️ Información del Sistema</div>
                
                <div class="setting-button" style="cursor: default;">
                    <div class="setting-left">
                        <div class="setting-icon">⏱️</div>
                        <div class="setting-text">
                            <h3>Uptime</h3>
                            <p>Tiempo activo del sistema</p>
                        </div>
                    </div>
                    <span class="setting-value" id="uptimeDisplay">-</span>
                </div>
                
                <button class="setting-button" onclick="logout()">
                    <div class="setting-left">
                        <div class="setting-icon">🚪</div>
                        <div class="setting-text">
                            <h3>Cerrar Sesión</h3>
                            <p>Salir del panel de control</p>
                        </div>
                    </div>
                    <span class="setting-arrow">›</span>
                </button>
            </div>
        </div>
    </div>
    
    <script>
        // ========== VARIABLES GLOBALES ==========
        let isPlaying = false;
        let currentTrackName = '';
        let audioElement = null;
        let currentVolume = 100;
        
        // ========== INICIALIZACIÓN DEL AUDIO ==========
        function initAudioPlayer() {
            audioElement = document.getElementById('radioPlayer');
            
            if (audioElement) {
                audioElement.volume = currentVolume / 100;
                
                audioElement.addEventListener('play', () => {
                    isPlaying = true;
                    updatePlayButton();
                });
                
                audioElement.addEventListener('pause', () => {
                    isPlaying = false;
                    updatePlayButton();
                });
                
                audioElement.addEventListener('ended', () => {
                    isPlaying = false;
                    updatePlayButton();
                });
                
                audioElement.addEventListener('error', (e) => {
                    console.error('Error en audio:', e);
                    isPlaying = false;
                    updatePlayButton();
                });
            }
        }
        
        // ========== CONTROLES DE REPRODUCCIÓN ==========
        function togglePlay() {
            if (!audioElement) {
                audioElement = document.getElementById('radioPlayer');
            }
            
            if (audioElement) {
                if (isPlaying) {
                    audioElement.pause();
                    showNotification('⏸️ Pausado', 'info');
                } else {
                    audioElement.play().then(() => {
                        showNotification('▶️ Reproduciendo', 'success');
                    }).catch(e => {
                        console.error('Error al reproducir:', e);
                        showNotification('❌ Error al reproducir', 'error');
                    });
                }
            }
        }
        
        function updatePlayButton() {
            const playIcon = document.getElementById('playIcon');
            const pauseIcon = document.getElementById('pauseIcon');
            const playBtn = document.getElementById('playPauseBtn');
            const albumArt = document.getElementById('albumArtContainer');
            
            if (isPlaying) {
                playIcon.style.display = 'none';
                pauseIcon.style.display = 'block';
                playBtn.classList.add('playing');
                albumArt.classList.add('playing');
            } else {
                playIcon.style.display = 'block';
                pauseIcon.style.display = 'none';
                playBtn.classList.remove('playing');
                albumArt.classList.remove('playing');
            }
        }
        
        function previousTrack() {
            showNotification('⏮️ Canción anterior', 'info');
            fetch('/api/previous', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        triggerTrackChangeEffect();
                        setTimeout(updateTrackInfo, 500);
                    }
                })
                .catch(e => showNotification('❌ Error al cambiar canción', 'error'));
        }
        
        function nextTrack() {
            showNotification('⏭️ Siguiente canción', 'info');
            fetch('/api/next', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        triggerTrackChangeEffect();
                        setTimeout(updateTrackInfo, 500);
                    }
                })
                .catch(e => showNotification('❌ Error al cambiar canción', 'error'));
        }
        
        function stopMusic() {
            if (audioElement) {
                audioElement.pause();
                audioElement.currentTime = 0;
                isPlaying = false;
                updatePlayButton();
                showNotification('⏹️ Reproducción detenida', 'info');
            }
        }
        
        // ========== CONTROL DE VOLUMEN ==========
        function changeVolume(value) {
            currentVolume = parseInt(value);
            document.getElementById('volumeValue').textContent = currentVolume + '%';
            
            if (audioElement) {
                audioElement.volume = currentVolume / 100;
            }
        }
        
        // ========== SEEK EN LA BARRA DE PROGRESO ==========
        function seekTo(event) {
            const progressBar = event.currentTarget;
            const rect = progressBar.getBoundingClientRect();
            const clickX = event.clientX - rect.left;
            const percentage = (clickX / rect.width) * 100;
            
            // Esta función necesitaría implementación en el backend
            console.log('Seek to:', percentage + '%');
            showNotification('Función de seek - implementar en backend', 'info');
        }
        
        // ========== EFECTOS DE CAMBIO DE CANCIÓN — NOCTURNO ANIMADO ==========
        function triggerTrackChangeEffect() {
            const albumArt = document.getElementById('albumArtContainer');
            const emoji = document.getElementById('albumEmoji');
            
            albumArt.classList.add('track-change');
            
            // Cambiar a texto NOCTURNO animado
            setTimeout(() => {
                emoji.innerHTML = '<span class="nocturno-wave">NOCTURNO</span>';
                emoji.style.transform = 'scale(1) rotate(0deg)';
                emoji.style.opacity = '1';
            }, 500);
            
            setTimeout(() => {
                albumArt.classList.remove('track-change');
            }, 1000);
        }
        
        // ========== ACTUALIZAR INFO DEL TRACK ==========
        let lastTrackName = '';
        
        function updateTrackInfo() {
            fetch('/api/track_info')
                .then(r => r.json())
                .then(data => {
                    if (data.success && data.track) {
                        const track = data.track;
                        
                        if (lastTrackName && lastTrackName !== track.name) {
                            triggerTrackChangeEffect();
                        }
                        lastTrackName = track.name;
                        
                        document.getElementById('trackTitle').textContent = track.name || 'Sin reproducción';
                        document.getElementById('trackArtist').textContent = '@' + (track.username || 'System');
                        
                        const progressBar = document.getElementById('progressFill');
                        if (progressBar) {
                            progressBar.style.width = track.progress + '%';
                        }
                        
                        document.getElementById('currentTime').textContent = formatTime(track.elapsed);
                        document.getElementById('totalTime').textContent = formatTime(track.duration);
                        
                        const albumArt = document.getElementById('albumArtContainer');
                        if (track.duration > 0 && track.elapsed > 0 && isPlaying) {
                            albumArt.classList.add('playing');
                        } else if (!isPlaying) {
                            albumArt.classList.remove('playing');
                        }
                    }
                })
                .catch(e => console.error('Error updating track info:', e));
        }
        
        // ========== ACTUALIZAR ESTADÍSTICAS ==========
        function updateStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('statTotalSongs').textContent = data.stats.total_songs || 0;
                        document.getElementById('statListeners').textContent = data.stats.listeners || 0;
                        document.getElementById('statQueue').textContent = data.stats.current_track ? 1 : 0;
                        document.getElementById('uptimeDisplay').textContent = data.stats.uptime || '-';
                    }
                })
                .catch(e => console.error('Error updating stats:', e));
        }
        
        // ========== ACTUALIZAR STATUS GENERAL ==========
        function updateStatus() {
            fetch('/api/radio_status')
                .then(r => r.json())
                .then(data => {
                    const crossfade = data.crossfade || 0;
                    document.getElementById('crossfadeDisplay').textContent = crossfade + 's';
                })
                .catch(e => console.error('Error updating status:', e));
        }
        
        // ========== CONTROLES AVANZADOS ==========
        function toggleShuffle() {
            fetch('/api/shuffle', { method: 'POST', headers: {'Content-Type': 'application/json'} })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        const shuffleBtn = document.getElementById('shuffleBtn');
                        if (data.shuffle) {
                            shuffleBtn.classList.add('active');
                            showNotification('🔀 Shuffle activado', 'success');
                        } else {
                            shuffleBtn.classList.remove('active');
                            showNotification('🔀 Shuffle desactivado', 'info');
                        }
                    }
                })
                .catch(e => showNotification('❌ Error', 'error'));
        }
        
        function toggleLoop() {
            fetch('/api/loop', { method: 'POST', headers: {'Content-Type': 'application/json'} })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        const loopBtn = document.getElementById('loopBtn');
                        if (data.loop) {
                            loopBtn.classList.add('active');
                            showNotification('🔁 Loop activado', 'success');
                        } else {
                            loopBtn.classList.remove('active');
                            showNotification('🔁 Loop desactivado', 'info');
                        }
                    }
                })
                .catch(e => showNotification('❌ Error', 'error'));
        }
        
        function downloadCurrent() {
            fetch('/api/track_info')
                .then(r => r.json())
                .then(data => {
                    if (data.success && data.track && data.track.name !== 'No hay música') {
                        const trackName = data.track.name;
                        showNotification(`💾 Descargando: ${trackName}...`, 'info');
                        window.location.href = `/api/download_track/${encodeURIComponent(trackName)}`;
                    } else {
                        showNotification('❌ No hay música reproduciéndose', 'error');
                    }
                })
                .catch(e => showNotification('❌ Error', 'error'));
        }
        
        function reloadPlaylist() {
            showNotification('🔄 Recargando playlist...', 'info');
            fetch('/api/reload_playlist', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showNotification(`✅ ${data.total_songs} canciones cargadas`, 'success');
                        updateStatus();
                        closeSettings();
                    }
                })
                .catch(e => showNotification('❌ Error al recargar', 'error'));
        }

        // ── File upload ──────────────────────────────────────────────────────
        function uploadMusicFiles() {
            const fileInput = document.getElementById('musicFileInput');
            const status = document.getElementById('uploadStatus');
            if (!fileInput || !fileInput.files.length) {
                showNotification('📂 Selecciona archivos primero', 'warning'); return;
            }
            const form = new FormData();
            for (const f of fileInput.files) form.append('music', f);
            status.textContent = `⬆️ Subiendo ${fileInput.files.length} archivo(s)…`;

            fetch('/upload_music', { method: 'POST', body: form })
                .then(r => r.json())
                .then(data => {
                    status.textContent = data.message || (data.success ? '✅ Listo' : '❌ Error');
                    if (data.success) {
                        showNotification(data.message, 'success');
                        fileInput.value = '';
                        updateStatus();
                    } else {
                        showNotification(data.message || '❌ Error al subir', 'error');
                    }
                })
                .catch(e => { status.textContent = '❌ Error de red'; });
        }
        
        // ========== VISUALIZADOR DE AUDIO ULTRA MEJORADO ==========
        const canvas = document.getElementById('audioVisualizer');
        const ctx = canvas ? canvas.getContext('2d') : null;
        
        if (canvas && ctx) {
            canvas.width = canvas.offsetWidth;
            canvas.height = 120;
            
            let bars = 60;
            let barHeights = new Array(bars).fill(0);
            let barVelocities = new Array(bars).fill(0);
            let barTargets = new Array(bars).fill(0);
            
            function drawVisualizer() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                
                const barWidth = canvas.width / bars;
                const maxHeight = 100;
                
                for (let i = 0; i < bars; i++) {
                    // Física mejorada
                    const intensity = isPlaying ? 1 : 0.3;
                    barTargets[i] = (Math.random() * maxHeight * 0.7 * intensity) + (maxHeight * 0.3 * intensity);
                    
                    barVelocities[i] += (barTargets[i] - barHeights[i]) * 0.08;
                    barVelocities[i] *= 0.82;
                    barHeights[i] += barVelocities[i];
                    
                    const height = Math.max(12, Math.min(maxHeight, barHeights[i]));
                    const x = i * barWidth;
                    const y = canvas.height - height;
                    
                    // Gradient tri-color mejorado
                    const gradient = ctx.createLinearGradient(0, y, 0, canvas.height);
                    gradient.addColorStop(0, '#ff006e');
                    gradient.addColorStop(0.25, '#667eea');
                    gradient.addColorStop(0.5, '#764ba2');
                    gradient.addColorStop(0.75, '#00fff9');
                    gradient.addColorStop(1, '#667eea');
                    
                    // Sombra de neón más intensa
                    ctx.shadowBlur = 20;
                    ctx.shadowColor = i % 2 === 0 ? 'rgba(102, 126, 234, 0.8)' : 'rgba(255, 0, 110, 0.8)';
                    
                    ctx.fillStyle = gradient;
                    ctx.fillRect(x + 1, y, barWidth - 2, height);
                    
                    // Barra de reflejo mejorada
                    const reflectionGradient = ctx.createLinearGradient(0, canvas.height, 0, canvas.height + height * 0.3);
                    reflectionGradient.addColorStop(0, i % 2 === 0 ? 'rgba(102, 126, 234, 0.3)' : 'rgba(255, 0, 110, 0.3)');
                    reflectionGradient.addColorStop(1, 'rgba(102, 126, 234, 0)');
                    
                    ctx.shadowBlur = 10;
                    ctx.fillStyle = reflectionGradient;
                    ctx.fillRect(x + 1, canvas.height, barWidth - 2, height * 0.15);
                }
                
                requestAnimationFrame(drawVisualizer);
            }
            
            drawVisualizer();
        }
        
        // ========== SETTINGS MODAL ==========
        function openSettings() {
            document.getElementById('settingsOverlay').classList.add('active');
        }
        
        function closeSettings() {
            document.getElementById('settingsOverlay').classList.remove('active');
        }
        
        function closeSettingsOnOverlay(event) {
            if (event.target === document.getElementById('settingsOverlay')) {
                closeSettings();
            }
        }
        
        function showStreamLink() {
            const streamUrl = window.location.origin + '/stream';
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(streamUrl).then(() => {
                    showNotification('Enlace copiado al portapapeles', 'success');
                }).catch(() => {
                    // fallback
                    const ta = document.createElement('textarea');
                    ta.value = streamUrl; ta.style.position='fixed'; ta.style.opacity='0';
                    document.body.appendChild(ta); ta.select();
                    document.execCommand('copy'); document.body.removeChild(ta);
                    showNotification('Enlace copiado', 'success');
                });
            } else {
                const ta = document.createElement('textarea');
                ta.value = streamUrl; ta.style.position='fixed'; ta.style.opacity='0';
                document.body.appendChild(ta); ta.select();
                document.execCommand('copy'); document.body.removeChild(ta);
                showNotification('Enlace copiado: ' + streamUrl, 'success');
            }
        }
        
        function updateCrossfade(seconds) {
            fetch('/update_crossfade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ seconds: parseInt(seconds) })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('crossfadeDisplay').innerText = data.seconds + 's';
                    showNotification('✅ Crossfade actualizado', 'success');
                } else {
                    showNotification('❌ Error: ' + data.message, 'error');
                }
            });
        }
        
        function logout() {
            if (confirm('¿Cerrar sesión?')) {
                window.location.href = '/logout';
            }
        }
        
        // ========== NOTIFICATIONS ==========
        function showNotification(message, type = 'info') {
            const notification = document.createElement('div');
            notification.className = 'notification';
            notification.textContent = message;
            
            document.body.appendChild(notification);
            
            setTimeout(() => {
                notification.style.opacity = '0';
                notification.style.transform = 'translate(-50%, -20px)';
                setTimeout(() => notification.remove(), 300);
            }, 3000);
        }
        
        // ========== UTILIDADES ==========
        function formatTime(seconds) {
            if (!seconds || seconds < 0) return '0:00';
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        }
        
        // ========== INICIALIZACIÓN ==========
        window.addEventListener('DOMContentLoaded', () => {
            initAudioPlayer();
            updateStatus();
            updateTrackInfo();
            updateStats();
            createDynamicParticles();
            initWaveformCursor();
            
            // Actualización periódica
            setInterval(updateTrackInfo, 1000);
            setInterval(updateStats, 3000);
            setInterval(updateStatus, 5000);
        });
        
        // ========== WAVEFORM CURSOR — ELEMENTO ÚNICO ==========
        function initWaveformCursor() {
            const container = document.getElementById('waveformCursor');
            if (!container) return;
            const barCount = Math.floor(window.innerWidth / 6);
            const delays = [];
            const durations = [];
            for (let i = 0; i < barCount; i++) {
                const b = document.createElement('div');
                b.className = 'wf-bar';
                const delay = (Math.random() * 1.2).toFixed(2) + 's';
                const dur = (.35 + Math.random() * .7).toFixed(2) + 's';
                b.style.animationDelay = delay;
                b.style.animationDuration = dur;
                container.appendChild(b);
            }
        }
        
        // ========== CREAR PARTÍCULAS DINÁMICAS ==========
        function createDynamicParticles() {
            const particleCount = 20;
            const body = document.body;
            
            for (let i = 0; i < particleCount; i++) {
                const particle = document.createElement('div');
                particle.className = 'particle';
                
                // Propiedades aleatorias
                const size = Math.random() * 100 + 50;
                const x = Math.random() * window.innerWidth;
                const y = Math.random() * window.innerHeight;
                const delay = Math.random() * 10;
                const duration = Math.random() * 15 + 10;
                
                particle.style.width = size + 'px';
                particle.style.height = size + 'px';
                particle.style.left = x + 'px';
                particle.style.top = y + 'px';
                particle.style.animationDelay = delay + 's';
                particle.style.animationDuration = duration + 's';
                
                body.appendChild(particle);
            }
            
            // Añadir estrellas adicionales
            const starCount = 30;
            for (let i = 0; i < starCount; i++) {
                const star = document.createElement('div');
                star.className = 'star';
                
                const x = Math.random() * window.innerWidth;
                const y = Math.random() * window.innerHeight;
                const delay = Math.random() * 3;
                
                star.style.left = x + 'px';
                star.style.top = y + 'px';
                star.style.animationDelay = delay + 's';
                
                body.appendChild(star);
            }
        }
        
        // ========== RESPONSIVE - Redimensionar canvas ==========
        window.addEventListener('resize', () => {
            if (canvas) {
                canvas.width = canvas.offsetWidth;
            }
        });
    </script>
</body>
</html>
"""

# ================== RUTAS ==================
@app.route("/")
@login_required
def index():
    return render_template_string(MAIN_TEMPLATE)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == PASSWORD:
            session['logged_in'] = True
            session['login_time'] = datetime.now().isoformat()
            get_login_logger().info(f"Login exitoso desde {request.remote_addr}")
            return redirect(url_for('index'))
        else:
            get_login_logger().warning(f"Intento de login fallido desde {request.remote_addr}")
            return render_template_string(LOGIN_TEMPLATE, error="Contraseña incorrecta")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    get_login_logger().info(f"Sesión cerrada desde {request.remote_addr}")
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route("/stream")
def stream():
    """Endpoint de streaming de radio"""
    pass  # log suprimido
    
    def generate():
        client_queue = Queue()
        radio.clients.append(client_queue)
        
        try:
            # Enviar buffer inicial
            if radio.pre_buffer:
                yield bytes(radio.pre_buffer)
            
            # Streaming continuo
            while True:
                chunk = client_queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if client_queue in radio.clients:
                radio.clients.remove(client_queue)
                pass  # log suprimido
    
    return Response(generate(), mimetype="audio/mpeg",
                   headers={
                       'Cache-Control': 'no-cache, no-store, must-revalidate',
                       'Pragma': 'no-cache',
                       'Expires': '0'
                   })

@app.route("/api/radio_status")
def radio_status():
    try:
        jingles = [f for f in os.listdir(JINGLES_FOLDER) if allowed_file(f)]
        
        status = {
            "now_playing": {
                "title": getattr(radio, 'current_track_title', radio.current_track.get('name', 'Sin reproducción') if radio.current_track else 'Sin reproducción'),
                "artist": "Nocturno DJ"
            },
            "playlist": {
                "total_songs": len(radio.queue_local) if hasattr(radio, 'queue_local') else 0,
                "current_index": getattr(radio, 'current_index', 0)
            },
            "jingles": {
                "count": len(jingles),
                "files": jingles
            },
            "crossfade": getattr(radio, 'crossfade', 10)
        }
        return jsonify(status)
    except Exception as e:
        print(f"[API] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/get_crossfade")
def get_crossfade():
    try:
        return jsonify({"crossfade": getattr(radio, 'crossfade', 10)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/set_crossfade", methods=["POST"])
@login_required
def set_crossfade():
    try:
        data = request.get_json()
        crossfade = int(data.get('crossfade', 10))
        
        if crossfade < 0 or crossfade > 30:
            return jsonify({"success": False, "message": "Valor debe estar entre 0 y 30"}), 400
        
        # Actualizar en la radio
        radio.crossfade = crossfade
        
        # Actualizar en config.json
        with open("config.json", "r") as f:
            config_data = json.load(f)
        
        config_data['crossfade'] = crossfade
        
        with open("config.json", "w") as f:
            json.dump(config_data, f, indent=2)
        
        print(f"[WEB] 🎚️ Crossfade actualizado a {crossfade}s")
        return jsonify({"success": True, "message": f"Crossfade configurado a {crossfade}s"})
        
    except Exception as e:
        print(f"[WEB] ❌ Error set_crossfade: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/upload_music", methods=["POST"])
@login_required
def upload_music():
    """Sube música a la carpeta local music/."""
    try:
        from radio import MUSIC_FOLDER as MUSIC_DIR
        if not os.path.exists(MUSIC_DIR):
            os.makedirs(MUSIC_DIR)

        files = request.files.getlist("music")
        if not files or files[0].filename == '':
            return jsonify({"success": False, "message": "No se seleccionaron archivos"}), 400

        uploaded_count = 0
        errors = []

        for file in files:
            if file and file.filename:
                if not allowed_file(file.filename):
                    errors.append(f"{file.filename}: Formato no permitido")
                    continue
                try:
                    filename = secure_filename(file.filename)
                    dest_path = os.path.join(MUSIC_DIR, filename)

                    if os.path.exists(dest_path):
                        errors.append(f"{file.filename}: Ya existe en la librería")
                        continue

                    file.save(dest_path)
                    file_size = os.path.getsize(dest_path)

                    if file_size > MAX_FILE_SIZE:
                        errors.append(f"{file.filename}: Archivo muy grande (máx {MAX_FILE_SIZE//(1024*1024)}MB)")
                        os.remove(dest_path)
                        continue

                    uploaded_count += 1
                    print(f"[UPLOAD] ✅ Guardado: {filename} ({file_size//(1024*1024)}MB)")
                except Exception as e:
                    errors.append(f"{file.filename}: {str(e)}")
                    print(f"[UPLOAD] ❌ Error: {e}")

        if uploaded_count > 0:
            radio.load_local_music()

        total_songs = len(radio.queue_local) if hasattr(radio, 'queue_local') else 0

        if uploaded_count > 0:
            msg = f"✅ {uploaded_count} archivo(s) guardado(s)"
            if errors:
                msg += f" ({len(errors)} con errores)"
            return jsonify({"success": True, "message": msg, "uploaded": uploaded_count,
                            "total_songs": total_songs, "errors": errors or None})
        else:
            return jsonify({"success": False, "message": "❌ No se pudo guardar ningún archivo",
                            "errors": errors}), 400

    except Exception as e:
        print(f"[UPLOAD] ❌ Error crítico: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

@app.route("/upload_jingle", methods=["POST"])
@login_required
def upload_jingle():
    try:
        files = request.files.getlist("jingle")
        
        if not files or files[0].filename == '':
            return jsonify({"success": False, "message": "No se seleccionaron archivos"}), 400
        
        if len(files) > 5:
            return jsonify({"success": False, "message": "Máximo 5 jingles"}), 400
        
        current_jingles = len([f for f in os.listdir(JINGLES_FOLDER) if allowed_file(f)])
        
        if current_jingles + len(files) > 5:
            return jsonify({"success": False, "message": f"Solo puedes tener 5 jingles en total (tienes {current_jingles})"}), 400
        
        uploaded_count = 0
        
        for file in files:
            if file and file.filename:
                if not allowed_file(file.filename):
                    continue
                
                filename = secure_filename(file.filename)
                filepath = os.path.join(JINGLES_FOLDER, filename)
                file.save(filepath)
                uploaded_count += 1
        
        if uploaded_count > 0:
            if hasattr(radio, 'load_jingles'):
                radio.load_jingles()
            
            return jsonify({
                "success": True,
                "message": f"{uploaded_count} jingle(s) agregado(s)"
            })
        else:
            return jsonify({"success": False, "message": "No se pudo subir ningún jingle"}), 400
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/previous_track", methods=["POST"])
def previous_track():
    try:
        if hasattr(radio, 'skip_to_previous'):
            radio.skip_to_previous()
            pass  # log suprimido
            return jsonify({"success": True, "message": "Canción anterior"})
        else:
            return jsonify({"success": False, "message": "Función no disponible"}), 400
    except Exception as e:
        logger.error(f"Error en previous_track: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/next_track", methods=["POST"])
def next_track():
    try:
        if hasattr(radio, 'skip_to_next'):
            radio.skip_to_next()
            pass  # log suprimido
            return jsonify({"success": True, "message": "Siguiente canción"})
        else:
            return jsonify({"success": False, "message": "Función no disponible"}), 400
    except Exception as e:
        logger.error(f"Error en next_track: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/reload_playlist", methods=["POST"])
def reload_playlist():
    try:
        if hasattr(radio, 'load_local_music'):
            radio.load_local_music()
            total_songs = len(radio.queue_local) if hasattr(radio, 'queue_local') else 0
            pass  # log suprimido
            return jsonify({
                "success": True, 
                "message": "Playlist recargada",
                "total_songs": total_songs
            })
        else:
            return jsonify({"success": False, "message": "Función no disponible"}), 400
    except Exception as e:
        logger.error(f"Error en reload_playlist: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/track_info")
def track_info():
    """Obtiene información detallada del track actual con progreso"""
    try:
        if radio.current_track:
            elapsed = int(time.time() - radio.track_start_time) if radio.track_start_time > 0 else 0
            duration = radio.current_duration if radio.current_duration > 0 else 1
            
            return jsonify({
                "success": True,
                "track": {
                    "name": radio.current_track.get('name', 'Unknown'),
                    "username": radio.current_track.get('username', 'System'),
                    "elapsed": elapsed,
                    "duration": duration,
                    "progress": min(100, (elapsed / duration * 100)) if duration > 0 else 0,
                    "formatted_elapsed": format_duration(elapsed),
                    "formatted_duration": format_duration(duration)
                }
            })
        else:
            return jsonify({
                "success": False, 
                "message": "No track playing",
                "track": {
                    "name": "No hay música",
                    "username": "System",
                    "elapsed": 0,
                    "duration": 0,
                    "progress": 0,
                    "formatted_elapsed": "00:00",
                    "formatted_duration": "00:00"
                }
            })
    except Exception as e:
        logger.error(f"Error en track_info: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/health")
def health_check():
    """Endpoint de health check para monitoreo"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime": get_radio_uptime(),
        "version": "7.0",
        "radio_active": radio_thread.is_alive()
    })

@app.route("/api/system_info")
@login_required
def system_info():
    """Información completa del sistema"""
    try:
        from radio import MUSIC_FOLDER as MUSIC_DIR
        return jsonify({
            "success": True,
            "system": {
                "version": "7.0",
                "uptime": get_radio_uptime(),
            },
            "radio": {
                "total_songs": len(radio.queue_local) if hasattr(radio, 'queue_local') else 0,
                "queue_size": radio.queue_requests.qsize() if hasattr(radio, 'queue_requests') else 0,
                "listeners": len(radio.clients) if hasattr(radio, 'clients') else 0,
                "current_track": radio.current_track.get('name') if radio.current_track else None,
                "paused": radio.paused if hasattr(radio, 'paused') else False,
            },
            "storage": {
                "music_count": len([f for f in os.listdir(MUSIC_DIR) if allowed_file(f)]) if os.path.exists(MUSIC_DIR) else 0,
                "jingles_count": len([f for f in os.listdir(JINGLES_FOLDER) if allowed_file(f)]) if os.path.exists(JINGLES_FOLDER) else 0,
            }
        })
    except Exception as e:
        logger.error(f"Error en system_info: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/playlist")
@login_required
def get_playlist():
    """Obtiene la playlist completa"""
    try:
        if hasattr(radio, 'queue_local'):
            playlist = [
                {
                    "name": track.get('name', 'Unknown'),
                    "username": track.get('username', 'System'),
                    "index": idx
                }
                for idx, track in enumerate(radio.queue_local)
            ]
            return jsonify({
                "success": True,
                "playlist": playlist,
                "total": len(playlist)
            })
        else:
            return jsonify({"success": False, "message": "Playlist no disponible"}), 400
    except Exception as e:
        logger.error(f"Error en get_playlist: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/logs")
@login_required
def get_logs():
    """Obtiene los últimos logs del sistema"""
    try:
        log_file = os.path.join(LOGS_FOLDER, f"nocturno_{datetime.now().strftime('%Y%m%d')}.log")
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-100:]  # Últimas 100 líneas
                return jsonify({
                    "success": True,
                    "logs": last_lines,
                    "total_lines": len(lines)
                })
        else:
            return jsonify({
                "success": True,
                "logs": [],
                "message": "No hay logs disponibles hoy"
            })
    except Exception as e:
        logger.error(f"Error en get_logs: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/stats")
def get_stats():
    """Obtiene estadísticas del sistema en tiempo real"""
    try:
        return jsonify({
            "success": True,
            "stats": {
                "total_songs": len(radio.queue_local) if hasattr(radio, 'queue_local') else 0,
                "queue_size": radio.queue_requests.qsize() if hasattr(radio, 'queue_requests') else 0,
                "listeners": len(radio.clients) if hasattr(radio, 'clients') else 0,
                "current_track": radio.current_track.get('name') if radio.current_track else None,
                "crossfade": radio.crossfade if hasattr(radio, 'crossfade') else 10,
                "paused": radio.paused if hasattr(radio, 'paused') else False,
                "uptime": get_radio_uptime(),
                "shuffle_mode": radio.shuffle_mode if hasattr(radio, 'shuffle_mode') else False,
                "loop_mode": radio.loop_mode if hasattr(radio, 'loop_mode') else False
            }
        })
    except Exception as e:
        logger.error(f"Error en get_stats: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/download_track/<path:track_name>")
@login_required
def download_track(track_name):
    """Descarga una canción desde la carpeta local music/."""
    try:
        from radio import MUSIC_FOLDER as MUSIC_DIR
        safe_name = secure_filename(track_name)
        file_path = os.path.join(MUSIC_DIR, safe_name)

        if not os.path.exists(file_path):
            return jsonify({"success": False, "message": "Archivo no encontrado"}), 404

        with open(file_path, "rb") as f:
            data = f.read()

        return Response(
            data,
            mimetype="audio/mpeg",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "Content-Type": "audio/mpeg",
            },
        )
    except Exception as e:
        logger.error(f"Error descargando {track_name}: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/pause", methods=["POST"])
@login_required
def pause_playback():
    """Pausa/reanuda la reproducción"""
    try:
        if hasattr(radio, 'paused'):
            radio.paused = not radio.paused
            status = "pausada" if radio.paused else "reanudada"
            pass  # log suprimido
            return jsonify({
                "success": True, 
                "message": f"Música {status}",
                "paused": radio.paused
            })
        else:
            return jsonify({"success": False, "message": "Función no disponible"}), 400
    except Exception as e:
        logger.error(f"Error en pause: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/shuffle", methods=["POST"])
@login_required
def shuffle_playlist():
    """Activa/desactiva el modo shuffle"""
    try:
        if not hasattr(radio, 'shuffle_mode'):
            radio.shuffle_mode = False
        
        radio.shuffle_mode = not radio.shuffle_mode
        status = "activado" if radio.shuffle_mode else "desactivado"
        pass  # log suprimido
        
        return jsonify({
            "success": True, 
            "message": f"🔀 Shuffle {status}",
            "shuffle": radio.shuffle_mode
        })
    except Exception as e:
        logger.error(f"Error en shuffle: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/loop", methods=["POST"])
@login_required
def loop_track():
    """Activa/desactiva el modo loop"""
    try:
        if not hasattr(radio, 'loop_mode'):
            radio.loop_mode = False
        
        radio.loop_mode = not radio.loop_mode
        status = "activado" if radio.loop_mode else "desactivado"
        pass  # log suprimido
        
        return jsonify({
            "success": True, 
            "message": f"🔁 Loop {status}",
            "loop": radio.loop_mode
        })
    except Exception as e:
        logger.error(f"Error en loop: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/update_crossfade', methods=['POST'])
@login_required
def update_crossfade():
    try:
        data = request.get_json()
        seconds = int(data.get('seconds', 20))
        radio.crossfade_seconds = seconds
        pass  # log suprimido
        return jsonify({"success": True, "seconds": seconds})
    except Exception as e:
        logger.error(f"Error actualizando crossfade: {e}")
        return jsonify({"success": False, "message": str(e)}), 400

# ================== ERROR HANDLERS PROFESIONALES ==================
@app.errorhandler(404)
def not_found(e):
    """Handler para 404 - Not Found"""
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "message": "Endpoint no encontrado"}), 404
    return redirect(url_for('login'))

@app.errorhandler(500)
def internal_error(e):
    """Handler para 500 - Internal Server Error"""
    logger.error(f"Error interno del servidor: {e}")
    return jsonify({"success": False, "message": "Error interno del servidor"}), 500

@app.errorhandler(413)
def request_entity_too_large(e):
    """Handler para 413 - Request Entity Too Large"""
    return jsonify({
        "success": False,
        "message": f"Archivo muy grande. Máximo: {MAX_FILE_SIZE / (1024*1024):.0f}MB"
    }), 413

# ================== INICIO ==================
if __name__ == "__main__":
    print("\n" + "="*80)
    print("🎵 NOCTURNO DJ BOT PRO v7.0")
    print("="*80)
    print(f"📁 Directorios:")
    print(f"   🎤 Jingles: {JINGLES_FOLDER}")
    print(f"   📊 Logs: {LOGS_FOLDER}")
    print(f"   💾 Backups: {BACKUP_FOLDER}")
    print("="*80 + "\n")

    port = int(os.environ.get("PORT", 5000))

    if not radio_thread.is_alive():
        radio_thread.start()

    # Flask corre en hilo de fondo; el bot de Highrise ocupa el hilo principal
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    print(f"[WEB] 🌐 Panel web corriendo en puerto {port}")

    print("="*80)
    print("🤖 INICIANDO BOT DE HIGHRISE")
    print("="*80 + "\n")
    run_highrise_bot()
