import asyncio
import datetime
import json
import os
import secrets
import subprocess
import uuid
from pathlib import Path
from collections import deque

# Carga .env si existe (útil en dev sin dev.sh)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import openai
import uvicorn
import websockets
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from supabase import Client, create_client

# ── Auth ──────────────────────────────────────────────────────────────────────

# token (httponly cookie) → {user_id, email, roles}
_sessions: dict[str, dict] = {}

PUBLIC_PATHS = {"/api/auth/login", "/health"}


def _is_authenticated(request: Request) -> bool:
    token = request.cookies.get("session")
    return bool(token and token in _sessions)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in PUBLIC_PATHS:
            return await call_next(request)

        if path.startswith("/api/"):
            if not _is_authenticated(request):
                return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)
            return await call_next(request)

        if path == "/ws/twilio":
            return await call_next(request)

        if path == "/ws":
            if not _is_authenticated(request):
                return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)
            return await call_next(request)

        # Frontend estático y SPA (incluye la pantalla de login en /)
        return await call_next(request)


# ── Supabase ──────────────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE", "")

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
    },
    "deepgram_openai_cartesia": {
        "label": "Deepgram + OpenAI + Cartesia",
        "voices": [
            {
                "id": "71a7ad14-091c-4e8e-a314-022ece01c121",
                "label": "British Reading Lady — clear, narrative",
            },
            {
                "id": "a0e99841-438c-4a64-b679-ae501e7d6091",
                "label": "Barbershop Man — warm, conversational",
            },
            {
                "id": "794f9389-aac1-45b6-b726-9d9369183238",
                "label": "Sarah — professional, friendly",
            },
            {
                "id": "e13cae5c-ec59-4f71-b0a6-266df3c9bb8e",
                "label": "Madame Mischief — playful, expressive",
            },
            {
                "id": "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
                "label": "Jacqueline — calm, measured",
            },
        ],
    },
}

# Centralized allow-list for the text Chat's OpenAI model -- the frontend
# only ever sees this via GET /api/chat/models, never hardcodes it, so
# there's a single source of truth the backend can validate against.
CHAT_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"]
CHAT_DEFAULT_MODEL = "gpt-4o-mini"

app = FastAPI()
app.add_middleware(AuthMiddleware)


@app.get("/health")
def health():
    return {"ok": True}


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
    default = {"provider": "openai_realtime", "voice": "verse", "log_level": "INFO", "chat_model": CHAT_DEFAULT_MODEL}
    try:
        res = get_db().table("app_config").select("provider,voice,log_level,chat_model").eq("id", 1).single().execute()
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


def load_active_prompt() -> str:
    return load_active_prompt_data()["content"]


def load_active_prompt_data() -> dict:
    default = {"content": "", "prompt_id": None, "updated_at": None}
    try:
        res = get_db().table("active_prompt").select("content,prompt_id,updated_at").eq("id", 1).single().execute()
        if res.data:
            return {
                "content": (res.data.get("content") or "").strip(),
                "prompt_id": res.data.get("prompt_id") or None,
                "updated_at": res.data.get("updated_at"),
            }
    except Exception:
        pass
    try:
        return {"content": _ACTIVE_PROMPT_FILE.read_text(encoding="utf-8").strip(), "prompt_id": None, "updated_at": None}
    except Exception:
        return default


def _set_live_session_initiator(user: dict):
    """Guarda quién va a iniciar la próxima llamada en live_session."""
    try:
        get_db().table("live_session").update({
            "initiated_by": user["user_id"],
            "initiated_by_email": user["email"],
        }).eq("id", 1).execute()
    except Exception:
        pass


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _get_user_roles(user_id: str) -> list[str]:
    """Devuelve lista de nombres de roles para un user_id."""
    try:
        res = get_db().table("user_roles").select("role_id").eq("user_id", user_id).execute()
        role_ids = [r["role_id"] for r in (res.data or [])]
        if not role_ids:
            return []
        res2 = get_db().table("roles").select("name").in_("id", role_ids).execute()
        return [r["name"] for r in (res2.data or [])]
    except Exception:
        return []


def get_session_user(request: Request) -> dict:
    """FastAPI dependency: retorna el usuario de sesión o lanza 401."""
    token = request.cookies.get("session")
    user = _sessions.get(token or "")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_ws_session_user(websocket: WebSocket) -> dict:
    """Same session check as get_session_user, but for WebSocket routes
    (Request-based dependencies don't bind to websocket connections)."""
    token = websocket.cookies.get("session")
    user = _sessions.get(token or "")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_superadmin(user: dict = Depends(get_session_user)) -> dict:
    if "superadmin" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="Superadmin required")
    return user


