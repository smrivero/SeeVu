import json
import os
import secrets
import uuid
from pathlib import Path

import openai
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# ── Auth ──────────────────────────────────────────────────────────────────────

USERS = {
    "upwork": "upwork",
    "acrons": "acrons1234",
}

_sessions: dict[str, str] = {}  # token → username

PUBLIC_PATHS = {"/login", "/api/login"}


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

LOGS_DIR = Path(os.getenv("LOGS_DIR", "conversation_logs"))
CONFIG_DIR = Path(os.getenv("CONFIG_PATH", "bot_config"))
CONFIG_FILE = CONFIG_DIR / "settings.json"
PROMPTS_FILE = CONFIG_DIR / "prompts.json"
ACTIVE_PROMPT_FILE = CONFIG_DIR / "active_prompt.txt"
LIVE_SESSION_FILE = CONFIG_DIR / "live_session.json"

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


def load_conversations() -> list[dict]:
    if not LOGS_DIR.exists():
        return []
    convs = []
    for f in sorted(LOGS_DIR.glob("conversation_*.json"), reverse=True):
        try:
            convs.append(json.loads(f.read_text()))
        except Exception:
            pass
    return convs


def load_config() -> dict:
    default = {"provider": "openai_realtime", "voice": "verse"}
    try:
        return {**default, **json.loads(CONFIG_FILE.read_text())}
    except Exception:
        return default


def load_prompts() -> list[dict]:
    try:
        return json.loads(PROMPTS_FILE.read_text())
    except Exception:
        return []


def fmt_duration(secs: int) -> str:
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"


