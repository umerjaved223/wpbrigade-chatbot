# WPBrigade User Management Chatbot

A FastAPI web app that lets an admin manage users through natural-language
chat commands. Commands are parsed by the Gemini API into structured JSON
(`{action, email, name, field, value}`), with a regex fallback when the API
is unavailable or no key is configured.

## Tech Stack

- Python 3 + FastAPI (Jinja2 templates, vanilla HTML/CSS/JS frontend)
- SQLite (built-in `sqlite3`)
- Gemini API (`google-generativeai`) for natural-language parsing
- `python-dotenv` for environment configuration

## Project Structure

```
wpbrigade-chatbot/
├── main.py            # FastAPI app: routes, sessions, command execution
├── database.py        # SQLite layer (admins + users tables)
├── lim_service.py     # Gemini parser with regex fallback
├── seed.py            # Seeds admin + demo users
├── test_commands.py   # pytest suite (no network access needed)
├── .env               # Local secrets (not committed)
├── .env.example       # Template for .env
├── requirements.txt
├── static/style.css   # Dark theme
└── templates/
    ├── login.html
    └── chat.html
```

## Setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # then paste your GEMINI_API_KEY into .env
python seed.py
```

Get a Gemini API key at https://aistudio.google.com/app/apikey

> Without a `GEMINI_API_KEY` the app still works — it falls back to a
> built-in regex parser.

## Run

```powershell
uvicorn main:app --reload
```

Open http://127.0.0.1:8000 and sign in with:

```
test06.wpbrigade@gmail.com
```

## Example Commands

| Command | Result |
|---|---|
| `add the user john@xyz.com with phone +92332` | Adds a user (with phone) |
| `add the user jane@xyz.com named Jane from London` | Adds a user with name + city |
| `remove the user john@xyz.com` | Deletes the user |
| `update samantha's city to Cordoba` | Updates a field by name (possessive handled) |
| `update john@xyz.com phone to +1 555 0100` | Updates a field by email |
| `help` | Shows example commands |

Anything unrecognized gets a friendly error message.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Login page |
| POST | `/login` | Validate admin email, set session cookie |
| GET | `/chat` | Chat UI (session required) |
| POST | `/api/command` | Process a natural-language command |
| GET | `/api/users` | List all users |
| GET | `/logout` | Clear session |
| GET | `/health` | Health check |

## Tests

```powershell
pytest
```

The suite covers the regex parser, the login flow, session protection, and
the full add/update/remove command flow. Gemini is monkeypatched out, so no
network or API key is required.

## Security Notes

- The Gemini API key is only ever read from `GEMINI_API_KEY` via `os.getenv`
  — never hardcode it. `.env` is git-ignored.
- Sessions are HMAC-signed cookies (`SECRET_KEY` in `.env`); change the
  default secret before deploying.
- SQL is parameterized throughout, and updatable fields are whitelisted
  (`city`, `phone`, `email`, `name`).
