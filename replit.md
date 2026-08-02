# Nex-Host Bot Hoster

Bot de hosting para Highrise. Permite que usuarios compren o reciban bots alojados directamente desde la sala de Highrise.

## Cómo correr

El workflow **Bot Hoster** ejecuta `python run.py`, que lee las credenciales de `config.json` y lanza el bot con el SDK de Highrise (v25.1.0).

```bash
python run.py
```

> **Runtime**: Python 3.11. Todas las dependencias instaladas vía pip en `.pythonlibs`.

## Configuración

Edita `config.json` con tus credenciales:
- `ROOM_ID` — ID de la sala donde vive el bot hoster
- `HOSTER_OWNER_ID` — Tu ID de usuario en Highrise (acceso al panel admin)
- `BOT_API_TOKEN` — Token del bot hoster (generado desde la app de Highrise)

## Estructura

- `main.py` — Lógica principal del bot (comandos, compras, admin)
- `database.py` — Base de datos SQLite (usuarios, bots alojados, categorías)
- `config.py` — Carga de configuración desde `config.json`
- `run.py` — Script de arranque
- `templates/` — Plantillas de bots para desplegar (`fiesta/`, `fiestamusica/`)
- `hosted_instances/` — Instancias activas generadas automáticamente

## Comandos disponibles (por inbox de Highrise)

| Comando | Descripción |
|---|---|
| `!menu` | Muestra el menú principal |
| `!saldo` | Consulta tu saldo |
| `!plan` | Ver categorías y precios |
| `!buy <cat> <token> <room_id>` | Comprar un bot |
| `!gift <user_id> <monto>` | Regalar saldo |
| `!mybots` | Ver tus bots alojados |

### Comandos admin (solo propietario)

| Comando | Descripción |
|---|---|
| `!giftbot` | Regalar bot paso a paso |
| `!addgold <user_id> <cantidad>` | Añadir oro a usuario |
| `!mantenimiento <cat> <on/off>` | Poner categoría en mantenimiento |
| `!detener / !activar <cat>` | Activar/desactivar categoría |
