import sqlite3
import re
from datetime import datetime, timedelta
from config import DB_NAME

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Usuarios y Saldos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            gold_balance INTEGER DEFAULT 0,
            pending_gift_from TEXT DEFAULT NULL,
            conversation_id TEXT DEFAULT NULL,
            is_banned INTEGER DEFAULT 0,
            host_language TEXT DEFAULT 'es'
        )
    """)

    # Categorías Mantenimiento/Activación
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_status (
            category TEXT PRIMARY KEY,
            is_active INTEGER DEFAULT 1,
            in_maintenance INTEGER DEFAULT 0
        )
    """)

    # Bots Alojados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hosted_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT,
            category TEXT,
            room_id TEXT,
            api_token TEXT,
            status TEXT DEFAULT 'stopped',
            expires_at TEXT DEFAULT NULL,
            bot_language TEXT DEFAULT 'es'
        )
    """)

    # Tickets de Soporte
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            username TEXT,
            message TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)

    # Migraciones seguras para columnas nuevas
    cursor.execute("PRAGMA table_info(users)")
    existing_user_cols = [row[1] for row in cursor.fetchall()]
    if "conversation_id" not in existing_user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN conversation_id TEXT DEFAULT NULL")
    if "is_banned" not in existing_user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
    if "host_language" not in existing_user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN host_language TEXT DEFAULT 'es'")

    cursor.execute("PRAGMA table_info(hosted_bots)")
    existing_bot_cols = [row[1] for row in cursor.fetchall()]
    if "bot_language" not in existing_bot_cols:
        cursor.execute("ALTER TABLE hosted_bots ADD COLUMN bot_language TEXT DEFAULT 'es'")

    categories = ['musica', 'juegos', 'fiesta', 'personalizado']
    for cat in categories:
        cursor.execute(
            "INSERT OR IGNORE INTO category_status (category, is_active, in_maintenance) VALUES (?, 1, 0)",
            (cat,))

    conn.commit()
    conn.close()


def save_conversation_id(user_id: str, conversation_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, conversation_id) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET conversation_id = ?
    """, (user_id, conversation_id, conversation_id))
    conn.commit()
    conn.close()


