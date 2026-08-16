# Nocturno DJ Bot Pro v7.0

## How to run
Starts automatically via the **DJ Bot Pro v7.0 (Final)** workflow (`python run.py`).
- Web panel on port 5000 — login password default: `070927` (change via `DJ_PASSWORD` env var)
- Radio streams audio from the `music/` folder (put MP3/WAV/FLAC/OGG/etc. files there)
- No Google Drive or Highrise required
- YouTube requests are played through a temporary live audio URL, with FFmpeg fade-in/out, and are not saved locally

## Music
All songs live in `music/`. You can:
- Drop files directly into the `music/` folder
- Upload via the web panel (Upload button)
- Request a song with `/play <name or link>` — yt-dlp only resolves its temporary audio URL, then FFmpeg streams it directly

## Nocturno DJ Bot Application

## Overview

This project is a Python-based Highrise bot application designed to manage automated interactions, user moderation, and special features within a Highrise virtual room. Its primary purpose is to create an engaging and controlled environment by handling user permissions, automating emotes, managing spatial zones, tracking user activity, and implementing a heart-based economy system. The project aims to provide a robust and automated presence that enhances the user experience within the Highrise platform.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Bot Architecture

The bot uses an event-driven architecture built on the Highrise SDK's `BaseBot` class, leveraging async/await patterns for real-time event handling. Key design decisions include:
- Asynchronous event handlers for chat messages, user lifecycle events, and position changes.
- Centralized configuration via `config.json` for room settings and zone definitions.
- Secrets-based credential management using environment variables for sensitive data.
- File-based persistence for user data (hearts, activity, user info, bans, mutes) to simplify deployment.
- A logging system writes operational and interaction data to `bot_log.txt`.

### Authorization & User Management

A role-based access control system with four tiers (Owner, Admins, Moderators, VIP Users) manages hierarchical permissions. User IDs are loaded from `config.json` (no longer dependent on secrets for local deployment). VIP status and banned/muted users are tracked at runtime and persisted to files.

**Recent Changes (Oct 31, 2025):**
- Removed all dependencies on environment variables/secrets for easier local deployment
- Owner and Admin now have unrestricted access to ALL commands without exceptions
- Owner and Admin bypass all zone restrictions including forbidden zones

### Spatial Zone Management

The system implements coordinate-based zone management, including VIP, DJ, Management, Forbidden, and Jail Zones. It uses Euclidean distance calculations to restrict access and automatically teleport unauthorized users from restricted areas.

**Jail Zone System:**
- Jail zone is a special restricted zone that can only be accessed by users who are sent there by Admin/Owner
- Admin/Owner can send users to jail using `!jail @username` command
- Admin/Owner can free users from jail using `!unjail @username` command
- Users in jail are tracked in the `JAIL_USERS` set
- Regular users cannot voluntarily access the jail zone
- Admin and Owner always have unrestricted access to all zones including jail and forbidden zones

### Economy System

A heart-based virtual economy allows users to earn hearts through activity, transfer them, and enables the bot to manage its own wallet. Hearts are tracked in a dictionary and persisted to `data/hearts.txt`.

### Automated Bot Behavior

The bot features an automated emote cycling system that plays predefined emotes to maintain an active visual presence. This cycle can be interrupted by manual commands. Initial outfit and emote sets are configured via `config.json`.

### Activity Tracking

User engagement is monitored through a multi-metric tracking system that records message counts, last activity timestamps, and join times. This data is persisted to `data/activity.txt` and used for automatic rewards.

### Logging & Monitoring

A structured logging system categorizes events (BOT, CHAT, ADMIN, MOD, ERROR, WARNING), includes timestamps, and stores entries in `bot_log.txt`. Critical events are also output to the console.

### Data Persistence Strategy

A hybrid approach uses JSON files for structured data (`user_info.json`) and plain text files for simple key-value data (`hearts.txt`, `activity.txt`), all organized under the `data/` directory. This strategy prioritizes simplicity and ease of deployment over high-concurrency performance.

### Command System

A unified, three-layer command handling system processes user interactions from both public chat and private whispers. The `handle_command` method acts as a central processor, routing responses contextually via a `send_response()` helper function and enforcing role-based access control.

### Bot Secundario

Se puede operar un segundo bot con un sistema de bucle de emotes configurable. Comparte el ID de la sala y del propietario con el bot principal, pero utiliza un token de API independiente y una configuración mínima.

