# NOCTURNO Bot

A Highrise virtual-world bot with a Flask web dashboard for monitoring.

## Stack
- **Python 3.12**
- **highrise-bot-sdk** — connects the bot to a Highrise room
- **Flask + Gunicorn** — web dashboard served on port 5000

## How to run
The single workflow `Start application` runs `python run.py`, which:
1. Starts the Flask dashboard on port 5000
2. Spawns the Highrise bot (`main.py`) as a subprocess

## Configuration
All bot settings live in `config.json` (API token, room ID, owner ID, etc.).  
See `config.example.json` for the full reference.  
The dashboard login password is set via the `"password"` key in `config.json`.

## Installing dependencies
Pendulum (a `highrise-bot-sdk` transitive dep) must be installed without build-isolation:

```bash
pip install pendulum --no-build-isolation
pip install highrise-bot-sdk --no-deps
pip install flask requests aiohttp cattrs quattro gunicorn
```

## Known fixes applied
- **Announcement spam fix**: `attempt_reconnection()` now cancels any running announcement/console/inventory tasks before recreating them, preventing duplicate tasks from stacking up on reconnect events.
- `start_announcements()` now properly re-raises `asyncio.CancelledError` so cancelled tasks exit cleanly.

## User preferences
- Spanish-language project (comments, logs, and UI are in Spanish).
