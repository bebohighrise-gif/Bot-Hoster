# 🤖 Nex-Host — Bot Hoster para Highrise

**Nex-Host** es una plataforma automatizada en Python diseñada para gestionar, alojar y desplegar bots para Highrise en tiempo real y 24/7. El sistema opera a través del inbox privado del bot principal, ofreciendo un menú interactivo para usuarios, sistema de saldo virtual, tienda de bots y un panel de administración para el propietario.

---

## 🚀 Características Principales

* **Alojamiento 24/7:** Despliegue de instancias independientes de bots que corren de manera continua.
* **Sistema de Saldo (Gold):** Recarga automática de saldo mediante donaciones / tips de oro en la sala.
* **Flujo Paso a Paso (`!giftbot`):** Asistente guiado e interactivo por privado para regalar bots sin escribir comandos largos o complejos.
* **Tiempos de Expiración Flexibles:** Asignación de tiempo de vida totalmente personalizado para bots regalados o de prueba (`15m`, `45m`, `3h`, `12h`, `30d`, etc.).
* **Gestión Inteligente de Proyectos:**
  * Visualización simplificada: Si un usuario tiene un solo bot, se muestran sus detalles directamente sin cargar listas pesadas.
  * Múltiples bots: Comando `!mybots` para listar todas las instancias activas de un usuario.
* **Copiar Outfit (`!copy`):** Clonación instantánea del outfit del dueño del hoster con un solo comando por **susurro** (whisper).
* **Control de Categorías:** Sistema de mantenimiento y apagado/activación por categorías de bot (`musica`, `juegos`, `fiesta`, `personalizado`).
* **Auto-Mantenimiento:** Al iniciar, el bot detecta automáticamente qué categorías no tienen plantilla y las pone en mantenimiento.
* **Verificador de Expiración:** Loop automático cada 60 segundos que detecta bots expirados, los termina y actualiza la base de datos.

---

## 🛠️ Requisitos del Sistema

* **Python 3.10+**
* Acceso a la API Token de Highrise.

---

## 📦 Instalación y Configuración

1. **Estructura de carpetas:**

   ```text
   nex-host/
   ├── config.py
   ├── config.json
   ├── database.py
   ├── main.py
   ├── run.py
   ├── requirements.txt
   ├── README.md
   ├── templates/          # Plantillas base de los bots
   │   ├── musica/
   │   └── fiesta/
   └── hosted_instances/   # Instancias creadas y ejecutadas en vivo
   ```

2. **Instalar dependencias:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar `config.json`:**

   ```json
   {
     "ROOM_ID": "ID_DE_TU_SALA_DE_HOSTING",
     "HOSTER_OWNER_ID": "TU_HIGHRISE_USER_ID",
     "BOT_API_TOKEN": "API_TOKEN_DEL_BOT_HOSTER"
   }
   ```

4. **Ejecutar el Bot Hoster:**

   ```bash
   python run.py
   ```

---

## 📜 Guía de Comandos

> ⚠️ **Todos los comandos funcionan por Inbox (mensaje privado)**, excepto `!copy` que se envía por **Susurro (Whisper)**.

### 👥 Comandos para Usuarios Generales

| Comando | Descripción |
| :--- | :--- |
| `!menu` | Muestra el menú principal, tu saldo y el estado de tus bots. |
| `!saldo` | Consulta tu balance actual de oro en la plataforma. |
| `!plan` | Muestra el catálogo de categorías disponibles y sus precios. |
| `!buy <CATEGORIA> <TOKEN> <ROOM_ID>` | Compra y despliega una instancia de bot en tu sala. |
| `!mybots` | Lista todos los bots que tienes alojados actualmente. |
| `!gift <USER_ID> <MONTO>` | Transfiere parte de tu saldo a otro usuario. |

### 👑 Comandos de Administración (Exclusivos del Dueño)

| Comando | Tipo | Descripción |
| :--- | :--- | :--- |
| `!giftbot` | Inbox | Inicia el **asistente paso a paso** para regalar una instancia con tiempo personalizado. |
| `!cancel` | Inbox | Cancela el flujo activo de `!giftbot`. |
| `!addgold <USER_ID> <CANTIDAD>` | Inbox | Añade saldo manualmente a la cuenta de cualquier usuario. |
| `!mantenimiento <CATEGORIA> <on/off>` | Inbox | Pone o quita el modo mantenimiento en una categoría. |
| `!detener / !activar <CATEGORIA>` | Inbox | Enciende o apaga la venta de una categoría completa. |
| `!copy` | **Susurro** | Ordena al Bot Hoster copiar exactamente tu outfit actual. |

---

## ⏱️ Formato de Tiempos Dinámicos

En el paso 5 del asistente `!giftbot`, puedes escribir **cualquier tiempo dinámico** sin restricciones:

* **Minutos (m):** `10m`, `15m`, `45m`, `90m`
* **Horas (h):** `1h`, `6h`, `18h`, `36h`
* **Días (d):** `1d`, `7d`, `30d`, `100d`

---

## 🗄️ Base de Datos (SQLite3)

El sistema utiliza **SQLite3** con las siguientes tablas:

1. **`users`** — ID de usuario, nombre, saldo acumulado y notificaciones de regalos pendientes.
2. **`category_status`** — Estado operacional y mantenimiento de cada tipo de bot.
3. **`hosted_bots`** — Instancias creadas, tokens, salas asignadas, estados y fecha exacta de expiración UTC.
