"""Tests for the WPBrigade chatbot.

The Gemini call is monkeypatched out, so tests always exercise the regex
fallback and never touch the network.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TEST_DB = os.path.join(tempfile.gettempdir(), "wpbrigade_test.db")

import database  # noqa: E402
import lim_service  # noqa: E402

database.DB_PATH = _TEST_DB

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN_EMAIL = "test06.wpbrigade@gmail.com"


@pytest.fixture(autouse=True)
def force_regex_fallback(monkeypatch):
    """Never call Gemini during tests."""
    monkeypatch.setattr(lim_service, "_parse_with_gemini", lambda text: None)


@pytest.fixture()
def client():
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)
    database.init_db()
    conn = database.get_connection()
    conn.execute("INSERT OR IGNORE INTO admins (email) VALUES (?)", (ADMIN_EMAIL,))
    conn.execute(
        "INSERT OR IGNORE INTO users (email, name, city) VALUES (?, ?, ?)",
        ("john.smith@xyz.com", "John Smith", "New York"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (email, name, city) VALUES (?, ?, ?)",
        ("samantha@xyz.com", "Samantha", "Madrid"),
    )
    conn.commit()
    conn.close()
    return TestClient(main.app)


def login(client, email=ADMIN_EMAIL):
    return client.post("/login", data={"email": email}, follow_redirects=False)


# ---------------------------------------------------------------------------
# Parser (regex fallback)
# ---------------------------------------------------------------------------

def test_parse_add_with_phone():
    parsed = lim_service.parse_command("add the user john@xyz.com with phone +92332")
    assert parsed["action"] == "add"
    assert parsed["email"] == "john@xyz.com"
    assert parsed["field"] == "phone"
    assert parsed["value"] == "+92332"


def test_parse_remove():
    parsed = lim_service.parse_command("remove the user john@xyz.com")
    assert parsed["action"] == "remove"
    assert parsed["email"] == "john@xyz.com"


def test_parse_update_possessive():
    parsed = lim_service.parse_command("update samanthas city to Cordoba")
    assert parsed["action"] == "update"
    assert parsed["name"] == "samantha"
    assert parsed["field"] == "city"
    assert parsed["value"] == "Cordoba"


def test_parse_help_and_unknown():
    assert lim_service.parse_command("help")["action"] == "help"
    assert lim_service.parse_command("what is the weather like")["action"] == "unknown"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_login_rejected(client):
    res = login(client, "stranger@xyz.com")
    assert res.status_code == 401
    assert "Access denied. Email not registered." in res.text


def test_login_success_and_chat_page(client):
    res = login(client)
    assert res.status_code == 303
    assert res.headers["location"] == "/chat"
    chat = client.get("/chat")
    assert chat.status_code == 200
    assert ADMIN_EMAIL in chat.text


def test_chat_requires_login(client):
    res = client.get("/chat", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/"


def test_api_requires_login(client):
    res = client.post("/api/command", json={"command": "help"})
    assert res.status_code == 401
    res = client.get("/api/users")
    assert res.status_code == 401


def test_logout(client):
    login(client)
    client.get("/logout", follow_redirects=False)
    res = client.get("/chat", follow_redirects=False)
    assert res.status_code == 303


# ---------------------------------------------------------------------------
# Command flow
# ---------------------------------------------------------------------------

def test_add_duplicate_remove_flow(client):
    login(client)

    res = client.post("/api/command", json={"command": "add the user new@xyz.com with phone +92332"})
    assert "User added: new@xyz.com" in res.json()["reply"]
    assert database.get_user_by_email("new@xyz.com")["phone"] == "+92332"

    res = client.post("/api/command", json={"command": "add the user new@xyz.com"})
    assert "⚠️ User already exists" in res.json()["reply"]

    res = client.post("/api/command", json={"command": "remove the user new@xyz.com"})
    assert "User removed: new@xyz.com" in res.json()["reply"]

    res = client.post("/api/command", json={"command": "remove the user new@xyz.com"})
    assert "⚠️ User not found" in res.json()["reply"]


def test_update_flow(client):
    login(client)

    res = client.post("/api/command", json={"command": "update samanthas city to Cordoba"})
    body = res.json()
    assert "✅ Updated samantha@xyz.com — city set to Cordoba" in body["reply"]
    samantha = next(u for u in body["users"] if u["email"] == "samantha@xyz.com")
    assert samantha["city"] == "Cordoba"

    res = client.post("/api/command", json={"command": "update ghost@xyz.com city to Rome"})
    assert "⚠️ User not found" in res.json()["reply"]


def test_help_and_unknown_commands(client):
    login(client)

    res = client.post("/api/command", json={"command": "help"})
    assert "add the user john@xyz.com" in res.json()["reply"]

    res = client.post("/api/command", json={"command": "sing me a song"})
    assert "didn't understand" in res.json()["reply"]


def test_list_users(client):
    login(client)
    res = client.get("/api/users")
    assert res.status_code == 200
    emails = {u["email"] for u in res.json()["users"]}
    assert emails == {"john.smith@xyz.com", "samantha@xyz.com"}
