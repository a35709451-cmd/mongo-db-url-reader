import sqlite3
import os
import time

DB_PATH = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at INTEGER
        )
    """)
    
    # Create sessions table to persist active mongodb connections
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER PRIMARY KEY,
            mongo_url TEXT,
            current_db TEXT,
            current_coll TEXT,
            updated_at INTEGER
        )
    """)
    
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, int(time.time()))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error in add_user: {e}")

def get_users_count():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"Error in get_users_count: {e}")
        return 0

def get_all_users():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception as e:
        print(f"Error in get_all_users: {e}")
        return []

def save_session(user_id, mongo_url, current_db=None, current_coll=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO sessions (user_id, mongo_url, current_db, current_coll, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, mongo_url, current_db, current_coll, int(time.time()))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error in save_session: {e}")

def get_session(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT mongo_url, current_db, current_coll FROM sessions WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"mongo_url": row[0], "current_db": row[1], "current_coll": row[2]}
        return None
    except Exception as e:
        print(f"Error in get_session: {e}")
        return None

def update_session_db_coll(user_id, current_db, current_coll):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET current_db = ?, current_coll = ?, updated_at = ? WHERE user_id = ?",
            (current_db, current_coll, int(time.time()), user_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error in update_session_db_coll: {e}")

def delete_session(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error in delete_session: {e}")

# Initialize database on import
init_db()
