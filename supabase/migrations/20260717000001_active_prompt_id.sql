-- Guarda qué prompt guardado está activo (para el selector del dashboard)
alter table active_prompt
  add column if not exists prompt_id text;
