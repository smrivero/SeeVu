#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import datetime
import io
import json
import os
import wave
from typing import Optional

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    MetricsFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
)
from pipecat.metrics.metrics import LLMUsageMetricsData, TTSUsageMetricsData
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.openai.realtime import events
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner
from supabase import AsyncClient, acreate_client, create_client

load_dotenv(override=True)

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "agents_prompts", "agent_constructor.txt")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE", "")

OPENAI_REALTIME_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_prompt() -> str:
    try:
        db = create_client(SUPABASE_URL, SUPABASE_KEY)
        res = db.table("active_prompt").select("content").eq("id", 1).single().execute()
        content = (res.data or {}).get("content", "").strip()
        if content:
            return content
    except Exception as e:
        logger.warning(f"Could not load prompt from Supabase: {e}")
    try:
        with open(_PROMPT_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def load_config() -> dict:
    default = {"provider": "openai_realtime", "voice": "verse"}
    try:
        db = create_client(SUPABASE_URL, SUPABASE_KEY)
        res = db.table("app_config").select("provider,voice").eq("id", 1).single().execute()
        return {**default, **(res.data or {})}
    except Exception as e:
        logger.warning(f"Could not load config from Supabase: {e}")
        return default


async def _write_live_session(db: AsyncClient, data: dict):
    try:
        await db.table("live_session").update({**data, "updated_at": _now()}).eq("id", 1).execute()
    except Exception as e:
        logger.warning(f"Failed to write live session: {e}")


class ConversationLogger(FrameProcessor):
    """Captures LLM text frames and user transcriptions for the live session and final save."""

    def __init__(self, config: dict, started_at: datetime.datetime, db: AsyncClient):
        super().__init__()
        self._turns: list[dict] = []
        self._bot_buffer: list[str] = []
        self._config = config
        self._started_at = started_at
        self._db = db

    async def add_user_turn(self, text: str):
        if text:
            self._turns.append({"role": "user", "content": text})
            await self._flush_live()

    def get_turns(self) -> list[dict]:
        if self._bot_buffer:
            self._turns.append({"role": "assistant", "content": "".join(self._bot_buffer).strip()})
            self._bot_buffer = []
        return self._turns

    async def _flush_live(self):
        turns = list(self._turns)
        if self._bot_buffer:
            turns.append({"role": "assistant", "content": "".join(self._bot_buffer).strip() + "…"})
        asyncio.create_task(_write_live_session(self._db, {
            "active": True,
            "started_at": self._started_at.isoformat(),
            "config": self._config,
            "turns": turns,
        }))

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame) and frame.text:
            self._bot_buffer.append(frame.text)
            await self._flush_live()
        elif isinstance(frame, LLMFullResponseEndFrame) and self._bot_buffer:
            self._turns.append({"role": "assistant", "content": "".join(self._bot_buffer).strip()})
            self._bot_buffer = []
            await self._flush_live()
        await self.push_frame(frame, direction)


class UserTranscriptCapture(FrameProcessor):
    """Placed BEFORE the LLM to intercept upstream TranscriptionFrames.

    OpenAIRealtimeLLMService pushes TranscriptionFrame upstream (back toward
    transport.input), so any processor placed after the LLM in the pipeline
    never sees them. This processor sits between transport.input and the LLM
    and catches those upstream frames before they leave the pipeline.
    """

    def __init__(self, conv_logger: ConversationLogger):
        super().__init__()
        self._conv_logger = conv_logger

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if (
            isinstance(frame, TranscriptionFrame)
            and frame.text
            and direction == FrameDirection.UPSTREAM
        ):
            await self._conv_logger.add_user_turn(frame.text)
        await self.push_frame(frame, direction)


class MetricsCollector(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.llm_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.tts_characters = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, MetricsFrame):
            for d in frame.data:
                if isinstance(d, LLMUsageMetricsData):
                    self.llm_usage["prompt_tokens"] += d.value.prompt_tokens
                    self.llm_usage["completion_tokens"] += d.value.completion_tokens
                    self.llm_usage["total_tokens"] += d.value.total_tokens
                elif isinstance(d, TTSUsageMetricsData):
                    self.tts_characters += d.value
        await self.push_frame(frame, direction)


class AudioRecorder(FrameProcessor):
    """Captures input (user) and output (bot) audio frames, uploads to Supabase Storage."""

    def __init__(self):
        super().__init__()
        self._bot_chunks: list[bytes] = []
        self._user_chunks: list[bytes] = []
        self._bot_rate: int = 24000
        self._user_rate: int = 24000
        self._channels: int = 1

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputAudioRawFrame):
            self._bot_chunks.append(frame.audio)
            self._bot_rate = frame.sample_rate
            self._channels = frame.num_channels
        elif isinstance(frame, InputAudioRawFrame):
            self._user_chunks.append(frame.audio)
            self._user_rate = frame.sample_rate
        await self.push_frame(frame, direction)

    def _make_wav_bytes(self, chunks: list[bytes], rate: int, channels: int) -> bytes | None:
        if not chunks:
            return None
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(b"".join(chunks))
        return buf.getvalue()

    async def save(self, session_id: str, db: AsyncClient) -> dict[str, bool]:
        results = {"bot": False, "user": False}
        uploads = [
            ("bot", self._make_wav_bytes(self._bot_chunks, self._bot_rate, self._channels)),
            ("user", self._make_wav_bytes(self._user_chunks, self._user_rate, self._channels)),
        ]
        for track, data in uploads:
            if not data:
                continue
            try:
                await db.storage.from_("audio").upload(
                    f"{track}_{session_id}.wav",
                    data,
                    {"content-type": "audio/wav", "upsert": "true"},
                )
                results[track] = True
                logger.info(f"Audio uploaded: {track}_{session_id}.wav ({len(data)} bytes)")
            except Exception as e:
                logger.error(f"Failed to upload {track} audio: {e}")
        return results


