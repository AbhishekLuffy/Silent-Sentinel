import sqlite3
import os
from datetime import datetime
import hashlib

# --- Admin User Management ---
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_database():
    """
    Initialize the SQLite database and create the audio_logs, admin_users, and pending_admins tables if they don't exist.
    """
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()

        # Create audio_logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audio_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                location_url TEXT,
                transcription TEXT
            )
        ''')

        # Create admin_users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')

        # Create pending_admins table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')

        # Create users table (general users who sign up via web)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                address TEXT,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')

        # Ensure address column exists (for upgrades)
        try:
            cursor.execute("SELECT address FROM users LIMIT 1")
        except Exception:
            cursor.execute("ALTER TABLE users ADD COLUMN address TEXT")
        
        # Ensure unique index on phone (login identifier)
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone)')

        conn.commit()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
    finally:
        conn.close()

# --- Pending Admin Registration ---
def register_pending_admin(username, password):
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute('INSERT INTO pending_admins (username, password_hash) VALUES (?, ?)', (username, password_hash))
        conn.commit()
        print(f"✅ Pending admin registered: {username}")
        return True
    except sqlite3.IntegrityError:
        print("❌ Username already exists in pending admins.")
        return False
    except Exception as e:
        print(f"❌ Error registering pending admin: {e}")
        return False
    finally:
        conn.close()

def get_pending_admins():
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, username FROM pending_admins')
        return cursor.fetchall()
    except Exception as e:
        print(f"❌ Error fetching pending admins: {e}")
        return []
    finally:
        conn.close()

def accept_pending_admin(pending_id):
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        # Get the pending admin's info
        cursor.execute('SELECT username, password_hash FROM pending_admins WHERE id=?', (pending_id,))
        row = cursor.fetchone()
        if not row:
            return False
        username, password_hash = row
        # Move to admin_users
        cursor.execute('INSERT INTO admin_users (username, password_hash) VALUES (?, ?)', (username, password_hash))
        # Remove from pending_admins
        cursor.execute('DELETE FROM pending_admins WHERE id=?', (pending_id,))
        conn.commit()
        print(f"✅ Pending admin accepted: {username}")
        return True
    except Exception as e:
        print(f"❌ Error accepting pending admin: {e}")
        return False
    finally:
        conn.close()

def delete_pending_admin(pending_id):
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pending_admins WHERE id=?', (pending_id,))
        conn.commit()
        print(f"✅ Pending admin deleted: {pending_id}")
        return True
    except Exception as e:
        print(f"❌ Error deleting pending admin: {e}")
        return False
    finally:
        conn.close()

# --- Approved Admins ---
def register_admin(username, password):
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute('INSERT INTO admin_users (username, password_hash) VALUES (?, ?)', (username, password_hash))
        conn.commit()
        print(f"✅ Admin registered: {username}")
        return True
    except sqlite3.IntegrityError:
        print("❌ Username already exists.")
        return False
    except Exception as e:
        print(f"❌ Error registering admin: {e}")
        return False
    finally:
        conn.close()

def verify_admin(username, password):
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute('SELECT * FROM admin_users WHERE username=? AND password_hash=?', (username, password_hash))
        result = cursor.fetchone()
        return result is not None
    except Exception as e:
        print(f"❌ Error verifying admin: {e}")
        return False
    finally:
        conn.close()

def insert_audio_log(filename, location_url=None, transcription=None):
    """
    Insert a new audio log entry into the database.
    
    Args:
        filename (str): Name of the audio file
        location_url (str, optional): Google Maps URL of the location
        transcription (str, optional): Transcribed text from the audio
    """
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
            INSERT INTO audio_logs (filename, timestamp, location_url, transcription)
            VALUES (?, ?, ?, ?)
        ''', (filename, timestamp, location_url, transcription))

        conn.commit()
        print(f"✅ Audio log saved to database: {filename}")
    except Exception as e:
        print(f"❌ Error saving to database: {e}")
    finally:
        conn.close()

def get_all_logs():
    """
    Retrieve all audio logs from the database.
    
    Returns:
        list: List of tuples containing log entries
    """
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM audio_logs ORDER BY timestamp DESC')
        logs = cursor.fetchall()
        return logs
    except Exception as e:
        print(f"❌ Error retrieving logs: {e}")
        return []
    finally:
        conn.close()

# --- General Users (Web) ---
def create_user(name, email, phone, address, password):
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        password_hash = hash_password(password)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO users (name, email, phone, address, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, email, phone, address, password_hash, created_at))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Email or phone already exists
        return False
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return False
    finally:
        conn.close()

def get_user_by_phone(phone):
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, email, phone, address, created_at FROM users WHERE phone=?', (phone,))
        row = cursor.fetchone()
        return row
    except Exception as e:
        print(f"❌ Error fetching user: {e}")
        return None
    finally:
        conn.close()

def verify_user(phone, password):
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute('SELECT id FROM users WHERE phone=? AND password_hash=?', (phone, password_hash))
        row = cursor.fetchone()
        return row is not None
    except Exception as e:
        print(f"❌ Error verifying user: {e}")
        return False
    finally:
        conn.close()

def get_all_users():
    try:
        conn = sqlite3.connect('evidence.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, email, phone, address, created_at FROM users ORDER BY created_at DESC')
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        print(f"❌ Error fetching users: {e}")
        return []
    finally:
        conn.close()

if __name__ == '__main__':
    # Initialize database when this module is run directly
    init_database() 