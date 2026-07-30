import sqlite3
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
            used_free_trial INTEGER DEFAULT 0,
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
    
    # Bots Alojados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hosted_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT,
            category TEXT,
            room_id TEXT,
            api_token TEXT,
            status TEXT DEFAULT 'stopped'
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
    cursor.execute("SELECT gold_balance, used_free_trial, pending_gift_from FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id, username, gold_balance, used_free_trial) VALUES (?, ?, 0, 0)", (user_id, username))
        conn.commit()
        conn.close()
        return {"balance": 0, "free_trial": False, "gift_from": None}
        
    conn.close()
    return {"balance": row[0], "free_trial": bool(row[1]), "gift_from": row[2]}

def update_gold(user_id: str, amount: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, gold_balance) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET gold_balance = gold_balance + ?
    """, (user_id, amount, amount))
    conn.commit()
    conn.close()

def mark_free_trial_used(user_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET used_free_trial = 1 WHERE user_id = ?", (user_id,))
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
    cursor.execute("SELECT id, room_id, status, category FROM hosted_bots WHERE owner_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def create_bot_entry(owner_id: str, category: str, room_id: str, api_token: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hosted_bots (owner_id, category, room_id, api_token, status)
        VALUES (?, ?, ?, ?, 'active')
    """, (owner_id, category, room_id, api_token))
    bot_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return bot_id

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
  