**Emote System:**
- Starts with "ghostfloat" (emote-ghost-idle) by default
- Admin/Owner can change the emote in loop using `!secemote <emote_id>`
- Admin/Owner can stop/start the loop with `!secstop` and `!secstart`
- Admin/Owner can check status with `!secstatus`
- Executes configured emote every 18 seconds to avoid rate limiting

## External Dependencies

- **Highrise SDK**: The primary API for interacting with the Highrise platform, providing `BaseBot` and event handlers. Authentication uses API tokens from environment variables.
- **Python Standard Library**: Utilized for asynchronous operations (`asyncio`), data serialization (`json`), timestamp management (`datetime`, `time`), and type hinting (`typing`).
- **File System**: Used for configuration (`config.json`, `secundario_config.json`), logging (`bot_log.txt`), and data storage (`data/` directory for user info, hearts, activity).
- **Configuration Files**: All credentials (API tokens, Room IDs, user IDs) are loaded from `config.json` and `secundario_config.json` for easy local deployment.
- **No External Database**: The project intentionally avoids external database dependencies, relying solely on file-based storage.

## Recent Updates

### January 27, 2026
- **Sistema de comandos completo implementado**:
  
  **Comandos de Usuario Normal:**
  - `/play <nombre o link>` - Añade una canción a la cola
  - `/fav` - Muestra tus canciones favoritas
  - `/fav clear` - Elimina todas tus canciones favoritas
  - `/favr <nombre>` - Añade una canción a favoritos
  - `/profile` - Muestra tu historial de canciones pedidas
  - `/q` - Muestra la cola de reproducción actual
  - `/pedidos` - Muestra cuántos pedidos activos tienes
  - `/lista` - Muestra la música local numerada
  - `/help` - Lista de comandos disponibles
  - `/stream` - URL de la emisora en streaming
  
  **Comandos de Admin/Owner:**
  - `/stop` - Detiene la reproducción
  - `/next` - Salta a la siguiente canción
  - `/prev` - Vuelve a la canción anterior
  - `/pause` - Pausa la canción actual
  - `/resume` - Reanuda la canción pausada
  - `/auto <mensaje>` - Configura mensaje automático periódico
  - `/autostop` - Detiene el mensaje automático
  - `/copy` - Copia outfit del admin
  - `/cambiar <número>` - Cambia el precio de pedidos
  - `/delete @user` - Bloquea a un usuario del bot
  - `/ancla` - Define la posición de inicio del bot

- **Nuevas funcionalidades:**
  - Sistema de favoritos por usuario (favorites.json)
  - Historial de canciones por usuario
  - Sistema de bloqueo de usuarios (banned.json)
  - Canción anterior (prev) disponible
  - Mensajes automáticos configurables

### January 26, 2026
- **Dependencias corregidas**: Instaladas yt-dlp, pydub y ffmpeg que faltaban
- **Bot integrado con Highrise**: Creado `highrise_bot.py` que conecta correctamente con el SDK de Highrise
- **Comandos disponibles en el chat de Highrise**:
  - `/play <cancion o URL>` - Reproducir musica de YouTube en streaming
  - `/queue` - Ver cola de reproduccion
  - `/now` - Cancion actual
  - `/stream` - Obtener URL de streaming
  - `/skip` - Saltar cancion (solo Admin)
  - `/help` - Ver ayuda
- **Panel web en puerto 5000**: Muestra cancion actual, permite subir MP3, y proporciona URL de streaming
- **Codigo refactorizado**: run.py ahora inicia radio, bot de Highrise y servidor web en paralelo

### November 10, 2025 (Tarde)
- **Bloqueo de emotes no gratuitos en bot principal**:
  - Implementado set `DISABLED_EMOTE_IDS` con 4 emotes no gratuitos: emote-kissing-passionate (kiss), emoji-shake-head (shakehead), emoji-nod (nod), emoji-hello (hello)
  - Agregada validación en todos los puntos de ejecución de emotes para rechazar emotes deshabilitados
  - Los usuarios reciben el mensaje "🚫 Emote deshabilitado" cuando intentan usar un emote bloqueado
  - Validación aplicada en: ejecución por número, comando !emote, ejecución rápida, emotes mutuos y ciclo automático
- **Eliminación de lista de emotes en bot secundario**:
  - Eliminado método `start_auto_emote_cycle` y su lista de 224 emotes del bot secundario
  - Comando `!automode` ahora responde "🚫 Modo automático deshabilitado"
  - Bot secundario sigue usando únicamente su emote por defecto (emote-ghost-idle / ghostfloat) en bucle
  - Simplificación del código del bot secundario al eliminar funcionalidad no utilizada

