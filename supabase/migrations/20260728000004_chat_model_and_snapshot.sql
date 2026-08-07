-- Modelo de OpenAI configurable para el chat de texto (Settings).
alter table app_config add column if not exists chat_model text default 'gpt-4o-mini';

-- Prompt y modelo quedan "congelados" al crear la sesión de chat, para que
-- cambios posteriores en Settings no afecten una conversación en curso.
alter table chat_conversations add column if not exists prompt_snapshot text;
alter table chat_conversations add column if not exists model text;
