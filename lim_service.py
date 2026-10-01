"""Natural-language command parsing via the Gemini API, with a regex fallback."""

import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a command parser. Parse user command into strict JSON:
{"action": "add"|"remove"|"update"|"help"|"unknown", "email": string|null, "name": string|null, "field": "city"|"phone"|"email"|"name"|null, "value": string|null}
Handle possessive 'samanthas' → name='samantha'
Return ONLY JSON, no other text."""

VALID_ACTIONS = {"add", "remove", "update", "help", "unknown"}
VALID_FIELDS = {"city", "phone", "email", "name"}


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def _parse_with_gemini(text):
    """Return a parsed dict, or None if Gemini is unavailable/fails."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            system_instruction=SYSTEM_PROMPT,
            generation_config={"temperature": 0},
        )
        response = model.generate_content(text)
        raw = (response.text or "").strip()
        # Strip markdown code fences / surrounding prose if present.
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        return json.loads(match.group(0))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Regex fallback
# ---------------------------------------------------------------------------

def _strip_possessive(token):
    """'samantha's' -> 'samantha', 'samanthas' -> 'samantha'."""
    if token.lower().endswith("'s"):
        return token[:-2]
    if token.lower().endswith("s"):
        return token[:-1]
    return token


def _parse_with_regex(text):
    t = text.strip()
    if not t:
        return {"action": "unknown"}

    if re.search(r"\b(help|commands?|examples?)\b", t, re.I) or "what can you do" in t.lower():
        return {"action": "help"}

    # update samantha's city to Cordoba / update john@xyz.com phone to +123
    m = re.search(
        r"\b(?:update|set|change)\s+([^\s]+)\s+(city|phone|email|name)\s+"
        r"(?:to|=|as)\s+(.+?)\s*$",
        t,
        re.I,
    )
    if m:
        who, field, value = m.group(1), m.group(2).lower(), m.group(3).rstrip(".! ")
        result = {"action": "update", "field": field, "value": value}
        if "@" in who:
            result["email"] = who.strip(".,!").lower()
        else:
            result["name"] = _strip_possessive(who)
        return result

    # remove the user john@xyz.com / delete john@xyz.com
    m = re.search(r"\b(?:remove|delete)\s+(?:the\s+)?user\s+([^\s]+@[^\s]+)", t, re.I) or \
        re.search(r"\b(?:remove|delete)\s+([^\s]+@[^\s]+)", t, re.I)
    if m:
        return {"action": "remove", "email": m.group(1).strip(".,!").lower()}

    # add the user john@xyz.com with phone +92332 / add user john@xyz.com named John from York
    m = re.search(r"\b(?:add|create|register)\s+(?:the\s+|a\s+)?user\s+([^\s]+@[^\s]+)", t, re.I) or \
        re.search(r"\b(?:add|create|register)\s+([^\s]+@[^\s]+)", t, re.I)
    if m:
        result = {"action": "add", "email": m.group(1).strip(".,!").lower()}

        pm = re.search(
            r"\bphone\b[\s:]*(?:number[\s:]*)?(?:is[\s:]*)?(\+?[\d][\d\s\-()]+\d)", t, re.I
        )
        if pm:
            result["field"] = "phone"
            result["value"] = pm.group(1).strip()
        else:
            cm = re.search(r"\bcity\b[\s:]*(?:is[\s:]*)?([A-Za-zÀ-ÿ'\- ]+?)\s*$", t, re.I) or \
                 re.search(r"\bfrom\s+([A-Za-zÀ-ÿ'\- ]+?)\s*$", t, re.I)
            if cm:
                result["field"] = "city"
                result["value"] = cm.group(1).strip()

        nm = re.search(r"\bnamed\s+([A-Za-zÀ-ÿ'\- ]+?)(?:\s+from|\s+with|\s*$)", t, re.I) or \
             re.search(r"\bname\s+([A-Za-zÀ-ÿ'\- ]+?)(?:\s+from|\s+with|\s*$)", t, re.I)
        if nm:
            result["name"] = nm.group(1).strip()
        return result

    return {"action": "unknown"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _normalize(data):
    if not isinstance(data, dict):
        data = {}

    action = str(data.get("action") or "unknown").strip().lower()
    if action == "delete":
        action = "remove"
    if action not in VALID_ACTIONS:
        action = "unknown"

    field = data.get("field")
    field = str(field).strip().lower() if field else None
    if field not in VALID_FIELDS:
        field = None

    parsed = {"action": action, "email": None, "name": None, "field": field, "value": None}
    for key in ("email", "name", "value"):
        value = data.get(key)
        if isinstance(value, str) and value.strip() and value.strip().lower() not in ("null", "none"):
            parsed[key] = value.strip()

    if parsed["email"]:
        parsed["email"] = parsed["email"].lower()
    return parsed


def parse_command(text):
    """Parse a natural-language command into {action, email, name, field, value}."""
    data = _parse_with_gemini(text)
    if data is None:
        data = _parse_with_regex(text)
    return _normalize(data)
