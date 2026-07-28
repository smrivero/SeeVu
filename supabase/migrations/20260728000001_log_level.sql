-- Nivel de detalle del log de bot.py, elegible desde el dashboard (Test Call).
alter table app_config add column if not exists log_level text default 'INFO';