def get_all_users_with_conversations():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, conversation_id FROM users WHERE conversation_id IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_or_create_user(user_id: str, username: str = "Usuario"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT gold_balance, pending_gift_from, is_banned FROM users WHERE user_id = ?",
        (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute(
            "INSERT INTO users (user_id, username, gold_balance) VALUES (?, ?, 0)",
            (user_id, username))
        conn.commit()
        conn.close()
        return {"balance": 0, "gift_from": None, "is_banned": 0}
    conn.close()
    return {"balance": row[0], "gift_from": row[1], "is_banned": row[2] if row[2] else 0}


def update_gold(user_id: str, amount: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, gold_balance) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET gold_balance = gold_balance + ?
    """, (user_id, amount, amount))
    conn.commit()
    conn.close()


def clear_pending_gift(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET pending_gift_from = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def set_pending_gift(target_id: str, sender_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, pending_gift_from) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET pending_gift_from = ?
    """, (target_id, sender_name, sender_name))
    conn.commit()
    conn.close()


def get_active_bot_instances():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT owner_id, category FROM hosted_bots WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_user_bots(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, room_id, status, category, expires_at FROM hosted_bots "
        "WHERE owner_id = ? AND status = 'active'",
        (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_bot_by_id(bot_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, owner_id, category, room_id, api_token, status, expires_at "
        "FROM hosted_bots WHERE id = ?",
        (bot_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "owner_id": row[1], "category": row[2],
                "room_id": row[3], "api_token": row[4], "status": row[5], "expires_at": row[6]}
    return None


def create_bot_entry(owner_id: str, category: str, room_id: str, api_token: str,
                     duration_str: str = None):
    conn = get_connection()
    cursor = conn.cursor()

    expires_at = None
    if duration_str:
        duration_str = duration_str.lower().strip()
        match = re.match(r"^(\d+)([mhd])$", duration_str)
        if match:
            value = int(match.group(1))
            unit  = match.group(2)
            now   = datetime.utcnow()
            if unit == 'm':
                expiration_date = now + timedelta(minutes=value)
            elif unit == 'h':
                expiration_date = now + timedelta(hours=value)
            elif unit == 'd':
                expiration_date = now + timedelta(days=value)
            expires_at = expiration_date.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO hosted_bots (owner_id, category, room_id, api_token, status, expires_at)
        VALUES (?, ?, ?, ?, 'active', ?)
    """, (owner_id, category, room_id, api_token, expires_at))
    bot_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return bot_id, expires_at


def get_expired_bots():
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        SELECT id, owner_id, category
        FROM hosted_bots
        WHERE status = 'active'
          AND expires_at IS NOT NULL
          AND expires_at <= ?
    """, (now,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def mark_bot_expired(bot_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE hosted_bots SET status = 'expired' WHERE id = ?", (bot_id,))
    conn.commit()
    conn.close()


def set_maintenance(category: str, state: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE category_status SET in_maintenance = ? WHERE category = ?",
        (state, category.lower()))
    conn.commit()
    conn.close()


def set_active_status(category: str, state: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE category_status SET is_active = ? WHERE category = ?",
        (state, category.lower()))
    conn.commit()
    conn.close()


def get_category_info(category: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_active, in_maintenance FROM category_status WHERE category = ?",
        (category.lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"active": bool(row[0]), "maintenance": bool(row[1])}
    return {"active": True, "maintenance": False}


# ─── FUNCIONES NUEVAS ────────────────────────────────────────────────

def get_stats():
    """Estadísticas generales del sistema."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM hosted_bots WHERE status = 'active'")
    active_bots = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'pending'")
    pending_tickets = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(gold_balance), 0) FROM users")
    total_gold = cursor.fetchone()[0]
    conn.close()
    return {
        "active_bots":      active_bots,
        "total_users":      total_users,
        "pending_tickets":  pending_tickets,
        "total_gold":       total_gold,
    }


def get_user_detail(user_id: str):
    """Devuelve info básica de un usuario."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, username, gold_balance FROM users WHERE user_id = ?",
        (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "username": row[1], "balance": row[2]}
    return None


def get_all_registered_users():
    """Usuarios con saldo > 0 o bots activos, ordenados por saldo."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT u.user_id, u.username, u.gold_balance
        FROM users u
        LEFT JOIN hosted_bots hb ON hb.owner_id = u.user_id AND hb.status = 'active'
        WHERE u.gold_balance > 0 OR hb.id IS NOT NULL
        ORDER BY u.gold_balance DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def create_ticket(user_id: str, username: str, message: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO tickets (user_id, username, message, created_at, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (user_id, username, message, now))
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ticket_id


def get_next_pending_ticket():
    """Devuelve el ticket más antiguo pendiente."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, message, created_at
        FROM tickets
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "user_id": row[1], "username": row[2],
                "message": row[3], "created_at": row[4]}
    return None


def mark_ticket_resolved(ticket_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()


def get_pending_ticket_by_user(user_id: str):
    """Devuelve el ticket pendiente más reciente de un usuario."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, username, message, created_at
        FROM tickets
        WHERE user_id = ? AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "user_id": row[1], "username": row[2],
                "message": row[3], "created_at": row[4]}
    return None


def ban_user(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, is_banned) VALUES (?, 1)
        ON CONFLICT(user_id) DO UPDATE SET is_banned = 1
    """, (user_id,))
    conn.commit()
    conn.close()


def unban_user(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def extend_bot_time(bot_id: int, duration_str: str):
    """Extiende la expiración de un bot activo. Retorna la nueva fecha o None si falla."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT expires_at FROM hosted_bots WHERE id = ? AND status = 'active'",
        (bot_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    match = re.match(r"^(\d+)([mhd])$", duration_str.lower().strip())
    if not match:
        conn.close()
        return None

    value = int(match.group(1))
    unit  = match.group(2)

    if row[0]:
        try:
            base = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            base = datetime.utcnow()
    else:
        base = datetime.utcnow()

    if unit == 'm':
        new_exp = base + timedelta(minutes=value)
    elif unit == 'h':
        new_exp = base + timedelta(hours=value)
    else:
        new_exp = base + timedelta(days=value)

    new_exp_str = new_exp.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE hosted_bots SET expires_at = ? WHERE id = ?", (new_exp_str, bot_id))
    conn.commit()
    conn.close()
    return new_exp_str


def update_bot_room(bot_id: int, new_room_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE hosted_bots SET room_id = ? WHERE id = ?", (new_room_id, bot_id))
    conn.commit()
    conn.close()


def set_bot_language(bot_id: int, language: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE hosted_bots SET bot_language = ? WHERE id = ?", (language, bot_id))
    conn.commit()
    conn.close()


def set_user_host_language(user_id: str, language: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, host_language) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET host_language = ?
    """, (user_id, language, language))
    conn.commit()
    conn.close()
