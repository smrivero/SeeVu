-- ================================================================
-- SeeVu — Schema inicial (conversaciones, config, prompts)
-- ================================================================

-- Conversaciones grabadas
create table if not exists conversations (
  session_id       text primary key,
  started_at       timestamptz,
  ended_at         timestamptz,
  duration_seconds integer default 0,
  call_info        jsonb   default '{}'::jsonb,
  config           jsonb   default '{}'::jsonb,
  has_audio_bot    boolean default false,
  has_audio_user   boolean default false,
  messages         jsonb   default '[]'::jsonb,
  usage            jsonb   default '{}'::jsonb,
  analysis         jsonb,
  created_at       timestamptz default now()
);

-- Sesión en vivo (fila única, id siempre = 1)
create table if not exists live_session (
  id         integer primary key default 1,
  active     boolean default false,
  started_at timestamptz,
  config     jsonb default '{}'::jsonb,
  turns      jsonb default '[]'::jsonb,
  updated_at timestamptz default now()
);
insert into live_session (id) values (1) on conflict do nothing;

-- Configuración del bot (fila única, id siempre = 1)
create table if not exists app_config (
  id         integer primary key default 1,
  provider   text default 'openai_realtime',
  voice      text default 'verse',
  updated_at timestamptz default now()
);
insert into app_config (id) values (1) on conflict do nothing;

-- Prompts guardados
create table if not exists prompts (
  id         text primary key,
  name       text not null,
  lang       text default 'en',
  content    text not null,
  created_at timestamptz default now()
);

-- Prompt activo (fila única, id siempre = 1)
create table if not exists active_prompt (
  id         integer primary key default 1,
  content    text default '',
  updated_at timestamptz default now()
);
insert into active_prompt (id) values (1) on conflict do nothing;

-- RLS desactivado: acceso solo desde backend con service_role key
alter table conversations  disable row level security;
alter table live_session   disable row level security;
alter table app_config     disable row level security;
alter table prompts        disable row level security;
alter table active_prompt  disable row level security;