### Sistema de Salud de Emotes ELIMINADO:
- Eliminado completamente el sistema EmoteHealthManager de ambos bots (bot principal y bot secundario)
- Eliminados comandos `!emotestats` y `!emotereset` del bot principal
- Eliminados archivos de persistencia `data/emote_health.json` y `data/secundario_emote_health.json`
- Todos los emotes deshabilitados fueron rehabilitados
- Los emotes ahora se ejecutan sin validación de salud
- **Bot Secundario**: Mantiene el emote 140 (emote-ghost-idle / ghostfloat) como emote por defecto
  - **Emotes NO gratuitos identificados**: emote-kissing-passionate (kiss), emoji-shake-head (shakehead), emoji-nod (nod), emoji-hello (hello)
  - Simplificación del código: reducido manejo de errores a detección básica de errores de transporte

### November 4, 2025 (Tarde)
- **Sistema de Gestión de Salud de Emotes (EmoteHealthManager)** [ELIMINADO EN NOV 10]:
  - Implementado sistema inteligente que detecta y deshabilita automáticamente emotes problemáticos que causan desconexiones del bot
  - **Persistencia completa**: Todos los datos se guardan en `data/emote_health.json` y sobreviven reinicios del bot
  - **Umbrales automáticos**:
    - 3 fallos consecutivos → emote en cooldown temporal (24 horas)
    - 5 fallos consecutivos → emote deshabilitado permanentemente
    - Detección inteligente de errores de transporte vs. errores normales
  - **Backoff exponencial**: Si hay 3+ errores de transporte consecutivos, el bot aborta el ciclo actual y espera antes de reintentar (evita desconexiones)
  - **Nuevos comandos de administrador**:
    - `!emotestats` - Ver estadísticas de salud de emotes y lista de emotes deshabilitados (Admin/Owner)
    - `!emotereset [emote_id]` - Reiniciar estado de un emote específico o todos los emotes (Owner)
  - **Logs mejorados**: Reporta emotes en cuarentena, emotes omitidos y estadísticas de salud en cada ciclo
  - **Balance I/O**: Guarda estado inmediatamente en cambios críticos (nuevos emotes, fallos, recuperaciones) y cada 20 éxitos para emotes conocidos
- **Emotes optimizados**: Eliminados los emotes "icon" (key 49) y "omg" (key 45) del catálogo
- **Bucle de emotes mejorado**: Reducido el tiempo de espera en `send_emote_loop` a `max(0.1, duration - 0.3)` para eliminar pausas visibles y lograr un flujo continuo sin interrupciones
- **Logging del bot secundario mejorado**: Agregados timestamps, tipos de error detallados y traceback completo para mejor debugging
- **Corrección de bug**: Agregada verificación `if self.bot_id` antes de teleportar en `attempt_reconnection` para evitar errores cuando bot_id es None
- **Sistema de bienvenida confiable**: Implementado sistema de reintentos (3 intentos con delays incrementales) en ambos bots para garantizar que los mensajes de bienvenida lleguen a todos los usuarios, evitando problemas de rate limiting de la API
- **Prevención de desconexiones del bot secundario**: 
  - Reducida frecuencia de emotes de 11.8s a 18s para evitar rate limiting (~3 emotes/min vs ~5 antes)
  - Implementado backoff exponencial en caso de errores (10s, 20s, 40s)
  - Reducida frecuencia de verificaciones de reconexión de 15s a 30s para menor carga en API
  - Eliminado keepalive redundante que duplicaba llamadas pesadas a la API
  - Mejorado manejo de errores con contadores y límites inteligentes
- **Sistema de emotes configurables para bot secundario**:
  - Convertido floss automático a sistema de emotes configurables
  - Bot inicia con "ghostfloat" (emote-ghost-idle) por defecto
  - Nuevos comandos solo para admin/owner:
    - `!secemote <emote_id>` - Cambiar emote en bucle
    - `!secstop` - Detener emote en bucle
    - `!secstart` - Reanudar emote en bucle
    - `!secstatus` - Ver estado actual del emote
  - Sistema flexible que permite usar cualquier emote de Highrise

### October 31, 2025
- **Removed secrets dependency**: All configuration now uses `config.json` files for easier local PC deployment
- **Enhanced permissions**: Owner and Admin now have unrestricted access to ALL commands and zones
- **Jail system**: Added `!jail` and `!unjail` commands for sending users to a restricted jail zone
- **Zone restrictions**: Admin/Owner bypass all forbidden zone restrictions
- **Owner ID updated**: Changed to `64dc252537db1cdb8e202d8d`