import subprocess
import sys
import json
import os
import argparse
import threading
import http.server
import socketserver
from datetime import datetime

# ---------- GENERAR WEB (igual que antes, pero ahora se guarda en la raíz) ----------
def generate_web():
    # Cargar configuración
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ No se encontró config.json")
        return

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

    # Obtener puerto de Render
    render_port = os.environ.get("PORT", "No definido (Render asigna automáticamente)")

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Aquí insertas la plantilla HTML (exactamente la misma que te di antes)
    # Para no repetir todo el HTML aquí, pondré un marcador.
    # Pero en el código final debe ir el HTML completo.
    # Como es extenso, lo omito en este mensaje, pero lo incluiré en el script final.

    # ...

    # Escribir index.html en la raíz
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)  # Aquí html debe ser la string con toda la plantilla

    print("✅ Página web generada correctamente en la raíz: index.html")
    print(f"📁 Categorías detectadas: {', '.join(categories)}")
    print(f"🌐 Puerto para Render: {render_port}")


# ---------- SERVIDOR WEB PARA MANTENER ACTIVO ----------
def start_web_server():
    port = int(os.environ.get("PORT", 8000))
    handler = http.server.SimpleHTTPRequestHandler

    # Personalizamos el manejador para responder a /ping
    class CustomHandler(handler):
        def do_GET(self):
            if self.path == "/ping":
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
                return
            # Para cualquier otra ruta, servir archivos estáticos desde el directorio actual
            return handler.do_GET(self)

    with socketserver.TCPServer(("0.0.0.0", port), CustomHandler) as httpd:
        print(f"🌐 Servidor web iniciado en el puerto {port}")
        print(f"   - Página principal: http://localhost:{port}/index.html")
        print(f"   - Health check: http://localhost:{port}/ping")
        httpd.serve_forever()


# ---------- FUNCIÓN PARA EJECUTAR EL BOT ----------
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

    print("🤖 Iniciando el bot de Highrise...")
    subprocess.run(
        [sys.executable, "-m", "highrise", "main:BotHoster", room_id, api_token],
        check=True
    )


# ---------- MAIN ----------
def main():
    parser = argparse.ArgumentParser(description="Nex-Host Bot Hoster")
    parser.add_argument("--web", action="store_true", help="Generar página web con los datos del bot y salir")
    args = parser.parse_args()

    if args.web:
        generate_web()
        return

    # Ejecución normal: lanzar el bot en un hilo y el servidor web en el principal
    # (o viceversa, da igual)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Iniciar servidor web (bloquea)
    start_web_server()


if __name__ == "__main__":
    main()
