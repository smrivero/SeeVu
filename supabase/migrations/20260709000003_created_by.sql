-- ================================================================
-- SeeVu — Tracking de usuario que inició cada conversación
-- ================================================================

-- Quién guardó la conversación (UUID FK + email denormalizado para display sin joins)
alter table public.conversations
  add column if not exists created_by       uuid references auth.users(id),
  add column if not exists created_by_email text;

-- Quién está a punto de hacer la próxima llamada (se actualiza desde el dashboard)
alter table public.live_session
  add column if not exists initiated_by       uuid references auth.users(id),
  add column if not exists initiated_by_email text;
