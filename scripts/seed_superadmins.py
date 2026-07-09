#!/usr/bin/env python3
"""
Seed de desarrollo: crea los usuarios superadmin en Supabase Auth y asigna el rol.

Uso:
    python scripts/seed_superadmins.py

Requiere en .env (o variables de entorno):
    SUPABASE_URL=...
    SUPABASE_SERVICE_ROLE_KEY=...

Solo para DEV — no correr en producción con estos passwords hardcodeados.
"""

import os
import sys
from pathlib import Path

# Cargar .env si existe
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("ERROR: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY deben estar en .env")

try:
    from supabase import create_client
except ImportError:
    sys.exit("ERROR: instalar supabase → pip install supabase")

db = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Usuarios a crear ──────────────────────────────────────────────
# SEED DE DEV — no commiteees esto a producción con passwords reales
DEV_SUPERADMINS = [
    {"email": "upwork@upwork.demo",  "password": "UpWork123"},
    {"email": "acrons@acrons.demo",  "password": "Acrons123"},
]

# ── Helpers ───────────────────────────────────────────────────────

def get_superadmin_role_id() -> str:
    res = db.table("roles").select("id").eq("name", "superadmin").single().execute()
    if not res.data:
        sys.exit("ERROR: rol 'superadmin' no encontrado. Correr supabase_auth_roles.sql primero.")
    return res.data["id"]


def find_user_by_email(email: str):
    """Busca un usuario existente en auth.users por email."""
    users_resp = db.auth.admin.list_users()
    for u in users_resp:
        if hasattr(u, "email") and u.email == email:
            return u
    return None


def create_or_get_user(email: str, password: str):
    existing = find_user_by_email(email)
    if existing:
        print(f"  → Usuario ya existe: {email} (id={existing.id})")
        return existing

    resp = db.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True,   # confirmar email sin enviar correo
    })
    print(f"  ✓ Usuario creado: {email} (id={resp.user.id})")
    return resp.user


def assign_superadmin(user_id: str, role_id: str, email: str):
    existing = db.table("user_roles") \
        .select("id") \
        .eq("user_id", user_id) \
        .eq("role_id", role_id) \
        .execute()
    if existing.data:
        print(f"  → Rol ya asignado a {email}")
        return
    db.table("user_roles").insert({"user_id": user_id, "role_id": role_id}).execute()
    print(f"  ✓ Rol superadmin asignado a {email}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    print("=== Seed superadmins (DEV) ===")
    role_id = get_superadmin_role_id()
    print(f"Rol superadmin id: {role_id}\n")

    for spec in DEV_SUPERADMINS:
        print(f"Procesando {spec['email']}...")
        user = create_or_get_user(spec["email"], spec["password"])
        assign_superadmin(str(user.id), role_id, spec["email"])
        print()

    print("=== Listo ===")


if __name__ == "__main__":
    main()
