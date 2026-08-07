-- Historial de conversaciones de texto (pantalla Chat).
create table if not exists chat_conversations (
  session_id       text primary key,
  started_at       timestamptz default now(),
  updated_at       timestamptz default now(),
  messages         jsonb default '[]'::jsonb,
  created_by       uuid references auth.users(id),
  created_by_email text
);
alter table chat_conversations disable row level security;
