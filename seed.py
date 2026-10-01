"""Seed the database with the initial admin and demo users."""

import database

ADMINS = [
    "test06.wpbrigade@gmail.com",
]

USERS = [
    {"email": "john.smith@xyz.com", "name": "John Smith", "phone": None, "city": "New York"},
    {"email": "samantha@xyz.com", "name": "Samantha", "phone": None, "city": "Madrid"},
]


def seed():
    database.init_db()
    conn = database.get_connection()
    try:
        for email in ADMINS:
            conn.execute("INSERT OR IGNORE INTO admins (email) VALUES (?)", (email,))

        for user in USERS:
            conn.execute(
                "INSERT OR IGNORE INTO users (email, name, phone, city) VALUES (?, ?, ?, ?)",
                (user["email"], user["name"], user["phone"], user["city"]),
            )
        conn.commit()

        admin_count = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()

    print(f"Seed complete: {admin_count} admin(s), {user_count} user(s).")
    print(f"Login with: {ADMINS[0]}")


if __name__ == "__main__":
    seed()
