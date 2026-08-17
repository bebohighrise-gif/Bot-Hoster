import subprocess
import sys
import json
import os
import threading
import http.server
import socketserver
from datetime import datetime

def generar_html():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}

    room_id = config.get("ROOM_ID", "No configurado")
    owner_id = config.get("HOSTER_OWNER_ID", "No configurado")
    api_token = config.get("BOT_API_TOKEN", "No configurado")
    api_token_masked = api_token[:10] + "..." if len(api_token) > 10 else api_token

    categories = []
    if os.path.isdir("templates"):
        for item in os.listdir("templates"):
            if os.path.isdir(os.path.join("templates", item)):
                categories.append(item)
    else:
        categories = ["musica", "juegos", "fiesta", "personalizado"]

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

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nex-Host</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: system-ui, sans-serif; background: #0b0e1a; color: #e4e7f0; line-height:1.6; padding:2rem; }}
        .container {{ max-width:900px; margin:0 auto; }}
        h1 {{ font-size:2.5rem; font-weight:700; }}
        h1 span {{ color:#7c3aed; }}
        .card {{ background:#131826; border-radius:1rem; padding:1.5rem; margin:1.5rem 0; border:1px solid #1e2438; }}
        .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:1rem; }}
        .stat {{ text-align:center; }}
        .stat .number {{ font-size:2rem; font-weight:700; color:#7c3aed; }}
        .stat .label {{ color:#8892b0; font-size:0.9rem; }}
        .badge {{ display:inline-block; background:#2a2f4a; padding:0.2rem 0.8rem; border-radius:1rem; font-size:0.8rem; margin:0.2rem; }}
        .badge.admin {{ background:#7c3aed; color:#fff; }}
        footer {{ margin-top:2rem; color:#8892b0; text-align:center; font-size:0.9rem; }}
        a {{ color:#7c3aed; text-decoration:none; }}
    </style>
</head>
<body>
<div class="container">
    <h1>Nex<span>Host</span></h1>
    <p style="color:#b0b8d1; margin-bottom:1.5rem;">Bot Hoster para Highrise · 24/7</p>

    <div class="card">
        <div class="grid">
            <div class="stat"><div class="number">24/7</div><div class="label">Disponibilidad</div></div>
            <div class="stat"><div class="number">{bots_count}</div><div class="label">Bots activos</div></div>
            <div class="stat"><div class="number">{render_port}</div><div class="label">Puerto</div></div>
        </div>
    </div>

    <div class="card">
        <h3 style="margin-bottom:0.5rem;">Configuración actual</h3>
        <p><strong>Room ID:</strong> {room_id}</p>
        <p><strong>Owner ID:</strong> {owner_id}</p>
        <p><strong>API Token:</strong> {api_token_masked}</p>
        <p><strong>Categorías:</strong> {', '.join(categories)}</p>
    </div>

    <div class="card">
        <h3 style="margin-bottom:0.5rem;">Características</h3>
        <p>✔ Alojamiento 24/7 &nbsp;✔ Sistema de saldo (Gold) &nbsp;✔ Asistente paso a paso</p>
        <p>✔ Tiempos flexibles (15m – 100d) &nbsp;✔ Copiar outfit &nbsp;✔ Auto‑mantenimiento</p>
    </div>

    <div class="card">
        <h3 style="margin-bottom:0.5rem;">Comandos principales</h3>
        <p><code>!menu</code> <code>!saldo</code> <code>!plan</code> <code>!buy</code> <code>!mybots</code> <code>!gift</code></p>
        <p><span class="badge admin">Admin</span> <code>!giftbot</code> <code>!addgold</code> <code>!mantenimiento</code> <code>!copy</code></p>
    </div>

    <div class="card">
        <h3 style="margin-bottom:0.5rem;">Tiempos dinámicos</h3>
        <p>10m 15m 45m 1h 6h 18h 1d 7d 30d 100d</p>
    </div>

    <footer>
        <p>Nex-Host · {now}</p>
        <p style="font-size:0.8rem;"><i class="fas fa-code"></i> con ❤️ para la comunidad</p>
    </footer>
</div>
</body>
</html>"""
    return html

class WebHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            html = generar_html()
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404")

def start_web_server():
    port = int(os.environ.get("PORT", 8000))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", port), WebHandler) as httpd:
        print(f"🌐 Web en http://0.0.0.0:{port}/")
        httpd.serve_forever()

def run_bot():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ No se encontró config.json")
        sys.exit(1)
    room_id = config.get("ROOM_ID")
    api_token = config.get("BOT_API_TOKEN")
    if not room_id or not api_token:
        print("❌ Faltan ROOM_ID o BOT_API_TOKEN en config.json")
        sys.exit(1)
    print("🤖 Iniciando bot...")
    subprocess.run([sys.executable, "-m", "highrise", "main:BotHoster", room_id, api_token], check=True)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    start_web_server()
