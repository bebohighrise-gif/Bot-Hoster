from flask import Flask, render_template_string, jsonify, request, send_from_directory
import requests
import threading
import time
import os
import json
import subprocess
import sys
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nocturno-bot-super-secret-key-2024')

# URL de la sala de Highrise (NO SE MUESTRA, solo se usa internamente)
ROOM_URL = "https://high.rs/room?id=686c527e9668a3cb40e1f58d&invite_id=698ae5d1b755084f644dbcaa"

# Variables globales para el estado del bot
bot_status = {
    "active": False,
    "uptime_start": None,
    "active_users": 0,
    "messages_today": 0,
    "commands_executed": 0,
    "last_activity": []
}

# ============================================================================
#                            CONFIGURACIÓN
# ============================================================================

def load_config(config_file="config.json"):
    """Carga la configuración desde un archivo JSON"""
    try:
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            logger.error(f"No se encontró {config_file}")
            return None
    except Exception as e:
        logger.error(f"Error cargando {config_file}: {e}")
        return None

# ============================================================================
#                        GESTIÓN DEL BOT
# ============================================================================

def run_bot(bot_name, bot_file, room_id, api_token):
    """Ejecuta un bot usando el SDK de Highrise"""
    logger.info("="*60)
    logger.info(f"Iniciando {bot_name}")
    logger.info(f"Archivo: {bot_file}")
    logger.info("="*60)
    
    bot_status["active"] = True
    bot_status["uptime_start"] = datetime.now()
    
    cmd = [
        sys.executable,
        "-m",
        "highrise",
        bot_file,
        room_id,
        api_token
    ]

    while True:
        try:
            # Recargar configuración antes de cada inicio
            config = load_config("config.json")
            if config:
                room_id = config.get("room_id", room_id)
                api_token = config.get("api_token", api_token)

            cmd = [
                sys.executable,
                "-m",
                "highrise",
                bot_file,
                room_id,
                api_token
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in process.stdout:
                log_line = f"[{bot_name}] {line.strip()}"
                logger.info(log_line)
                
                # Actualizar actividad
                if len(bot_status["last_activity"]) >= 20:
                    bot_status["last_activity"].pop()
                bot_status["last_activity"].insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "text": line.strip()[:100]
                })
                
                sys.stdout.flush()

            code = process.wait()
            logger.warning(f"{bot_name} terminó con código {code}. Reiniciando en 15s...")
            time.sleep(15)

        except Exception as e:
            logger.error(f"Error en {bot_name}: {e}")
            time.sleep(5)

def start_bots():
    """Inicializa y lanza todos los bots"""
    logger.info("\n" + "="*60)
    logger.info("🌙 NOCTURNO BOT LAUNCHER v2.0")
    logger.info("="*60 + "\n")

    required_files = ["config.json", "main.py"]

    for file in required_files:
        status = "✅ Encontrado" if os.path.exists(file) else "❌ NO encontrado"
        logger.info(f"{status}: {file}")

    config_main = load_config("config.json")

    if not config_main:
        logger.error("❌ Error cargando configuración principal")
        return

    api_main = config_main.get("api_token")
    room_main = config_main.get("room_id")

    # Lanzar bot principal
    threading.Thread(
        target=run_bot, 
        args=("Bot Principal", "main:Bot", room_main, api_main), 
        daemon=True
    ).start()
    
    logger.info("✅ Bot principal iniciado correctamente")

