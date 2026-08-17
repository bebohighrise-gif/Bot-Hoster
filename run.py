import subprocess
import sys
import json
import os
import threading
import http.server
import socketserver
from datetime import datetime

# ---------- GENERAR HTML DINÁMICAMENTE (en memoria) ----------
def generar_html():
    # Leer configuración
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}

    room_id = config.get("ROOM_ID", "No configurado")
    owner_id = config.get("HOSTER_OWNER_ID", "No configurado")
    api_token = config.get("BOT_API_TOKEN", "No configurado")
    api_token_masked = api_token[:10] + "..." if len(api_token) > 10 else api_token

    # Leer categorías desde templates/
    categories = []
    if os.path.isdir("templates"):
        for item in os.listdir("templates"):
            if os.path.isdir(os.path.join("templates", item)):
                categories.append(item)
    else:
        categories = ["musica", "juegos", "fiesta", "personalizado"]

    # Contar bots activos (opcional)
    bots_count = "N/A"
    try:
        import sqlite3
        db_path = "bots.db"
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM hosted_bots WHERE estado = 'activo'")
            bots_count = c.fetchone()[0]
            conn.close()
    except Exception:
        pass

    render_port = os.environ.get("PORT", "8000")
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # PLANTILLA HTML COMPLETA (incrustada aquí)
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Nex-Host · Bot Hoster para Highrise</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700;14..32,800&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', sans-serif; background: #0b0e1a; color: #e4e7f0; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 0 2rem; }}
        .btn-glow {{ display: inline-block; background: linear-gradient(135deg, #7c3aed, #4f46e5); color: #fff; font-weight: 600; padding: 0.8rem 2rem; border-radius: 2rem; border: none; cursor: pointer; transition: all 0.3s ease; box-shadow: 0 0 15px rgba(124, 58, 237, 0.4); font-size: 1rem; text-decoration: none; }}
        .btn-glow:hover {{ transform: translateY(-3px); box-shadow: 0 0 30px rgba(124, 58, 237, 0.7); background: linear-gradient(135deg, #8b5cf6, #6366f1); }}
        .btn-outline {{ display: inline-block; background: transparent; border: 2px solid #7c3aed; color: #e4e7f0; font-weight: 600; padding: 0.75rem 2rem; border-radius: 2rem; transition: all 0.3s ease; text-decoration: none; }}
        .btn-outline:hover {{ background: #7c3aed; color: #fff; box-shadow: 0 0 20px rgba(124, 58, 237, 0.3); }}
        header {{ padding: 1.5rem 0; border-bottom: 1px solid #1e2438; position: sticky; top: 0; background: rgba(11, 14, 26, 0.9); backdrop-filter: blur(10px); z-index: 100; }}
        header .container {{ display: flex; justify-content: space-between; align-items: center; }}
        .logo {{ font-size: 1.8rem; font-weight: 800; letter-spacing: -1px; }}
        .logo span {{ color: #7c3aed; }}
        .hero {{ padding: 6rem 0 4rem; background: radial-gradient(ellipse at top left, #1a1f33, #0b0e1a 70%); }}
        .hero .container {{ display: flex; flex-wrap: wrap; align-items: center; gap: 3rem; }}
        .hero-content {{ flex: 1 1 500px; }}
        .hero-content h1 {{ font-size: 3.5rem; font-weight: 800; line-height: 1.1; margin-bottom: 1.2rem; }}
        .hero-content h1 .highlight {{ color: #7c3aed; position: relative; }}
        .hero-content h1 .highlight::after {{ content: ''; position: absolute; left: 0; bottom: -5px; width: 100%; height: 4px; background: linear-gradient(90deg, #7c3aed, #4f46e5); border-radius: 2px; }}
        .hero-content p {{ font-size: 1.2rem; color: #b0b8d1; max-width: 550px; margin-bottom: 2rem; }}
        .hero-buttons {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
        .hero-stats {{ display: flex; gap: 3rem; margin-top: 3rem; padding-top: 2rem; border-top: 1px solid #1e2438; }}
        .hero-stats div {{ text-align: center; }}
        .hero-stats .number {{ font-size: 2rem; font-weight: 700; color: #7c3aed; }}
        .hero-stats .label {{ font-size: 0.9rem; color: #8892b0; }}
        .hero-image {{ flex: 1 1 400px; background: linear-gradient(135deg, #1e2438, #2a2f4a); border-radius: 2rem; padding: 2rem; text-align: center; border: 1px solid #2a2f4a; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6); }}
        .hero-image i {{ font-size: 8rem; color: #7c3aed; opacity: 0.8; }}
        .hero-image h3 {{ margin-top: 1rem; font-weight: 600; font-size: 1.5rem; }}
        .hero-image p {{ color: #b0b8d1; font-size: 0.95rem; }}
        section {{ padding: 5rem 0; }}
        .section-title {{ font-size: 2.5rem; font-weight: 700; text-align: center; margin-bottom: 3rem; }}
        .section-title span {{ color: #7c3aed; }}
        .section-subtitle {{ text-align: center; color: #8892b0; max-width: 700px; margin: -1.5rem auto 3rem; font-size: 1.1rem; }}
        .features-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 2rem; }}
        .feature-card {{ background: #131826; padding: 2rem 1.5rem; border-radius: 1.5rem; border: 1px solid #1e2438; transition: transform 0.3s, border-color 0.3s; }}
        .feature-card:hover {{ transform: translateY(-6px); border-color: #7c3aed; }}
        .feature-card .icon {{ font-size: 2.5rem; color: #7c3aed; margin-bottom: 1rem; }}
        .feature-card h3 {{ font-size: 1.3rem; margin-bottom: 0.5rem; }}
        .feature-card p {{ color: #b0b8d1; font-size: 0.95rem; }}
        .commands-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; }}
        .command-card {{ background: #131826; border-radius: 1rem; padding: 1.2rem 1.5rem; border-left: 4px solid #7c3aed; transition: background 0.3s; }}
        .command-card:hover {{ background: #1a1f33; }}
        .command-card .cmd {{ font-family: 'Courier New', monospace; font-weight: 700; color: #a78bfa; font-size: 1.1rem; }}
        .command-card .desc {{ color: #b0b8d1; font-size: 0.95rem; margin-top: 0.3rem; }}
        .command-card .badge {{ display: inline-block; font-size: 0.7rem; background: #2a2f4a; padding: 0.2rem 0.8rem; border-radius: 1rem; margin-top: 0.5rem; color: #b0b8d1; }}
        .command-card .badge.admin {{ background: #7c3aed; color: #fff; }}
        .install-steps {{ display: flex; flex-wrap: wrap; gap: 2rem; justify-content: center; }}
        .step {{ background: #131826; border-radius: 1.5rem; padding: 2rem; flex: 1 1 280px; text-align: center; border: 1px solid #1e2438; }}
        .step .step-num {{ display: inline-block; background: #7c3aed; color: #fff; width: 40px; height: 40px; border-radius: 50%; line-height: 40px; font-weight: 700; margin-bottom: 1rem; }}
        .step h4 {{ font-size: 1.2rem; margin-bottom: 0.5rem; }}
        .step p {{ color: #b0b8d1; font-size: 0.95rem; }}
        .step code {{ background: #0b0e1a; padding: 0.2rem 0.6rem; border-radius: 0.4rem; font-size: 0.85rem; color: #a78bfa; }}
        .times-grid {{ display: flex; flex-wrap: wrap; gap: 1rem; justify-content: center; margin-top: 2rem; }}
        .time-chip {{ background: #1a1f33; padding: 0.5rem 1.5rem; border-radius: 2rem; font-weight: 600; border: 1px solid #2a2f4a; }}
        .time-chip span {{ color: #a78bfa; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; background: #131826; border-radius: 1.5rem; padding: 2rem; border: 1px solid #1e2438; margin-top: 2rem; }}
        .info-item {{ text-align: center; }}
        .info-item .label {{ color: #8892b0; font-size: 0.9rem; }}
        .info-item .value {{ font-size: 1.2rem; font-weight: 600; color: #e4e7f0; word-break: break-all; }}
        .render-card {{ background: #1a1f33; border-radius: 1.5rem; padding: 2rem; border: 2px solid #7c3aed; margin: 2rem 0; text-align: center; }}
        .render-card i {{ color: #7c3aed; font-size: 2.5rem; margin-bottom: 1rem; }}
        footer {{ border-top: 1px solid #1e2438; padding: 2.5rem 0; text-align: center; color: #8892b0; }}
        footer .social {{ display: flex; justify-content: center; gap: 1.5rem; margin-bottom: 1rem; }}
        footer .social a {{ color: #b0b8d1; font-size: 1.3rem; transition: color 0.3s; }}
        footer .social a:hover {{ color: #7c3aed; }}
        @media (max-width: 768px) {{ .hero-content h1 {{ font-size: 2.5rem; }} .hero-stats {{ gap: 1.5rem; flex-wrap: wrap; }} .section-title {{ font-size: 2rem; }} .commands-grid {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <div class="logo">Nex<span>Host</span></div>
            <nav>
                <a href="#features" style="color: #b0b8d1; margin-right: 1.5rem; text-decoration: none;">Características</a>
                <a href="#commands" style="color: #b0b8d1; margin-right: 1.5rem; text-decoration: none;">Comandos</a>
                <a href="#install" style="color: #b0b8d1; margin-right: 1.5rem; text-decoration: none;">Instalación</a>
                <a href="#" class="btn-glow" style="padding: 0.5rem 1.5rem; font-size: 0.9rem;">GitHub</a>
            </nav>
        </div>
    </header>

    <section class="hero">
        <div class="container">
            <div class="hero-content">
                <h1>Aloja bots para <br /><span class="highlight">Highrise 24/7</span></h1>
                <p>Nex-Host es una plataforma automatizada en Python que permite gestionar, desplegar y mantener bots de Highrise en tiempo real, con sistema de saldo, tienda y panel de administración.</p>
                <div class="hero-buttons">
                    <a href="#install" class="btn-glow">Comenzar</a>
                    <a href="#features" class="btn-outline">Explorar</a>
                </div>
                <div class="hero-stats">
                    <div><div class="number">24/7</div><div class="label">Disponibilidad</div></div>
                    <div><div class="number">{bots_count}</div><div class="label">Bots activos</div></div>
                    <div><div class="number">100%</div><div class="label">Automatizado</div></div>
                </div>
            </div>
            <div class="hero-image">
                <i class="fas fa-robot"></i>
                <h3>Bot Hoster</h3>
                <p>Gestiona tus bots desde el inbox con comandos simples.</p>
                <div style="margin-top: 1.5rem; display: flex; gap: 0.8rem; justify-content: center; flex-wrap: wrap;">
                    {''.join(f'<span class="time-chip"><i class="fas fa-check-circle" style="color: #7c3aed;"></i> {cat.capitalize()}</span>' for cat in categories)}
                </div>
            </div>
        </div>
    </section>

    <section style="background: #0f1322; padding: 2rem 0;">
        <div class="container">
            <h2 class="section-title" style="font-size: 1.8rem;">Configuración <span>actual</span></h2>
            <div class="info-grid">
                <div class="info-item"><div class="label">Room ID</div><div class="value">{room_id}</div></div>
                <div class="info-item"><div class="label">Owner ID</div><div class="value">{owner_id}</div></div>
                <div class="info-item"><div class="label">API Token</div><div class="value">{api_token_masked}</div></div>
                <div class="info-item"><div class="label">Categorías</div><div class="value">{', '.join(categories) or 'Ninguna'}</div></div>
                <div class="info-item"><div class="label">Puerto</div><div class="value">{render_port}</div></div>
            </div>
        </div>
    </section>

    <section style="background: #0b0e1a;">
        <div class="container">
            <div class="render-card">
                <i class="fas fa-cloud-upload-alt"></i>
                <h3 style="margin-bottom: 0.5rem;">Despliegue en <span style="color: #7c3aed;">Render</span></h3>
                <p style="color: #b0b8d1; max-width: 700px; margin: 0 auto 1.5rem;">
                    Nex-Host está listo para ejecutarse en Render. La plataforma asigna automáticamente un puerto 
                    (actualmente <strong>{render_port}</strong>) que se usa para mantener el servicio activo.
                    Solo necesitas configurar tu <code>config.json</code> y ejecutar <code>python run.py</code>.
                </p>
                <pre style="background: #0b0e1a; padding: 1rem; border-radius: 1rem; text-align: left; color: #a78bfa; max-width: 500px; margin: 0 auto; border: 1px solid #2a2f4a;">
# Comando para iniciar en Render
python run.py</pre>
                <p style="margin-top: 1rem; font-size: 0.9rem; color: #8892b0;">
                    <i class="fas fa-check-circle" style="color: #7c3aed;"></i> El bot se conecta a Highrise usando el token y room ID.
                </p>
            </div>
        </div>
    </section>

    <section id="features">
        <div class="container">
            <h2 class="section-title">Características <span>principales</span></h2>
            <p class="section-subtitle">Todo lo que necesitas para alojar y gestionar bots de Highrise de forma eficiente.</p>
            <div class="features-grid">
                <div class="feature-card"><div class="icon"><i class="fas fa-infinity"></i></div><h3>Alojamiento 24/7</h3><p>Instancias independientes que corren de manera continua sin interrupciones.</p></div>
                <div class="feature-card"><div class="icon"><i class="fas fa-coins"></i></div><h3>Sistema de Saldo (Gold)</h3><p>Recarga automática mediante donaciones o tips de oro en la sala.</p></div>
                <div class="feature-card"><div class="icon"><i class="fas fa-gift"></i></div><h3>Asistente paso a paso</h3><p>Comando <code>!giftbot</code> con flujo guiado para regalar bots sin complicaciones.</p></div>
                <div class="feature-card"><div class="icon"><i class="fas fa-clock"></i></div><h3>Tiempos flexibles</h3><p>Desde 15 minutos hasta 100 días, personaliza la duración de cada bot.</p></div>
                <div class="feature-card"><div class="icon"><i class="fas fa-clone"></i></div><h3>Copiar Outfit</h3><p>Comando <code>!copy</code> por susurro para clonar el outfit del dueño al instante.</p></div>
                <div class="feature-card"><div class="icon"><i class="fas fa-tools"></i></div><h3>Auto‑Mantenimiento</h3><p>Detección automática de categorías sin plantilla y gestión de expiraciones.</p></div>
            </div>
        </div>
    </section>

    <section id="commands" style="background: #0f1322;">
        <div class="container">
            <h2 class="section-title">Comandos <span>disponibles</span></h2>
            <p class="section-subtitle">Todos los comandos funcionan por <strong>Inbox</strong> (mensaje privado), excepto <code>!copy</code> que se envía por <strong>Susurro</strong>.</p>
            <div class="commands-grid">
                <div class="command-card"><div class="cmd">!menu</div><div class="desc">Muestra el menú principal, tu saldo y estado de tus bots.</div><span class="badge">Usuario</span></div>
                <div class="command-card"><div class="cmd">!saldo</div><div class="desc">Consulta tu balance actual de oro en la plataforma.</div><span class="badge">Usuario</span></div>
                <div class="command-card"><div class="cmd">!plan</div><div class="desc">Catálogo de categorías disponibles y sus precios.</div><span class="badge">Usuario</span></div>
                <div class="command-card"><div class="cmd">!buy &lt;CAT&gt; &lt;TOKEN&gt; &lt;ROOM_ID&gt;</div><div class="desc">Compra y despliega una instancia de bot en tu sala.</div><span class="badge">Usuario</span></div>
                <div class="command-card"><div class="cmd">!mybots</div><div class="desc">Lista todos los bots que tienes alojados actualmente.</div><span class="badge">Usuario</span></div>
                <div class="command-card"><div class="cmd">!gift &lt;USER_ID&gt; &lt;MONTO&gt;</div><div class="desc">Transfiere parte de tu saldo a otro usuario.</div><span class="badge">Usuario</span></div>
                <div class="command-card"><div class="cmd">!giftbot</div><div class="desc">Asistente paso a paso para regalar una instancia con tiempo personalizado.</div><span class="badge admin">Admin</span></div>
                <div class="command-card"><div class="cmd">!cancel</div><div class="desc">Cancela el flujo activo de <code>!giftbot</code>.</div><span class="badge admin">Admin</span></div>
                <div class="command-card"><div class="cmd">!addgold &lt;USER_ID&gt; &lt;CANT&gt;</div><div class="desc">Añade saldo manualmente a la cuenta de cualquier usuario.</div><span class="badge admin">Admin</span></div>
                <div class="command-card"><div class="cmd">!mantenimiento &lt;CAT&gt; on/off</div><div class="desc">Pone o quita el modo mantenimiento en una categoría.</div><span class="badge admin">Admin</span></div>
                <div class="command-card"><div class="cmd">!detener / !activar &lt;CAT&gt;</div><div class="desc">Enciende o apaga la venta de una categoría completa.</div><span class="badge admin">Admin</span></div>
                <div class="command-card"><div class="cmd">!copy</div><div class="desc">(Susurro) Ordena al Bot Hoster copiar exactamente tu outfit actual.</div><span class="badge admin">Admin</span></div>
            </div>
        </div>
    </section>

    <section id="times">
        <div class="container">
            <h2 class="section-title">Tiempos <span>dinámicos</span></h2>
            <p class="section-subtitle">En el paso 5 del asistente <code>!giftbot</code> puedes escribir cualquier duración sin restricciones.</p>
            <div class="times-grid">
                <span class="time-chip"><span>10m</span></span>
                <span class="time-chip"><span>15m</span></span>
                <span class="time-chip"><span>45m</span></span>
                <span class="time-chip"><span>1h</span></span>
                <span class="time-chip"><span>6h</span></span>
                <span class="time-chip"><span>18h</span></span>
                <span class="time-chip"><span>1d</span></span>
                <span class="time-chip"><span>7d</span></span>
                <span class="time-chip"><span>30d</span></span>
                <span class="time-chip"><span>100d</span></span>
            </div>
            <p style="text-align: center; margin-top: 2rem; color: #8892b0;"><i class="fas fa-arrow-right" style="color: #7c3aed;"></i> Formato: <strong>minutos (m)</strong>, <strong>horas (h)</strong> o <strong>días (d)</strong></p>
        </div>
    </section>

    <section id="install" style="background: #0f1322;">
        <div class="container">
            <h2 class="section-title">Instalación <span>rápida</span></h2>
            <p class="section-subtitle">Sigue estos pasos para poner en marcha tu propio Bot Hoster.</p>
            <div class="install-steps">
                <div class="step"><div class="step-num">1</div><h4>Clona el repositorio</h4><p>Estructura de carpetas lista con plantillas y configuración.</p><code>nex-host/</code></div>
                <div class="step"><div class="step-num">2</div><h4>Instala dependencias</h4><p>Usa <code>pip install -r requirements.txt</code></p></div>
                <div 