# ── Auth endpoints ───────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_page(error: str = ""):
    err_html = f'<div class="error">{error}</div>' if error else ""
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SeeVu — Sign in</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg viewBox='0 0 40 40' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='40' y2='40' gradientUnits='userSpaceOnUse'%3E%3Cstop stop-color='%2338C6F4'/%3E%3Cstop offset='1' stop-color='%230B5CAD'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='40' height='40' rx='9' fill='url(%23g)'/%3E%3Cpath d='M8 21 Q14 14 20 14 Q26 14 32 21 Q26 28 20 28 Q14 28 8 21Z' fill='white'/%3E%3Ccircle cx='20' cy='21' r='5.5' fill='%231EA7F2'/%3E%3C/svg%3E">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
    background: #08111F; min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background-image: radial-gradient(ellipse at 50% 0%, rgba(30,167,242,.12) 0%, transparent 60%);
  }}
  .card {{
    background: #0C1728; border: 1px solid rgba(56,198,244,.18); border-radius: 16px;
    padding: 40px; width: 360px;
    box-shadow: 0 24px 64px rgba(0,0,0,.5), 0 0 0 1px rgba(56,198,244,.06);
  }}
  .logo {{ display: flex; flex-direction: column; align-items: center; gap: 14px; margin-bottom: 32px; }}
  .logo-icon {{ flex-shrink: 0; }}
  .logo-text {{ font-size: 26px; font-weight: 800; color: #EAF6FF; letter-spacing: -.03em; }}
  .logo-text span {{ color: #38C6F4; }}
  .logo-sub {{ font-size: 12px; color: #4A6A88; letter-spacing: .04em; text-transform: uppercase; font-weight: 600; margin-top: -8px; }}
  .divider {{ height: 1px; background: rgba(56,198,244,.12); margin-bottom: 28px; }}
  label {{ display: block; font-size: 11px; font-weight: 600; color: #8FA8C3;
    text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }}
  input {{
    width: 100%; padding: 10px 13px; border: 1px solid rgba(56,198,244,.18);
    border-radius: 8px; font-size: 14px; color: #EAF6FF;
    background: #08111F; margin-bottom: 16px; outline: none;
    transition: border-color .15s, box-shadow .15s; font-family: inherit;
  }}
  input:focus {{ border-color: #1EA7F2; box-shadow: 0 0 0 3px rgba(30,167,242,.15); }}
  input::placeholder {{ color: #4A6A88; }}
  button {{
    width: 100%; padding: 11px; border: none; border-radius: 8px;
    background: linear-gradient(135deg, #1EA7F2, #38C6F4);
    color: #fff; font-size: 14px; font-weight: 700;
    cursor: pointer; transition: all .15s; margin-top: 6px;
    letter-spacing: .01em; font-family: inherit;
  }}
  button:hover {{ background: linear-gradient(135deg, #0B98E0, #1EA7F2); box-shadow: 0 4px 16px rgba(30,167,242,.4); transform: translateY(-1px); }}
  button:active {{ transform: translateY(0); }}
  button:disabled {{ opacity: .5; cursor: default; transform: none; box-shadow: none; }}
  .error {{ background: rgba(220,38,38,.15); color: #f87171; border: 1px solid rgba(220,38,38,.3); border-radius: 8px;
    padding: 10px 13px; font-size: 13px; margin-bottom: 16px; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <svg viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg" style="width:60px;height:60px" class="logo-icon">
      <defs>
        <linearGradient id="sv-login" x1="0" y1="0" x2="60" y2="60" gradientUnits="userSpaceOnUse">
          <stop stop-color="#38C6F4"/>
          <stop offset="1" stop-color="#0B5CAD"/>
        </linearGradient>
      </defs>
      <rect width="60" height="60" rx="14" fill="url(#sv-login)"/>
      <path d="M11 30 Q20 20 30 20 Q40 20 49 30 Q40 40 30 40 Q20 40 11 30Z" fill="white"/>
      <circle cx="30" cy="30" r="8" fill="#1EA7F2"/>
      <path d="M22 30v3.5M25.5 27v7M29 28.5v5M32.5 26v8M36 27.5v6" stroke="white" stroke-width="2.2" stroke-linecap="round"/>
      <rect x="41" y="8" width="3.5" height="3.5" rx=".8" fill="rgba(255,255,255,.7)"/>
      <rect x="46.5" y="8" width="3.5" height="3.5" rx=".8" fill="rgba(255,255,255,.45)"/>
      <rect x="43.5" y="13" width="3" height="3" rx=".7" fill="rgba(255,255,255,.3)"/>
      <rect x="7" y="43" width="3.5" height="3.5" rx=".8" fill="rgba(255,255,255,.7)"/>
      <rect x="12.5" y="43" width="3.5" height="3.5" rx=".8" fill="rgba(255,255,255,.45)"/>
      <rect x="7" y="48.5" width="3" height="3" rx=".7" fill="rgba(255,255,255,.3)"/>
    </svg>
    <div class="logo-text">See<span>Vu</span></div>
    <div class="logo-sub">AI Call Automation</div>
  </div>
  <div class="divider"></div>
  {err_html}
  <label for="u">Username</label>
  <input id="u" type="text" placeholder="Enter your username" autocomplete="username">
  <label for="p">Password</label>
  <input id="p" type="password" placeholder="Enter your password" autocomplete="current-password">
  <button id="btn" onclick="doLogin()">Sign in</button>
</div>
<script>
  document.addEventListener('keydown', e => {{ if (e.key === 'Enter') doLogin(); }});
  async function doLogin() {{
    const btn = document.getElementById('btn');
    btn.disabled = true;
    const res = await fetch('/api/login', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{username: document.getElementById('u').value, password: document.getElementById('p').value}}),
    }});
    if (res.ok) {{ window.location.href = '/'; }}
    else {{ window.location.href = '/login?error=Invalid+credentials'; }}
    btn.disabled = false;
  }}
</script>
</body>
</html>""")


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


@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        _sessions.pop(token, None)
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp


# ── API ──────────────────────────────────────────────────────────────────────

@app.get("/api/conversations")
def api_conversations():
    return load_conversations()


@app.get("/api/config")
def api_get_config():
    return load_config()


@app.post("/api/config")
async def api_set_config(payload: dict):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(payload, indent=2))
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
        prompts = load_prompts()
        prompts.append({"id": str(uuid.uuid4())[:8], "name": name, "lang": lang, "content": content})
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PROMPTS_FILE.write_text(json.dumps(prompts, indent=2, ensure_ascii=False))
        return {"ok": True, "prompts": prompts}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/prompt/apply")
async def api_apply_prompt(payload: dict):
    content = payload.get("content", "").strip()
    if not content:
        return JSONResponse({"ok": False, "error": "content required"}, status_code=400)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        ACTIVE_PROMPT_FILE.write_text(content, encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/live-session")
def api_live_session():
    try:
        return json.loads(LIVE_SESSION_FILE.read_text())
    except Exception:
        return {"active": False, "turns": []}


@app.get("/api/providers")
def api_providers():
    return PROVIDERS


@app.get("/api/audio/{track}/{session_id}")
def api_audio(track: str, session_id: str):
    if track not in ("bot", "user"):
        raise HTTPException(status_code=400, detail="track must be bot or user")
    path = LOGS_DIR / f"audio_{track}_{session_id}.wav"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/analyze/{session_id}")
async def api_analyze(session_id: str):
    path = LOGS_DIR / f"conversation_{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")

    data = json.loads(path.read_text())

    if "analysis" in data:
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
        analysis = {
            "sentiment": "neutral",
            "productive": False,
            "summary": raw,
            "highlights": [],
        }

    data["analysis"] = analysis
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return analysis


# ── Static frontend ──────────────────────────────────────────────────────────

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
