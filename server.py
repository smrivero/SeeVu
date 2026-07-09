import datetime
import json
import os
import secrets
import uuid
from pathlib import Path

import openai
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from supabase import Client, create_client

# ── Auth ──────────────────────────────────────────────────────────────────────

USERS = {
    "upwork": "upwork",
    "acrons": "acrons1234",
}

_sessions: dict[str, str] = {}  # token → username

PUBLIC_PATHS = {"/api/login"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        token = request.cookies.get("session")
        if not token or token not in _sessions:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)
            return RedirectResponse("/login", status_code=302)
        return await call_next(request)


# ── Supabase ──────────────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE", "")

# Legacy file paths — used as fallback until Supabase schema is applied
_LOGS_DIR   = Path(os.getenv("LOGS_DIR", "conversation_logs"))
_CONFIG_DIR = Path(os.getenv("CONFIG_PATH", "bot_config"))
_CONFIG_FILE        = _CONFIG_DIR / "settings.json"
_PROMPTS_FILE       = _CONFIG_DIR / "prompts.json"
_ACTIVE_PROMPT_FILE = _CONFIG_DIR / "active_prompt.txt"
_LIVE_SESSION_FILE  = _CONFIG_DIR / "live_session.json"

_db: Client | None = None


def get_db() -> Client:
    global _db
    if _db is None:
        _db = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _db


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── Providers ─────────────────────────────────────────────────────────────────

PROVIDERS = {
    "openai_realtime": {
        "label": "OpenAI Realtime",
        "voices": [
            {"id": "alloy",   "label": "Alloy — neutral, balanced"},
            {"id": "ash",     "label": "Ash — calm, composed"},
            {"id": "ballad",  "label": "Ballad — warm, gentle"},
            {"id": "coral",   "label": "Coral — energetic, bright"},
            {"id": "echo",    "label": "Echo — clear, precise"},
            {"id": "sage",    "label": "Sage — wise, measured"},
            {"id": "shimmer", "label": "Shimmer — light, airy"},
            {"id": "verse",   "label": "Verse — natural, conversational"},
        ],
    }
}

app = FastAPI()
app.add_middleware(AuthMiddleware)


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_conversations() -> list[dict]:
    try:
        res = get_db().table("conversations").select("*").order("started_at", desc=True).execute()
        if res.data:
            return res.data
    except Exception:
        pass
    # Fallback: read from local JSON files
    if not _LOGS_DIR.exists():
        return []
    convs = []
    for f in sorted(_LOGS_DIR.glob("conversation_*.json"), reverse=True):
        try:
            convs.append(json.loads(f.read_text()))
        except Exception:
            pass
    return convs


def load_config() -> dict:
    default = {"provider": "openai_realtime", "voice": "verse"}
    try:
        res = get_db().table("app_config").select("provider,voice").eq("id", 1).single().execute()
        if res.data:
            return {**default, **res.data}
    except Exception:
        pass
    try:
        return {**default, **json.loads(_CONFIG_FILE.read_text())}
    except Exception:
        return default


def load_prompts() -> list[dict]:
    try:
        res = get_db().table("prompts").select("*").order("created_at").execute()
        if res.data:
            return res.data
    except Exception:
        pass
    try:
        return json.loads(_PROMPTS_FILE.read_text())
    except Exception:
        return []


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/me")
def api_me(request: Request):
    token = request.cookies.get("session")
    return {"username": _sessions.get(token or "", "")}


@app.post("/api/login")
async def api_login(payload: dict, response: JSONResponse = None):
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    if USERS.get(username) != password:
        return JSONResponse({"ok": False}, status_code=401)
    token = secrets.token_hex(32)
    _sessions[token] = username
    resp = JSONResponse({"ok": True})
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return resp


@app.post("/api/logout")
def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        _sessions.pop(token, None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    return resp


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/conversations")
def api_conversations():
    return load_conversations()


@app.get("/api/config")
def api_get_config():
    return load_config()


@app.post("/api/config")
async def api_set_config(payload: dict):
    try:
        get_db().table("app_config").update({
            "provider": payload.get("provider"),
            "voice": payload.get("voice"),
            "updated_at": _now(),
        }).eq("id", 1).execute()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/prompts")
def api_get_prompts():
    return load_prompts()


@app.post("/api/prompts")
async def api_save_prompt(payload: dict):
    name = payload.get("name", "").strip()
    content = payload.get("content", "").strip()
    lang = payload.get("lang", "en")
    if not name or not content:
        return JSONResponse({"ok": False, "error": "name and content required"}, status_code=400)
    try:
        get_db().table("prompts").insert({
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "lang": lang,
            "content": content,
        }).execute()
        return {"ok": True, "prompts": load_prompts()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/prompt/apply")
async def api_apply_prompt(payload: dict):
    content = payload.get("content", "").strip()
    if not content:
        return JSONResponse({"ok": False, "error": "content required"}, status_code=400)
    try:
        get_db().table("active_prompt").update({
            "content": content,
            "updated_at": _now(),
        }).eq("id", 1).execute()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/live-session")
def api_live_session():
    try:
        res = get_db().table("live_session").select("*").eq("id", 1).single().execute()
        return res.data or {"active": False, "turns": []}
    except Exception:
        return {"active": False, "turns": []}


@app.get("/api/providers")
def api_providers():
    return PROVIDERS


@app.get("/api/audio/{track}/{session_id}")
def api_audio(track: str, session_id: str):
    if track not in ("bot", "user"):
        raise HTTPException(status_code=400, detail="track must be bot or user")
    path = f"{track}_{session_id}.wav"
    url = f"{SUPABASE_URL}/storage/v1/object/public/audio/{path}"
    return RedirectResponse(url)


@app.post("/api/analyze/{session_id}")
async def api_analyze(session_id: str):
    try:
        res = get_db().table("conversations").select("*").eq("session_id", session_id).single().execute()
        data = res.data
    except Exception:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if data.get("analysis"):
        return data["analysis"]

    messages = data.get("messages", [])
    if not messages:
        return JSONResponse({"error": "No messages to analyze"}, status_code=400)

    transcript = "\n".join(
        f"{m['role'].upper()}: {m.get('content', '')}" for m in messages
    )

    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You analyze voice AI call transcripts. "
                    "Return ONLY a valid JSON object, no markdown, no extra text."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Analyze this call transcript and return a JSON object with:\n"
                    "- \"sentiment\": \"positive\", \"neutral\", or \"negative\"\n"
                    "- \"productive\": true or false (was the call goal achieved?)\n"
                    "- \"summary\": 2-3 sentence summary of what happened\n"
                    "- \"highlights\": array of 2-4 key points (strings)\n\n"
                    f"Transcript:\n{transcript}\n\n"
                    "Return only the JSON object."
                ),
            },
        ],
        temperature=0.3,
        max_tokens=600,
    )

    raw = response.choices[0].message.content or ""
    try:
        analysis = json.loads(raw)
    except Exception:
        analysis = {"sentiment": "neutral", "productive": False, "summary": raw, "highlights": []}

    get_db().table("conversations").update({"analysis": analysis}).eq("session_id", session_id).execute()
    return analysis


# ── Static frontend ────────────────────────────────────────────────────────────

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
