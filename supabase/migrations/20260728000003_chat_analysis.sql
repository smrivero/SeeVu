-- Resultado de análisis de sentimiento para conversaciones de chat.
alter table chat_conversations add column if not exists analysis jsonb;