# ============================================================================
#                        PÁGINAS HTML
# ============================================================================

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NOCTURNO Bot - Access Control</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Electrolize&family=Russo+One&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --neon-purple: #b026ff;
            --neon-pink: #ff006e;
            --neon-blue: #00f0ff;
            --dark-bg: #0a0014;
            --card-bg: rgba(16, 0, 30, 0.9);
        }
        body {
            font-family: 'Electrolize', sans-serif;
            background: var(--dark-bg);
            color: #fff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }
        .background {
            position: fixed;
            width: 100%;
            height: 100%;
            top: 0;
            left: 0;
            z-index: -1;
            background: 
                radial-gradient(circle at 20% 30%, rgba(176, 38, 255, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 80% 70%, rgba(255, 0, 110, 0.12) 0%, transparent 50%),
                linear-gradient(135deg, #0a0014 0%, #1a0028 50%, #0d001f 100%);
        }
        .grid-overlay {
            position: fixed;
            width: 100%;
            height: 100%;
            top: 0;
            left: 0;
            z-index: -1;
            background-image: 
                linear-gradient(rgba(176, 38, 255, 0.05) 1px, transparent 1px),
                linear-gradient(90deg, rgba(176, 38, 255, 0.05) 1px, transparent 1px);
            background-size: 40px 40px;
            animation: gridMove 30s linear infinite;
        }
        @keyframes gridMove {
            0% { transform: translateY(0) translateX(0); }
            100% { transform: translateY(40px) translateX(40px); }
        }
        .login-container {
            width: 90%;
            max-width: 500px;
            padding: 3rem;
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border: 2px solid var(--neon-purple);
            border-radius: 30px;
            box-shadow: 0 0 60px rgba(176, 38, 255, 0.5);
            animation: fadeInScale 1s ease-out;
        }
        @keyframes fadeInScale {
            from { opacity: 0; transform: scale(0.8) translateY(50px); }
            to { opacity: 1; transform: scale(1) translateY(0); }
        }
        .logo-icon {
            width: 100px;
            height: 100px;
            margin: 0 auto 1.5rem;
            background: linear-gradient(135deg, var(--neon-purple), var(--neon-pink));
            border-radius: 25px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Russo One', sans-serif;
            font-size: 48px;
            box-shadow: 0 0 40px var(--neon-purple);
            animation: logoFloat 3s ease-in-out infinite;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .logo-icon:hover {
            transform: scale(1.1);
            box-shadow: 0 0 60px var(--neon-purple);
        }
        @keyframes logoFloat {
            0%, 100% { transform: translateY(0) rotate(0deg); }
            50% { transform: translateY(-10px) rotate(5deg); }
        }
        .logo h1 {
            font-family: 'Russo One', sans-serif;
            font-size: 2.5rem;
            background: linear-gradient(90deg, var(--neon-purple), var(--neon-pink), var(--neon-blue));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 4px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .logo h1:hover {
            transform: scale(1.05);
            filter: drop-shadow(0 0 20px var(--neon-purple));
        }
        .logo p {
            font-family: 'Orbitron', monospace;
            color: var(--neon-blue);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 3px;
            text-shadow: 0 0 10px var(--neon-blue);
            text-align: center;
            margin-bottom: 2rem;
        }
        .form-group {
            margin-bottom: 2rem;
        }
        .form-group label {
            display: block;
            margin-bottom: 0.8rem;
            color: var(--neon-purple);
            font-family: 'Orbitron', monospace;
            text-transform: uppercase;
            letter-spacing: 2px;
            text-shadow: 0 0 10px var(--neon-purple);
        }
        .form-group input {
            width: 100%;
            padding: 1rem 1.5rem;
            background: rgba(176, 38, 255, 0.05);
            border: 2px solid rgba(176, 38, 255, 0.3);
            border-radius: 15px;
            color: #fff;
            font-size: 1.1rem;
            font-family: 'Electrolize', sans-serif;
            letter-spacing: 3px;
            transition: all 0.4s ease;
        }
        .form-group input:focus {
            outline: none;
            border-color: var(--neon-purple);
            background: rgba(176, 38, 255, 0.1);
            box-shadow: 0 0 20px rgba(176, 38, 255, 0.4);
        }
        .login-button {
            width: 100%;
            padding: 1.2rem;
            background: linear-gradient(135deg, var(--neon-purple), var(--neon-pink));
            border: none;
            border-radius: 15px;
            color: #fff;
            font-family: 'Russo One', sans-serif;
            font-size: 1.2rem;
            text-transform: uppercase;
            letter-spacing: 3px;
            cursor: pointer;
            transition: all 0.4s ease;
            box-shadow: 0 0 30px rgba(176, 38, 255, 0.6);
        }
        .login-button:hover {
            transform: translateY(-3px);
            box-shadow: 0 0 50px rgba(176, 38, 255, 0.9);
        }
        .error-message {
            background: rgba(255, 0, 110, 0.1);
            border: 2px solid var(--neon-pink);
            border-radius: 10px;
            padding: 1rem;
            margin-top: 1rem;
            text-align: center;
            color: var(--neon-pink);
            font-family: 'Orbitron', monospace;
            display: none;
            animation: shake 0.5s ease;
        }
        .error-message.show { display: block; }
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-10px); }
            75% { transform: translateX(10px); }
        }
        .creator-info {
            text-align: center;
            padding: 2rem 1.5rem;
            background: rgba(176, 38, 255, 0.05);
            border: 2px solid rgba(176, 38, 255, 0.2);
            border-radius: 20px;
            margin-top: 2rem;
        }
        .creator-title {
            font-family: 'Orbitron', monospace;
            font-size: 1.1rem;
            color: var(--neon-blue);
            margin-bottom: 1rem;
            text-transform: uppercase;
            letter-spacing: 2px;
            text-shadow: 0 0 15px var(--neon-blue);
        }
        .creator-services {
            margin-bottom: 1.5rem;
            line-height: 2;
            color: rgba(255, 255, 255, 0.8);
        }
        .creator-services div {
            margin: 0.5rem 0;
            font-size: 0.95rem;
        }
        .creator-services span {
            color: var(--neon-purple);
            font-weight: bold;
        }
        .contact-cta {
            font-size: 1rem;
            color: rgba(255, 255, 255, 0.9);
            margin-bottom: 1rem;
        }
        .creator-link {
            display: inline-block;
            padding: 1rem 2rem;
            background: linear-gradient(135deg, var(--neon-pink), var(--neon-purple));
            border-radius: 15px;
            color: #fff;
            font-family: 'Russo One', sans-serif;
            font-size: 1.1rem;
            text-decoration: none;
            letter-spacing: 2px;
            transition: all 0.4s ease;
            box-shadow: 0 0 30px rgba(255, 0, 110, 0.5);
            cursor: pointer;
        }
        .creator-link:hover {
            transform: translateY(-5px) scale(1.05);
            box-shadow: 0 0 50px rgba(255, 0, 110, 0.8);
        }
    </style>
</head>
<body>
    <div class="background"></div>
    <div class="grid-overlay"></div>
    
    <div class="login-container">
        <div class="logo">
            <div class="logo-icon" onclick="window.open('{{ room_url }}', '_blank')">N</div>
            <h1 onclick="window.open('{{ room_url }}', '_blank')">NOCTURNO</h1>
            <p>Bot Access Control</p>
        </div>
        <form class="login-form" id="loginForm">
            <div class="form-group">
                <label>🔐 Código de Acceso</label>
                <input type="password" id="password" placeholder="••••••" autocomplete="off" required>
            </div>
            <button type="submit" class="login-button">Acceder al Sistema</button>
            <div class="error-message" id="errorMessage">❌ Código incorrecto</div>
        </form>
        
        <div class="creator-info">
            <div class="creator-title">👨‍💻 Creado por {{ creator_name }}</div>
            <div class="creator-services">
                {% for service in creator_services %}
                <div>✨ <span>{{ service }}</span></div>
                {% endfor %}
            </div>
            <div class="contact-cta">💬 Toca aquí para contactar con el creador</div>
            <a href="#" class="creator-link" onclick="window.open('{{ creator_url }}', '_blank'); return false;">
                @{{ creator_username }}
            </a>
        </div>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const password = document.getElementById('password').value;
            
            fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({password: password})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    sessionStorage.setItem('nocturno_auth', 'true');
                    window.location.href = '/dashboard';
                } else {
                    document.getElementById('errorMessage').classList.add('show');
                    document.getElementById('password').value = '';
                }
            });
        });
        
        window.addEventListener('load', () => {
            document.getElementById('password').focus();
        });
    </script>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NOCTURNO Bot - Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Electrolize&family=Russo+One&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --neon-purple: #b026ff;
            --neon-pink: #ff006e;
            --neon-blue: #00f0ff;
            --neon-green: #39ff14;
            --dark-bg: #0a0014;
            --card-bg: rgba(16, 0, 30, 0.85);
        }
        body {
            font-family: 'Electrolize', sans-serif;
            background: var(--dark-bg);
            color: #fff;
        }
        .background {
            position: fixed;
            width: 100%;
            height: 100%;
            top: 0;
            left: 0;
            z-index: -1;
            background: 
                radial-gradient(circle at 20% 30%, rgba(176, 38, 255, 0.12) 0%, transparent 50%),
                linear-gradient(135deg, #0a0014 0%, #1a0028 50%, #0d001f 100%);
        }
        header {
            padding: 1.5rem 3rem;
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-bottom: 3px solid var(--neon-purple);
            box-shadow: 0 5px 40px rgba(176, 38, 255, 0.4);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        .header-content {
            max-width: 1600px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1.5rem;
        }
        .logo-section {
            display: flex;
            align-items: center;
            gap: 1.5rem;
            cursor: pointer;
        }
        .logo-icon {
            width: 60px;
            height: 60px;
            background: linear-gradient(135deg, var(--neon-purple), var(--neon-pink));
            border-radius: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Russo One', sans-serif;
            font-size: 32px;
            box-shadow: 0 0 30px var(--neon-purple);
            overflow: hidden;
            position: relative;
            transition: all 0.3s ease;
        }
        .logo-icon:hover {
            transform: scale(1.1);
            box-shadow: 0 0 50px var(--neon-purple);
        }
        .logo-icon img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            position: absolute;
            top: 0;
            left: 0;
        }
        .logo-text h1 {
            font-family: 'Russo One', sans-serif;
            font-size: 2rem;
            background: linear-gradient(90deg, var(--neon-purple), var(--neon-pink), var(--neon-blue));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            transition: all 0.3s ease;
        }
        .logo-text h1:hover {
            transform: scale(1.05);
            filter: drop-shadow(0 0 20px var(--neon-purple));
        }
        .logo-text p {
            color: rgba(255, 255, 255, 0.6);
            font-size: 0.85rem;
            letter-spacing: 2px;
        }
        .header-actions {
            display: flex;
            gap: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }
        .status-badge {
            padding: 0.8rem 1.5rem;
            background: rgba(57, 255, 20, 0.1);
            border: 2px solid var(--neon-green);
            border-radius: 50px;
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            background: var(--neon-green);
            border-radius: 50%;
            animation: blink 1.5s infinite;
        }
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .status-text {
            font-family: 'Orbitron', monospace;
            font-weight: 700;
            color: var(--neon-green);
            font-size: 0.9rem;
            text-transform: uppercase;
        }
        .btn-logout {
            padding: 0.8rem 1.8rem;
            background: rgba(255, 0, 110, 0.1);
            border: 2px solid var(--neon-pink);
            border-radius: 50px;
            color: var(--neon-pink);
            font-family: 'Orbitron', monospace;
            font-weight: 700;
            font-size: 0.9rem;
            text-transform: uppercase;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .btn-logout:hover {
            background: rgba(255, 0, 110, 0.2);
            transform: translateY(-3px);
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 2.5rem 2rem;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 2rem;
            margin-bottom: 3rem;
        }
        .stat-card {
            background: var(--card-bg);
            backdrop-filter: blur(10px);
            border: 2px solid rgba(176, 38, 255, 0.3);
            border-radius: 20px;
            padding: 2rem;
            transition: all 0.3s ease;
        }
        .stat-card:hover {
            transform: translateY(-5px);
            border-color: var(--neon-purple);
            box-shadow: 0 10px 40px rgba(176, 38, 255, 0.4);
        }
        .stat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        .stat-label {
            font-family: 'Orbitron', monospace;
            color: rgba(255, 255, 255, 0.7);
            font-size: 0.9rem;
            text-transform: uppercase;
        }
        .stat-icon {
            font-size: 1.5rem;
        }
        .stat-value {
            font-family: 'Russo One', sans-serif;
            font-size: 3rem;
            color: var(--neon-purple);
            margin: 1rem 0;
            text-shadow: 0 0 20px var(--neon-purple);
        }
        .stat-description {
            color: rgba(255, 255, 255, 0.5);
            font-size: 0.85rem;
        }
        .activity-log {
            background: var(--card-bg);
            border: 2px solid rgba(176, 38, 255, 0.3);
            border-radius: 20px;
            padding: 2rem;
            margin-top: 2rem;
        }
        .activity-log h2 {
            color: var(--neon-purple);
            margin-bottom: 1.5rem;
            font-family: 'Russo One', sans-serif;
        }
        .activity-item {
            padding: 1rem;
            border-bottom: 1px solid rgba(176, 38, 255, 0.2);
            display: flex;
            justify-content: space-between;
            gap: 1rem;
        }
        .activity-item:last-child {
            border-bottom: none;
        }
        .activity-time {
            color: var(--neon-blue);
            font-family: 'Orbitron', monospace;
            min-width: 80px;
        }
        .activity-text {
            flex: 1;
            color: rgba(255, 255, 255, 0.8);
        }
        .creator-footer {
            text-align: center;
            padding: 3rem 2rem;
            margin-top: 4rem;
            border-top: 2px solid rgba(176, 38, 255, 0.2);
        }
        .creator-footer p {
            color: rgba(255, 255, 255, 0.6);
            margin-bottom: 1rem;
        }
        .creator-link-footer {
            display: inline-block;
            padding: 0.8rem 2rem;
            background: linear-gradient(135deg, var(--neon-pink), var(--neon-purple));
            border-radius: 15px;
            color: #fff;
            font-family: 'Russo One', sans-serif;
            text-decoration: none;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .creator-link-footer:hover {
            transform: translateY(-3px);
            box-shadow: 0 0 30px rgba(255, 0, 110, 0.6);
        }
    </style>
</head>
<body>
    <div class="background"></div>
    <header>
        <div class="header-content">
            <div class="logo-section" onclick="window.open('{{ room_url }}', '_blank')">
                <div class="logo-icon" id="logoIcon">
                    <img id="avatarImage" src="/api/avatar" alt="HR" onerror="this.style.display='none'; this.parentElement.innerHTML='N';">
                </div>
                <div class="logo-text">
                    <h1>NOCTURNO</h1>
                    <p>Bot Dashboard</p>
                </div>
            </div>
            <div class="header-actions">
                <div class="status-badge">
                    <div class="status-dot"></div>
                    <span class="status-text" id="botStatus">ONLINE</span>
                </div>
                <button class="btn-logout" onclick="logout()">🚪 Salir</button>
            </div>
        </div>
    </header>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-label">Usuarios Activos</div>
                    <div class="stat-icon">👥</div>
                </div>
                <div class="stat-value" id="activeUsers">0</div>
                <div class="stat-description">En la sala ahora</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-label">Mensajes Hoy</div>
                    <div class="stat-icon">💬</div>
                </div>
                <div class="stat-value" id="messagesCount">0</div>
                <div class="stat-description">Actividad en las últimas 24h</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-label">Comandos Ejecutados</div>
                    <div class="stat-icon">⚡</div>
                </div>
                <div class="stat-value" id="commandsCount">0</div>
                <div class="stat-description">Comandos procesados hoy</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-label">Tiempo Online</div>
                    <div class="stat-icon">⏱️</div>
                </div>
                <div class="stat-value" id="uptime">0h</div>
                <div class="stat-description">Sin interrupciones</div>
            </div>
        </div>
        
        <div class="activity-log">
            <h2>📊 Actividad Reciente</h2>
            <div id="activityList">
                <div class="activity-item">
                    <div class="activity-time">--:--:--</div>
                    <div class="activity-text">Esperando actividad del bot...</div>
                </div>
            </div>
        </div>
    </div>
    
    <footer class="creator-footer">
        <p>✨ Desarrollado por</p>
        <a href="#" class="creator-link-footer" onclick="window.open('{{ creator_url }}', '_blank'); return false;">
            @{{ creator_username }}
        </a>
        <p style="margin-top: 1rem; font-size: 0.85rem;">🚀 NOCTURNO Bot System v2.0</p>
    </footer>
    
    <script>
        if (sessionStorage.getItem('nocturno_auth') !== 'true') {
            window.location.href = '/';
        }
        
        function logout() {
            sessionStorage.removeItem('nocturno_auth');
            window.location.href = '/';
        }
        
        function updateDashboard() {
            fetch('/api/stats')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('activeUsers').textContent = data.active_users;
                    document.getElementById('messagesCount').textContent = data.messages_today;
                    document.getElementById('commandsCount').textContent = data.commands_executed;
                    document.getElementById('uptime').textContent = data.uptime;
                    document.getElementById('botStatus').textContent = data.active ? 'ONLINE' : 'OFFLINE';
                    
                    const activityList = document.getElementById('activityList');
                    if (data.last_activity && data.last_activity.length > 0) {
                        activityList.innerHTML = '';
                        data.last_activity.slice(0, 10).forEach(activity => {
                            const item = document.createElement('div');
                            item.className = 'activity-item';
                            item.innerHTML = `
                                <div class="activity-time">${activity.time}</div>
                                <div class="activity-text">${activity.text}</div>
                            `;
                            activityList.appendChild(item);
                        });
                    }
                })
                .catch(err => console.error('Error updating dashboard:', err));
        }
        
        updateDashboard();
        setInterval(updateDashboard, 5000);
    </script>
</body>
</html>
"""

# ============================================================================
#                        RUTAS FLASK
# ============================================================================

@app.route("/")
def home():
    config = load_config()
    creator = config.get("creator", {}) if config else {}
    return render_template_string(
        LOGIN_HTML,
        room_url=ROOM_URL,
        creator_name=creator.get("name", "Kmi.77"),
        creator_username=creator.get("username", "_Kmi.77"),
        creator_url=creator.get("profile_url", "https://high.rs/user?name=_Kmi.77"),
        creator_services=creator.get("services", [
            "Páginas Web Profesionales",
            "Bots de Highrise Personalizados",
            "Emisoras de Streaming",
            "Y mucho más..."
        ])
    )

@app.route("/dashboard")
def dashboard():
    config = load_config()
    creator = config.get("creator", {}) if config else {}
    return render_template_string(
        DASHBOARD_HTML,
        room_url=ROOM_URL,
        creator_username=creator.get("username", "_Kmi.77"),
        creator_url=creator.get("profile_url", "https://high.rs/user?name=_Kmi.77")
    )

# ============================================================================
#                        API ENDPOINTS
# ============================================================================

@app.route("/api/login", methods=["POST"])
def api_login():
    """Endpoint de login - NO muestra información del config"""
    try:
        data = request.json
        password = data.get("password", "")
        config = load_config()
        
        if not config:
            return jsonify({"success": False, "error": "Error de configuración"})
        
        correct_password = config.get("password", "070927")
        
        if password == correct_password:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Contraseña incorrecta"})
    except Exception as e:
        logger.error(f"Error en login: {e}")
        return jsonify({"success": False, "error": "Error del servidor"})

@app.route("/api/stats")
def api_stats():
    """Retorna estadísticas del bot - NO muestra información del config"""
    try:
        uptime = "0h"
        if bot_status["uptime_start"]:
            delta = datetime.now() - bot_status["uptime_start"]
            hours = delta.total_seconds() / 3600
            uptime = f"{int(hours)}h {int((hours % 1) * 60)}m"
        
        return jsonify({
            "active": bot_status["active"],
            "active_users": bot_status["active_users"],
            "messages_today": bot_status["messages_today"],
            "commands_executed": bot_status["commands_executed"],
            "uptime": uptime,
            "last_activity": bot_status["last_activity"]
        })
    except Exception as e:
        logger.error(f"Error obteniendo stats: {e}")
        return jsonify({"error": "Error del servidor"}), 500

@app.route("/api/avatar")
def api_avatar():
    """Retorna la imagen del avatar de Highrise"""
    try:
        avatar_files = [
            "Highrise-Room-26-01-26-06-33-13.png",
            "avatar.png",
            "hr_avatar.png",
            "bot_avatar.png"
        ]
        
        for filename in avatar_files:
            if os.path.exists(filename):
                return send_from_directory(".", filename)
        
        return "", 404
    except Exception as e:
        logger.error(f"Error sirviendo avatar: {e}")
        return "", 404

@app.route("/health")
def health():
    """Health check para Render - NO muestra información del config"""
    return jsonify({
        "status": "OK",
        "bot_active": bot_status["active"],
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route("/status")
def status():
    """Status endpoint - NO muestra información del config"""
    return jsonify({
        "status": "active",
        "bots": ["principal"],
        "active": bot_status["active"],
        "uptime": str(datetime.now() - bot_status["uptime_start"]) if bot_status["uptime_start"] else "0",
        "timestamp": time.time()
    })

# ============================================================================
#                    INICIO DEL SERVIDOR
# ============================================================================

def start_webserver():
    """Inicia el servidor Flask"""
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Servidor web escuchando en puerto {port}")
    logger.info(f"📱 Accede a: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

# ============================================================================
#                        MAIN
# ============================================================================

if __name__ == "__main__":
    try:
        logger.info("🚀 Iniciando NOCTURNO Bot System v2.0...")
        
        # Iniciar bots en segundo plano
        threading.Thread(target=start_bots, daemon=True).start()
        
        # Pequeña pausa para que los bots inicien
        time.sleep(2)
        
        # Iniciar servidor Flask
        start_webserver()
        
    except KeyboardInterrupt:
        logger.info("\n👋 Sistema detenido por el usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        raise
