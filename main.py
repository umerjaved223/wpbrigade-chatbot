"""WPBrigade user-management chatbot — FastAPI application.

Run with: uvicorn main:app --reload
"""

import hashlib
import hmac
import os
import sqlite3
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database
import lim_service

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = os.getenv("SECRET_KEY", "wpbrigade-dev-secret-change-me")

app = FastAPI(title="WPBrigade User Management Chatbot")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

database.init_db()

HELP_TEXT = (
    "Here's what I can do:\n"
    "• add the user john@xyz.com with phone +92332\n"
    "• add the user jane@xyz.com named Jane from London\n"
    "• remove the user john@xyz.com\n"
    "• update samantha's city to Cordoba\n"
    "• update john@xyz.com phone to +1 555 0100\n"
    "Type any command in plain English and I'll take care of it."
)


# ---------------------------------------------------------------------------
# Session handling (HMAC-signed cookie, no server-side state)
# ---------------------------------------------------------------------------

def _sign(value: str) -> str:
    return hmac.new(SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def create_session_token(email: str) -> str:
    return f"{email}|{_sign(email)}"


def verify_session_token(token: Optional[str]) -> Optional[str]:
    if not token or "|" not in token:
        return None
    email, signature = token.rsplit("|", 1)
    if hmac.compare_digest(signature, _sign(email)):
        return email
    return None


def get_current_admin(request: Request) -> Optional[str]:
    email = verify_session_token(request.cookies.get("session"))
    if email and database.get_admin_by_email(email):
        return email
    return None


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------

def execute_command(parsed: dict) -> str:
    action = parsed.get("action") or "unknown"
    email = parsed.get("email")
    name = parsed.get("name")
    field = parsed.get("field")
    value = parsed.get("value")

    if action == "help":
        return HELP_TEXT

    if action == "add":
        if not email:
            return "⚠️ Please provide an email, e.g. add the user john@xyz.com"
        if database.get_user_by_email(email):
            return f"⚠️ User already exists: {email}"
        extras = {}
        if name:
            extras["name"] = name
        if field in ("phone", "city", "name") and value:
            extras[field] = value
        try:
            database.add_user(email, **extras)
        except sqlite3.IntegrityError:
            return f"⚠️ User already exists: {email}"
        details = ", ".join(f"{k}: {v}" for k, v in extras.items())
        return f"✅ User added: {email}" + (f" ({details})" if details else "")

    if action == "remove":
        if not email:
            return "⚠️ Please provide the email of the user to remove, e.g. remove the user john@xyz.com"
        if database.delete_user_by_email(email):
            return f"🗑️ User removed: {email}"
        return f"⚠️ User not found: {email}"

    if action == "update":
        if field not in database.UPDATABLE_FIELDS or not value:
            return "⚠️ I couldn't tell what to update. Try: update samantha's city to Cordoba"
        user = None
        if email:
            user = database.get_user_by_email(email)
        if user is None and name:
            user = database.get_user_by_name(name)
        if user is None:
            return f"⚠️ User not found: {email or name or 'unknown'}"
        if field == "email":
            value = value.lower()
            existing = database.get_user_by_email(value)
            if existing and existing["id"] != user["id"]:
                return f"⚠️ User already exists: {value}"
        database.update_user_field(user["id"], field, value)
        return f"✅ Updated {user['email']} — {field} set to {value}"

    return "🤔 I didn't understand that command. Type 'help' to see what I can do."


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CommandRequest(BaseModel):
    command: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_admin(request):
        return RedirectResponse(url="/chat", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...)):
    email = email.strip().lower()
    if not database.get_admin_by_email(email):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Access denied. Email not registered."},
            status_code=401,
        )
    response = RedirectResponse(url="/chat", status_code=303)
    response.set_cookie("session", create_session_token(email), httponly=True, samesite="lax")
    return response


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    email = get_current_admin(request)
    if not email:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "chat.html", {"email": email})


@app.post("/api/command")
def run_command(request: Request, body: CommandRequest):
    if not get_current_admin(request):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    command = body.command.strip()
    if not command:
        return {"reply": "⚠️ Please type a command first.", "users": database.list_users()}
    parsed = lim_service.parse_command(command)
    reply = execute_command(parsed)
    return {"reply": reply, "parsed": parsed, "users": database.list_users()}


@app.get("/api/users")
def list_users(request: Request):
    if not get_current_admin(request):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return {"users": database.list_users()}


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session")
    return response


@app.get("/health")
def health():
    return {"status": "ok"}
