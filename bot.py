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
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    LLMFullResponseEndFrame,
    LLMRunFrame,
    LLMTextFrame,
    MetricsFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
)
from pipecat.metrics.metrics import LLMUsageMetricsData, TTSUsageMetricsData
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy
from pipecat.turns.user_mute.mute_until_first_bot_complete_user_mute_strategy import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
)
from pipecat.turns.user_turn_completion_mixin import UserTurnCompletionConfig
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
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

# ── File logging (shared with dashboard via conversation_logs/ volume) ────────
_LOG_DIR = os.path.join(os.path.dirname(__file__), "conversation_logs")
os.makedirs(_LOG_DIR, exist_ok=True)
logger.add(
    os.path.join(_LOG_DIR, "bot.log"),
    rotation="10 MB",
    retention=3,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
)

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "agents_prompts", "agent_constructor.txt")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE", "")

PROVIDER_OPENAI_REALTIME = "openai_realtime"
PROVIDER_DEEPGRAM_CARTESIA = "deepgram_openai_cartesia"

OPENAI_REALTIME_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]
CARTESIA_DEFAULT_VOICE = "71a7ad14-091c-4e8e-a314-022ece01c121"
CARTESIA_VOICES = {
    "71a7ad14-091c-4e8e-a314-022ece01c121",
    "a0e99841-438c-4a64-b679-ae501e7d6091",
    "794f9389-aac1-45b6-b726-9d9369183238",
    "e13cae5c-ec59-4f71-b0a6-266df3c9bb8e",
    "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
}


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
            full = "".join(self._bot_buffer).strip()
            logger.info(f"[LLM→TTS] BOT: {full[:200]}{'…' if len(full) > 200 else ''}")
            self._turns.append({"role": "assistant", "content": full})
            self._bot_buffer = []
            await self._flush_live()
        await self.push_frame(frame, direction)


class UserTranscriptCapture(FrameProcessor):
    """Captures user TranscriptionFrames for conversation logging.

    OpenAI Realtime pushes TranscriptionFrame upstream (back toward
    transport.input). Deepgram STT pushes them downstream. This processor
    accepts either direction so both pipelines can share the same logger.
    """

    def __init__(self, conv_logger: ConversationLogger):
        super().__init__()
        self._conv_logger = conv_logger

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text:
            logger.info(f"[STT→LLM] USER: {frame.text}")
            await self._conv_logger.add_user_turn(frame.text)
        elif isinstance(frame, InterimTranscriptionFrame):
            logger.info(f"[STT interim] {frame.text!r}")
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
    provider = config.get("provider", PROVIDER_OPENAI_REALTIME)
    voice = config.get("voice", "verse")

    if provider == PROVIDER_DEEPGRAM_CARTESIA:
        if voice not in CARTESIA_VOICES:
            voice = CARTESIA_DEFAULT_VOICE
    else:
        provider = PROVIDER_OPENAI_REALTIME
        if voice not in OPENAI_REALTIME_VOICES:
            voice = "verse"

    logger.info(f"Starting with provider={provider} voice={voice}")

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

    started_at = datetime.datetime.now()
    conv_logger = ConversationLogger(config, started_at, db)
    user_capture = UserTranscriptCapture(conv_logger)
    metrics_collector = MetricsCollector()
    audio_recorder = AudioRecorder()

    if provider == PROVIDER_DEEPGRAM_CARTESIA:
        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            settings=OpenAILLMService.Settings(
                model="gpt-4o-mini",
                system_instruction=system_prompt,
            ),
        )
        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            settings=CartesiaTTSService.Settings(voice=voice),
            push_silence_after_stop=True,
        )
        context = LLMContext()
        # Soft kickoff so the bot greets according to the active system prompt.
        context.add_message({
            "role": "user",
            "content": (
                "The call just connected. Greet the user and begin according "
                "to your instructions."
            ),
        })
        context_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                vad_analyzer=SileroVADAnalyzer(
                    params=VADParams(
                        start_secs=0.2,
                        stop_secs=0.2,
                        min_volume=0.65,
                    )
                ),
                # Mute mic from call start until the bot finishes its first
                # utterance (prevents ambient noise from cancelling the
                # greeting before it ever reaches TTS), and keep muting
                # while the bot speaks afterwards (prevents speaker echo
                # from being picked up as user speech).
                user_mute_strategies=[
                    MuteUntilFirstBotCompleteUserMuteStrategy(),
                    AlwaysUserMuteStrategy(),
                ],
                # Smart Turn says INCOMPLETE for short phrases; reduce wait
                # from 5s default to 1.2s before processing the turn anyway.
                user_turn_completion_config=UserTurnCompletionConfig(
                    incomplete_short_timeout=1.2,
                    incomplete_long_timeout=3.0,
                ),
                # Deepgram's finalized transcript sometimes takes several
                # seconds to arrive (observed TTFB up to ~13s on this
                # connection). The old 3.0s timeout was firing the no-content
                # fallback path before the real transcript showed up, so the
                # turn closed empty and the LLM never got triggered.
                user_turn_stop_timeout=15.0,
            ),
        )
        pipeline = Pipeline([
            transport.input(),
            stt,
            user_capture,
            context_aggregator.user(),
            llm,
            conv_logger,
            tts,
            metrics_collector,
            audio_recorder,
            transport.output(),
            context_aggregator.assistant(),
        ])
        audio_in_sample_rate = 8000
        audio_out_sample_rate = 8000
        kickoff_frames = [LLMRunFrame()]
    else:
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
        pipeline = Pipeline([
            transport.input(),
            user_capture,
            llm,
            conv_logger,
            metrics_collector,
            audio_recorder,
            transport.output(),
        ])
        audio_in_sample_rate = 24000
        audio_out_sample_rate = 8000
        kickoff_frames = [LLMContext()]

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=audio_in_sample_rate,
            audio_out_sample_rate=audio_out_sample_rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal started_at
        started_at = datetime.datetime.now()
        conv_logger._started_at = started_at
        logger.info("=" * 60)
        logger.info(f"CALL CONNECTED — provider={provider}  voice={voice}")
        logger.info(f"  SUPABASE_URL set: {bool(SUPABASE_URL)}")
        logger.info(f"  SUPABASE_KEY set: {bool(SUPABASE_KEY)}")
        logger.info(f"  OPENAI_API_KEY set: {bool(os.getenv('OPENAI_API_KEY'))}")
        logger.info(f"  DEEPGRAM_API_KEY set: {bool(os.getenv('DEEPGRAM_API_KEY'))}")
        logger.info(f"  CARTESIA_API_KEY set: {bool(os.getenv('CARTESIA_API_KEY'))}")
        logger.info("=" * 60)
        await _write_live_session(db, {
            "active": True,
            "started_at": started_at.isoformat(),
            "config": config,
            "turns": [],
        })
        # For Deepgram+Cartesia: wait for Deepgram WS to connect and settle
        # before sending the kickoff. Without this, Silero VAD fires on the
        # initial audio burst the moment Deepgram connects (~2.4s after call
        # start), interrupting the LLM greeting before TTS can speak it.
        if provider == PROVIDER_DEEPGRAM_CARTESIA:
            await asyncio.sleep(3.5)
        await worker.queue_frames(kickoff_frames)

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
