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
            pending_gift_from TEXT DEFAULT NULL
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
    
    # Bots Alojados (Expiración en fecha ISO)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hosted_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT,
            category TEXT,
            room_id TEXT,
            api_token TEXT,
            status TEXT DEFAULT 'stopped',
            expires_at TEXT DEFAULT NULL
        )
    """)
    
    categories = ['musica', 'juegos', 'fiesta', 'personalizado']
    for cat in categories:
        cursor.execute("INSERT OR IGNORE INTO category_status (category, is_active, in_maintenance) VALUES (?, 1, 0)", (cat,))
        
    conn.commit()
    conn.close()

def get_or_create_user(user_id: str, username: str = "Usuario"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT gold_balance, pending_gift_from FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id, username, gold_balance) VALUES (?, ?, 0)", (user_id, username))
        conn.commit()
        conn.close()
        return {"balance": 0, "gift_from": None}
        
    conn.close()
    return {"balance": row[0], "gift_from": row[1]}

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

def get_user_bots(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, room_id, status, category, expires_at FROM hosted_bots WHERE owner_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def create_bot_entry(owner_id: str, category: str, room_id: str, api_token: str, duration_str: str = None):
    """
    Soporta cualquier tiempo dinámico ingresado:
    - Minutos: "15m", "45m", "120m"...
    - Horas:   "1h", "6h", "36h"...
    - Días:    "1d", "15d", "90d"...
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    expires_at = None
    if duration_str:
        duration_str = duration_str.lower().strip()
        match = re.match(r"^(\d+)([mhd])$", duration_str)
        
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            
            now = datetime.utcnow()
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
    """Devuelve lista de (bot_id, owner_id, category) de bots activos que ya expiraron."""
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
    """Marca un bot como expirado en la base de datos."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE hosted_bots SET status = 'expired' WHERE id = ?", (bot_id,))
    conn.commit()
    conn.close()

def set_maintenance(category: str, state: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE category_status SET in_maintenance = ? WHERE category = ?", (state, category.lower()))
    conn.commit()
    conn.close()

def set_active_status(category: str, state: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE category_status SET is_active = ? WHERE category = ?", (state, category.lower()))
    conn.commit()
    conn.close()

def get_category_info(category: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active, in_maintenance FROM category_status WHERE category = ?", (category.lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"active": bool(row[0]), "maintenance": bool(row[1])}
    return {"active": True, "maintenance": False}