async def get_call_info(call_sid: str) -> dict:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return {}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=aiohttp.BasicAuth(account_sid, auth_token)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                return {"from_number": data.get("from"), "to_number": data.get("to")}
    except Exception as e:
        logger.error(f"Error fetching call info: {e}")
        return {}


async def save_conversation(
    turns: list[dict],
    call_info: dict,
    started_at: datetime.datetime,
    metrics: MetricsCollector,
    config: dict,
    audio: dict[str, bool],
    db: AsyncClient,
    created_by: str | None = None,
    created_by_email: str | None = None,
):
    ended_at = datetime.datetime.now()
    session_id = started_at.strftime("%Y%m%d_%H%M%S")
    data = {
        "session_id": session_id,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_seconds": round((ended_at - started_at).total_seconds()),
        "call_info": call_info,
        "config": config,
        "has_audio_bot": audio.get("bot", False),
        "has_audio_user": audio.get("user", False),
        "messages": turns,
        "usage": {
            "llm": metrics.llm_usage,
            "tts_characters": metrics.tts_characters,
        },
    }
    if created_by:
        data["created_by"] = created_by
    if created_by_email:
        data["created_by_email"] = created_by_email
    await db.table("conversations").upsert(data).execute()
    logger.info(f"Conversation saved to Supabase: {session_id}")


async def run_bot(
    transport: BaseTransport,
    handle_sigint: bool,
    testing: bool,
    call_info: dict | None = None,
):
    system_prompt = load_prompt()
    config = load_config()
    voice = config.get("voice", "verse")
    if voice not in OPENAI_REALTIME_VOICES:
        voice = "verse"

    logger.info(f"Starting with provider=openai_realtime voice={voice}")

    db: AsyncClient = await acreate_client(SUPABASE_URL, SUPABASE_KEY)

    # Quién inició la sesión desde el dashboard (puede ser None para llamadas externas)
    _initiated_by: str | None = None
    _initiated_by_email: str | None = None
    try:
        ls = await db.table("live_session").select("initiated_by,initiated_by_email").eq("id", 1).execute()
        if ls.data:
            _initiated_by = ls.data[0].get("initiated_by")
            _initiated_by_email = ls.data[0].get("initiated_by_email")
    except Exception:
        pass

    llm = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAIRealtimeLLMService.Settings(
            system_instruction=system_prompt,
            session_properties=events.SessionProperties(
                audio=events.AudioConfiguration(
                    input=events.AudioInput(
                        format=events.PCMAudioFormat(),
                        transcription=events.InputAudioTranscription(
                            model="gpt-4o-transcribe",
                            language="en",
                        ),
                        turn_detection=events.TurnDetection(
                            type="server_vad",
                            threshold=0.5,
                            prefix_padding_ms=200,
                            silence_duration_ms=400,
                        ),
                    ),
                    output=events.AudioOutput(
                        format=events.PCMAudioFormat(),
                        voice=voice,
                    ),
                ),
            ),
        ),
    )

    started_at = datetime.datetime.now()
    conv_logger = ConversationLogger(config, started_at, db)
    user_capture = UserTranscriptCapture(conv_logger)
    metrics_collector = MetricsCollector()
    audio_recorder = AudioRecorder()

    pipeline = Pipeline([
        transport.input(),
        user_capture,
        llm,
        conv_logger,
        metrics_collector,
        audio_recorder,
        transport.output(),
    ])

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=24000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal started_at
        started_at = datetime.datetime.now()
        conv_logger._started_at = started_at
        await _write_live_session(db, {
            "active": True,
            "started_at": started_at.isoformat(),
            "config": config,
            "turns": [],
        })
        await worker.queue_frames([LLMContext()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await _write_live_session(db, {"active": False, "turns": []})
        session_id = started_at.strftime("%Y%m%d_%H%M%S")
        audio = await audio_recorder.save(session_id, db)
        await save_conversation(
            conv_logger.get_turns(),
            call_info or {},
            started_at,
            metrics_collector,
            config,
            audio,
            db,
            created_by=_initiated_by,
            created_by_email=_initiated_by_email,
        )
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=handle_sigint, force_gc=True)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments, testing: Optional[bool] = False):
    """Main bot entry point compatible with Pipecat Cloud."""
    _, call_data = await parse_telephony_websocket(runner_args.websocket)
    call_info = await get_call_info(call_data["call_id"])
    if call_info:
        logger.info(f"Call from: {call_info.get('from_number')} to: {call_info.get('to_number')}")

    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data["call_id"],
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    await run_bot(transport, runner_args.handle_sigint, testing, call_info)


if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
