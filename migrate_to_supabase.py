"""
Migrates local JSON data to Supabase.
Run AFTER applying supabase_schema.sql in the Supabase SQL Editor.

Usage:
    uv run migrate_to_supabase.py
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(override=True)

db = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE", ""))

CONFIG_DIR = Path("bot_config")
LOGS_DIR   = Path("conversation_logs")

# ── Prompts ───────────────────────────────────────────────────────────────────
prompts_file = CONFIG_DIR / "prompts.json"
if prompts_file.exists():
    prompts = json.loads(prompts_file.read_text())
    if prompts:
        db.table("prompts").upsert(prompts).execute()
        print(f"✓ Migrated {len(prompts)} prompt(s)")
    else:
        print("  No prompts to migrate")
else:
    print("  No prompts.json found")

# ── Active prompt ──────────────────────────────────────────────────────────────
active_file = CONFIG_DIR / "active_prompt.txt"
if active_file.exists():
    content = active_file.read_text(encoding="utf-8").strip()
    if content:
        db.table("active_prompt").update({"content": content}).eq("id", 1).execute()
        print("✓ Migrated active prompt")

# ── Config ────────────────────────────────────────────────────────────────────
config_file = CONFIG_DIR / "settings.json"
if config_file.exists():
    cfg = json.loads(config_file.read_text())
    db.table("app_config").update(cfg).eq("id", 1).execute()
    print(f"✓ Migrated config: {cfg}")

# ── Conversations ─────────────────────────────────────────────────────────────
if LOGS_DIR.exists():
    files = sorted(LOGS_DIR.glob("conversation_*.json"))
    if files:
        convs = []
        for f in files:
            try:
                convs.append(json.loads(f.read_text()))
            except Exception as e:
                print(f"  ✗ Skipped {f.name}: {e}")
        if convs:
            # Keep only columns that exist in the schema
            COLS = {"session_id","started_at","ended_at","duration_seconds",
                    "call_info","config","has_audio_bot","has_audio_user",
                    "messages","usage","analysis"}
            clean = [{k: v for k, v in c.items() if k in COLS} for c in convs]
            db.table("conversations").upsert(clean).execute()
            print(f"✓ Migrated {len(clean)} conversation(s)")
    else:
        print("  No conversation files found")
else:
    print("  No conversation_logs/ directory found")

print("\nDone. You can now remove the fallback code from dashboard.py if everything looks correct.")