def require_admin_or_above(user: dict = Depends(get_session_user)) -> dict:
    if not any(r in user.get("roles", []) for r in ("superadmin", "company_admin")):
        raise HTTPException(status_code=403, detail="Admin required")
    return user


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def auth_login(payload: dict):
    email    = payload.get("email", "").strip()
    password = payload.get("password", "")
    if not email or not password:
        return JSONResponse({"ok": False, "error": "Email and password required"}, status_code=400)
    try:
        auth_resp = get_db().auth.sign_in_with_password({"email": email, "password": password})
        user = auth_resp.user
        if not user:
            raise ValueError("no user")
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid credentials"}, status_code=401)

    roles = _get_user_roles(str(user.id))
    token = secrets.token_hex(32)
    _sessions[token] = {"user_id": str(user.id), "email": user.email, "roles": roles}

    resp = JSONResponse({"ok": True})
    secure_cookie = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER"))
    resp.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        max_age=86400 * 7,
    )
    return resp


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    token = request.cookies.get("session")
    if token:
        _sessions.pop(token, None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    return resp


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(get_session_user)):
    return {"user_id": user["user_id"], "email": user["email"], "roles": user["roles"]}


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/conversations")
def api_conversations():
    return load_conversations()


@app.delete("/api/conversations/{session_id}")
def api_delete_conversation(session_id: str):
    try:
        get_db().table("conversations").delete().eq("session_id", session_id).execute()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/config")
def api_get_config():
    return load_config()


_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


@app.post("/api/config")
async def api_set_config(payload: dict, user: dict = Depends(get_session_user)):
    try:
        update = {
            "provider": payload.get("provider"),
            "voice": payload.get("voice"),
            "updated_at": _now(),
        }
        log_level = payload.get("log_level")
        if log_level in _VALID_LOG_LEVELS:
            update["log_level"] = log_level
        chat_model = payload.get("chat_model")
        if chat_model in CHAT_MODELS:
            update["chat_model"] = chat_model
        get_db().table("app_config").update(update).eq("id", 1).execute()
        _set_live_session_initiator(user)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/prompts")
def api_get_prompts():
    return load_prompts()


@app.get("/api/prompt/active")
def api_get_active_prompt():
    return load_active_prompt_data()


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
async def api_apply_prompt(payload: dict, user: dict = Depends(get_session_user)):
    content = payload.get("content", "").strip()
    if not content:
        return JSONResponse({"ok": False, "error": "content required"}, status_code=400)
    prompt_id = (payload.get("prompt_id") or "").strip() or None
    try:
        get_db().table("active_prompt").update({
            "content": content,
            "prompt_id": prompt_id,
            "updated_at": _now(),
        }).eq("id", 1).execute()
        _set_live_session_initiator(user)
        return {"ok": True, "prompt_id": prompt_id}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


_MAX_CHAT_HISTORY = 40  # cap turns sent to OpenAI so context doesn't grow unbounded


