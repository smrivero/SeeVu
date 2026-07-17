import asyncio
import datetime
import json
import os
import secrets
import uuid
from pathlib import Path

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
    }
}

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


def load_active_prompt() -> str:
    return load_active_prompt_data()["content"]


def load_active_prompt_data() -> dict:
    default = {"content": "", "prompt_id": None}
    try:
        res = get_db().table("active_prompt").select("content,prompt_id").eq("id", 1).single().execute()
        if res.data:
            return {
                "content": (res.data.get("content") or "").strip(),
                "prompt_id": res.data.get("prompt_id") or None,
            }
    except Exception:
        pass
    try:
        return {"content": _ACTIVE_PROMPT_FILE.read_text(encoding="utf-8").strip(), "prompt_id": None}
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


@app.post("/api/config")
async def api_set_config(payload: dict, user: dict = Depends(get_session_user)):
    try:
        get_db().table("app_config").update({
            "provider": payload.get("provider"),
            "voice": payload.get("voice"),
            "updated_at": _now(),
        }).eq("id", 1).execute()
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


# ── WebSocket proxy (production: dashboard → bot interno) ─────────────────────

BOT_INTERNAL_WS_URL = os.getenv("BOT_INTERNAL_WS_URL", "ws://127.0.0.1:7860/ws")


async def _proxy_to_bot(client_ws: WebSocket) -> None:
    await client_ws.accept()
    try:
        async with websockets.connect(BOT_INTERNAL_WS_URL, open_timeout=15) as bot_ws:

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
    except Exception:
        pass
    finally:
        await client_ws.close()


@app.websocket("/ws")
async def websocket_proxy_dashboard(client_ws: WebSocket):
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
