"""SQLite database layer for the WPBrigade chatbot."""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "database.db"))

# Fields that are allowed to be updated through natural-language commands.
UPDATABLE_FIELDS = {"city", "phone", "email", "name"}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT,
                phone TEXT,
                city TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admins
# ---------------------------------------------------------------------------

def get_admin_by_email(email):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM admins WHERE LOWER(email) = LOWER(?)", (email,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def add_user(email, name=None, phone=None, city=None):
    """Insert a user. Raises sqlite3.IntegrityError on duplicate email."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, name, phone, city) VALUES (?, ?, ?, ?)",
            (email, name, phone, city),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_name(name):
    """Match by exact name first, then by name prefix (e.g. 'samantha')."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(name) = LOWER(?)", (name,)
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(name) LIKE LOWER(?) "
                "ORDER BY id LIMIT 1",
                (name + "%",),
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_user_field(user_id, field, value):
    if field not in UPDATABLE_FIELDS:
        raise ValueError(f"Field '{field}' cannot be updated")
    conn = get_connection()
    try:
        cursor = conn.execute(
            f"UPDATE users SET {field} = ? WHERE id = ?", (value, user_id)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_user_by_email(email):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM users WHERE LOWER(email) = LOWER(?)", (email,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def list_users():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