def load_chat_conversations() -> list[dict]:
    try:
        res = get_db().table("chat_conversations").select("*").order("updated_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []


def _load_chat_session(session_id: str) -> dict | None:
    """Returns the frozen prompt/model for an existing session, or None if
    the session_id is new/unknown (caller should start a fresh one)."""
    try:
        res = get_db().table("chat_conversations").select("prompt_snapshot,model").eq("session_id", session_id).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return None


def _save_chat_turn(session_id: str, history: list[dict], reply: str, user: dict, prompt_snapshot: str, model: str, is_new: bool) -> None:
    """Persist the conversation so far (best-effort -- a failure here
    shouldn't fail the chat response the user is waiting on). prompt_snapshot
    and model are only written on creation -- they stay frozen for the life
    of the session regardless of what Settings changes to afterward."""
    now = _now()
    full_messages = history + [{"role": "assistant", "content": reply}]
    try:
        if is_new:
            get_db().table("chat_conversations").insert({
                "session_id": session_id,
                "started_at": now,
                "updated_at": now,
                "messages": full_messages,
                "prompt_snapshot": prompt_snapshot,
                "model": model,
                "created_by": user.get("user_id"),
                "created_by_email": user.get("email"),
            }).execute()
        else:
            get_db().table("chat_conversations").update({
                "messages": full_messages,
                "updated_at": now,
            }).eq("session_id", session_id).execute()
    except Exception as e:
        print(f"[chat] failed to persist conversation {session_id}: {e!r}", flush=True)


@app.get("/api/chat/models")
def api_chat_models():
    return {"models": CHAT_MODELS, "default": CHAT_DEFAULT_MODEL}


@app.post("/api/chat")
async def api_chat(payload: dict, user: dict = Depends(get_session_user)):
    """Text chat using the same active prompt configured in Settings (and
    used by the voice agent). The system prompt is always loaded here from
    the DB -- the frontend sends only the conversation turns, never the
    prompt itself, so it can't be overridden client-side.

    Prompt and model are frozen into the chat_conversations row the moment
    a session is created, and reused for every later turn in that session --
    changing the prompt or the chat model in Settings only affects NEW
    conversations, never one already in progress.
    """
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        return JSONResponse({"ok": False, "error": "invalid_messages"}, status_code=400)

    history = []
    for m in raw_messages[-_MAX_CHAT_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            history.append({"role": role, "content": content.strip()})

    if not history:
        return JSONResponse({"ok": False, "error": "no_messages"}, status_code=400)

    requested_session_id = (payload.get("session_id") or "").strip()
    existing = _load_chat_session(requested_session_id) if requested_session_id else None

    if existing:
        session_id = requested_session_id
        system_prompt = existing.get("prompt_snapshot") or ""
        model = existing.get("model") or CHAT_DEFAULT_MODEL
        is_new = False
    else:
        system_prompt = load_active_prompt()
        if not system_prompt:
            return JSONResponse({"ok": False, "error": "no_prompt"}, status_code=400)
        requested_model = payload.get("model")
        if requested_model in CHAT_MODELS:
            model = requested_model
        else:
            model = load_config().get("chat_model")
            if model not in CHAT_MODELS:
                model = CHAT_DEFAULT_MODEL
        session_id = requested_session_id or str(uuid.uuid4())
        is_new = True

    messages = [{"role": "system", "content": system_prompt}, *history]

    print(f"[chat] session={session_id[:8]} model={model} new={is_new}", flush=True)

    try:
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.chat.completions.create(model=model, messages=messages)
        reply = response.choices[0].message.content
    except Exception as e:
        err = str(e)
        error_code = "invalid_model" if "model" in err.lower() else "openai_error"
        return JSONResponse({"ok": False, "error": error_code, "detail": err}, status_code=500)

    _save_chat_turn(session_id, history, reply, user, system_prompt, model, is_new)

    return {"ok": True, "message": reply, "session_id": session_id, "model": model}


@app.get("/api/chat/conversations")
def api_chat_conversations():
    return load_chat_conversations()


@app.delete("/api/chat/conversations/{session_id}")
def api_delete_chat_conversation(session_id: str):
    try:
        get_db().table("chat_conversations").delete().eq("session_id", session_id).execute()
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


_PROJECT_ROOT = Path(__file__).parent
_BOT_LOG_FILE = _PROJECT_ROOT / "conversation_logs" / "bot.log"


def _keep_log_line(line: str) -> bool:
    """Filter out noisy system-prompt lines that pipecat logs as bare INF lines
    (no timestamp prefix). Keep only structured log lines and server messages."""
    stripped = line.strip()
    if not stripped:
        return False
    # pipecat structured line: starts with a timestamp "2026-..."
    if stripped[:4].isdigit():
        return True
    # uvicorn/INFO lines
    if stripped.startswith("INFO:") or stripped.startswith("["):
        return True
    return False


def _read_logs_via_docker(offset: int) -> dict | None:
    """Dev environment: bot runs in a separate container via docker compose.
    Returns None if docker isn't available (e.g. production)."""
    try:
        result = subprocess.run(
            ["docker", "compose", "logs", "--no-log-prefix", "--tail", "3000", "bot"],
            capture_output=True, text=True, cwd=str(_PROJECT_ROOT), timeout=8,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    all_lines = [l for l in result.stdout.splitlines() if _keep_log_line(l)]
    if not all_lines and result.returncode != 0:
        return None
    new_lines = all_lines[offset:]
    return {"lines": new_lines, "next_offset": len(all_lines)}


def _read_logs_via_file(offset: int) -> dict:
    """Production: server.py and bot.py are sibling processes in the same
    container sharing conversation_logs/, so read the log file directly."""
    if not _BOT_LOG_FILE.exists():
        return {"lines": ["[server] bot.log aún no existe — esperando a que el bot arranque"], "next_offset": 0}
    try:
        size = _BOT_LOG_FILE.stat().st_size
        if offset > size:
            offset = 0  # file was rotated
        # Open in binary mode: seek() with a raw byte offset is only
        # well-defined for binary files. Text-mode seek() requires an
        # opaque cookie from tell() on the same handle, so seeking with
        # a plain byte count (as we do here across requests) was silently
        # landing in the wrong spot and returning no new content.
        with open(_BOT_LOG_FILE, "rb") as f:
            f.seek(offset)
            chunk = f.read(64 * 1024)  # max 64 KB per poll
        text = chunk.decode("utf-8", errors="replace")
        lines = [l for l in text.splitlines() if l.strip()]
        return {"lines": lines, "next_offset": offset + len(chunk)}
    except Exception as e:
        return {"lines": [f"[server] Error: {e}"], "next_offset": offset}


@app.get("/api/logs/recent")
def get_bot_logs(offset: int = 0, _user: dict = Depends(get_session_user)):
    """Returns new bot log lines since `offset`. Tries docker compose logs
    (local dev, bot in its own container) first, falls back to reading the
    shared log file directly (production, bot + server in one container)."""
    docker_result = _read_logs_via_docker(offset)
    if docker_result is not None:
        docker_result["source"] = "docker"
        return docker_result
    result = _read_logs_via_file(offset)
    result["source"] = "file"
    result["debug"] = {
        "path": str(_BOT_LOG_FILE),
        "exists": _BOT_LOG_FILE.exists(),
        "size": _BOT_LOG_FILE.stat().st_size if _BOT_LOG_FILE.exists() else None,
    }
    return result


@app.get("/api/audio/{track}/{session_id}")
def api_audio(track: str, session_id: str):
    if track not in ("bot", "user"):
        raise HTTPException(status_code=400, detail="track must be bot or user")
    path = f"{track}_{session_id}.wav"
    url = f"{SUPABASE_URL}/storage/v1/object/public/audio/{path}"
    return RedirectResponse(url)


async def _analyze_transcript(messages: list[dict], kind: str) -> dict:
    """Shared sentiment/summary analysis for both voice calls and text
    chats. `kind` only tweaks the system prompt wording."""
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
                    f"You analyze {kind} transcripts. "
                    "Return ONLY a valid JSON object, no markdown, no extra text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Analyze this {kind} transcript and return a JSON object with:\n"
                    "- \"sentiment\": \"positive\", \"neutral\", or \"negative\"\n"
                    "- \"productive\": true or false (was the goal achieved?)\n"
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
        return json.loads(raw)
    except Exception:
        return {"sentiment": "neutral", "productive": False, "summary": raw, "highlights": []}


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

    analysis = await _analyze_transcript(messages, "voice AI call")
    get_db().table("conversations").update({"analysis": analysis}).eq("session_id", session_id).execute()
    return analysis


@app.post("/api/chat/analyze/{session_id}")
async def api_analyze_chat(session_id: str):
    try:
        res = get_db().table("chat_conversations").select("*").eq("session_id", session_id).single().execute()
        data = res.data
    except Exception:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if data.get("analysis"):
        return data["analysis"]

    messages = data.get("messages", [])
    if not messages:
        return JSONResponse({"error": "No messages to analyze"}, status_code=400)

    analysis = await _analyze_transcript(messages, "text chat")
    get_db().table("chat_conversations").update({"analysis": analysis}).eq("session_id", session_id).execute()
    return analysis


# ── WebSocket proxy (production: dashboard → bot interno) ─────────────────────

BOT_INTERNAL_WS_URL = os.getenv("BOT_INTERNAL_WS_URL", "ws://127.0.0.1:7860/ws")


async def _proxy_to_bot(client_ws: WebSocket) -> None:
    await client_ws.accept()
    try:
        async with websockets.connect(BOT_INTERNAL_WS_URL, open_timeout=15) as bot_ws:
            print(f"[ws-proxy] connected to bot at {BOT_INTERNAL_WS_URL}", flush=True)

            async def client_to_bot():
                try:
                    while True:
                        msg = await client_ws.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if msg.get("text") is not None:
                            await bot_ws.send(msg["text"])
                        elif msg.get("bytes") is not None:
                            await bot_ws.send(msg["bytes"])
                except WebSocketDisconnect:
                    pass

            async def bot_to_client():
                try:
                    async for message in bot_ws:
                        if isinstance(message, str):
                            await client_ws.send_text(message)
                        else:
                            await client_ws.send_bytes(message)
                except websockets.ConnectionClosed:
                    pass

            _done, pending = await asyncio.wait(
                [asyncio.create_task(client_to_bot()), asyncio.create_task(bot_to_client())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    except Exception as e:
        print(f"[ws-proxy] error connecting to bot at {BOT_INTERNAL_WS_URL}: {e!r}", flush=True)
    finally:
        await client_ws.close()


@app.websocket("/ws")
async def websocket_proxy_dashboard(client_ws: WebSocket, _user: dict = Depends(get_ws_session_user)):
    """WebSocket autenticado para pruebas desde el dashboard (navegador)."""
    await _proxy_to_bot(client_ws)


@app.websocket("/ws/twilio")
async def websocket_proxy_twilio(client_ws: WebSocket):
    """WebSocket público para llamadas telefónicas de Twilio (sin login)."""
    await _proxy_to_bot(client_ws)


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
