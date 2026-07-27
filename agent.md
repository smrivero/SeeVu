# Agent notes — SeeVu / pipecat

## Completado

- [x] Multi-provider en dashboard + bot:
  - `openai_realtime` — OpenAI Realtime (STT+LLM+TTS unificado)
  - `deepgram_openai_cartesia` — Deepgram STT + OpenAI LLM + Cartesia TTS
- [x] Voces Cartesia expuestas en Settings / Test Call
- [x] `DEEPGRAM_API_KEY` y `CARTESIA_API_KEY` en `env.example` (y placeholder en `.env`)
- [x] Extra `deepgram` añadido a `pipecat-ai` en `pyproject.toml`
- [x] Script local `dev.sh` para levantar/bajar API + bot + frontend de una

## Pendiente / próximos pasos

- [ ] Completar `DEEPGRAM_API_KEY` en `.env` (local) y en variables de Railway
- [ ] Confirmar `CARTESIA_API_KEY` en Railway (ya está en `.env` local)
- [ ] Redeploy bot + API para que `/api/providers` exponga la nueva opción
- [ ] Probar Test Call con ambos providers y validar audio + transcript en live session
- [ ] `uv sync` / rebuild imagen Docker para instalar el extra `deepgram`
- [ ] (Opcional) Filtrar transcripciones intermedias de Deepgram si aparecen turnos duplicados
- [ ] Probar `./dev.sh start` / `./dev.sh stop` en local

## Cómo elegir provider

1. Settings o Test Call → Provider → Apply
2. El bot lee `app_config` (Supabase) al inicio de cada sesión
3. Keys necesarias:
   - Realtime: `OPENAI_API_KEY`
   - Pipeline: `DEEPGRAM_API_KEY` + `OPENAI_API_KEY` + `CARTESIA_API_KEY`

## Dev local (script)

```bash
./dev.sh start     # API :8080 + bot :7860 + Vite :5174
./dev.sh stop
./dev.sh restart
./dev.sh status
./dev.sh logs      # o: logs api | bot | front
```

Front: http://localhost:5174  
Logs: `.dev/logs/`
