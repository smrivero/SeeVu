-- ================================================================
-- SeeVu — Roles y user_roles (Supabase Auth)
-- ================================================================

-- Tabla de roles
create table if not exists public.roles (
  id          uuid        primary key default gen_random_uuid(),
  name        text        unique not null,
  description text,
  created_at  timestamptz default now()
);

-- Vinculación usuario ↔ rol (usa auth.users nativa de Supabase)
create table if not exists public.user_roles (
  id         uuid        primary key default gen_random_uuid(),
  user_id    uuid        not null references auth.users(id) on delete cascade,
  role_id    uuid        not null references public.roles(id) on delete restrict,
  created_at timestamptz default now(),
  unique(user_id, role_id)
);

create index if not exists idx_user_roles_user_id on public.user_roles(user_id);
create index if not exists idx_user_roles_role_id on public.user_roles(role_id);

-- Roles iniciales
insert into public.roles (name, description) values
  ('superadmin',    'Full access to all resources'),
  ('company_admin', 'Admin of a specific company'),
  ('user',          'Standard authenticated user')
on conflict (name) do nothing;

-- RLS activado: el backend (service_role) lo bypasea siempre.
-- Las políticas protegen acceso directo desde clientes externos.
alter table public.roles      enable row level security;
alter table public.user_roles enable row level security;

-- Cualquier usuario autenticado puede leer la lista de roles
create policy "roles_select"
  on public.roles for select
  to authenticated using (true);

-- Cada usuario solo puede leer sus propias asignaciones
create policy "user_roles_select_own"
  on public.user_roles for select
  to authenticated using (auth.uid() = user_id);
