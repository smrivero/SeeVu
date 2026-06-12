#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import datetime
import io
import os
import wave
from typing import Optional

import aiofiles
import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TTSAudioRawFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)


async def get_call_info(call_sid: str) -> dict:
    """Fetch call information from Twilio REST API using aiohttp.

    Args:
        call_sid: The Twilio call SID

    Returns:
        Dictionary containing call information including from_number, to_number, status, etc.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    if not account_sid or not auth_token:
        logger.warning("Missing Twilio credentials, cannot fetch call info")
        return {}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json"

    try:
        # Use HTTP Basic Auth with aiohttp
        auth = aiohttp.BasicAuth(account_sid, auth_token)

        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=auth) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Twilio API error ({response.status}): {error_text}")
                    return {}

                data = await response.json()

                call_info = {
                    "from_number": data.get("from"),
                    "to_number": data.get("to"),
                }

                return call_info

    except Exception as e:
        logger.error(f"Error fetching call info from Twilio: {e}")
        return {}


class CachedOpenAITTSService(OpenAITTSService):
    """OpenAITTSService that caches generated audio for repeated text.

    Useful for fixed messages (e.g. the welcome greeting) so they're only
    synthesized once via the API and reused on subsequent calls.
    """

    _audio_cache: dict[str, list[bytes]] = {}

    async def run_tts(self, text: str, context_id: str):
        cached = self._audio_cache.get(text)
        if cached is not None:
            await self.start_tts_usage_metrics(text)
            await self.stop_ttfb_metrics()
            for chunk in cached:
                yield TTSAudioRawFrame(chunk, self.sample_rate, 1, context_id=context_id)
            return

        chunks: list[bytes] = []
        async for frame in super().run_tts(text, context_id):
            if isinstance(frame, TTSAudioRawFrame):
                chunks.append(frame.audio)
            yield frame
        self._audio_cache[text] = chunks


async def save_audio(audio: bytes, sample_rate: int, num_channels: int):
    if len(audio) > 0:
        filename = f"recording_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        with io.BytesIO() as buffer:
            with wave.open(buffer, "wb") as wf:
                wf.setsampwidth(2)
                wf.setnchannels(num_channels)
                wf.setframerate(sample_rate)
                wf.writeframes(audio)
            async with aiofiles.open(filename, "wb") as file:
                await file.write(buffer.getvalue())
        logger.info(f"Merged audio saved to {filename}")
    else:
        logger.info("No audio data to save")


async def save_conversation(messages: list[dict], call_info: dict):
    folder = "conversation_logs"
    os.makedirs(folder, exist_ok=True)

    now = datetime.datetime.now()
    filename = os.path.join(folder, f"conversation_{now.strftime('%Y%m%d_%H%M%S')}.txt")

    lines = [f"Fecha: {now.isoformat()}"]
    if call_info:
        lines.append(f"De: {call_info.get('from_number')} a: {call_info.get('to_number')}")
    lines.append("")

    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        lines.append(f"{role}: {message.get('content')}")

    async with aiofiles.open(filename, "w") as file:
        await file.write("\n".join(lines))
    logger.info(f"Conversation saved to {filename}")


async def run_bot(
    transport: BaseTransport, handle_sigint: bool, testing: bool, call_info: dict | None = None
):
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            model="gpt-4o-mini",
        ),
    )

    stt = OpenAISTTService(
        api_key=os.getenv("OPENAI_API_KEY"),
        language=Language.ES,
    )

    tts = CachedOpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        sample_rate=24000,
        settings=CachedOpenAITTSService.Settings(
            voice="alloy",
            model="tts-1",
        ),
    )

    welcome_message = "Bienvenido a Acrons, en que podemos ayudarte?"

    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": (
                    "Sos un agente de soporte al cliente de Acrons atendiendo una llamada "
                    "telefonica. Respondes siempre en espanol. Tu salida se convierte a audio, "
                    "asi que no uses caracteres especiales. Responde con oraciones cortas y "
                    "claras.\n\n"
                    "Segui siempre este flujo de conversacion:\n"
                    "1. Antes de responder cualquier consulta, pedile amablemente al usuario "
                    "su nombre, edad y numero de documento.\n"
                    "2. Una vez que tengas esos tres datos, ofrecele elegir entre estas tres "
                    "opciones diciendo el numero o el nombre de la opcion: "
                    "1) Ver Facturacion y pagos, 2) Cambio de Plan, 3) Otros Problemas.\n"
                    "3. Segun la opcion que elija:\n"
                    "   - Opcion 1 (Ver Facturacion y pagos): decile 'Estas en el menu Ver "
                    "Facturacion y pagos' y a continuacion 'No tienes deuda actual'.\n"
                    "   - Opcion 2 (Cambio de Plan): decile 'Estas en el menu Cambio de Plan' "
                    "y a continuacion 'Tu plan actual es Movistar 10GB, por cual plan quieres "
                    "actualizar?'.\n"
                    "   - Opcion 3 (Otros Problemas): decile 'Estas en el menu Otros "
                    "Problemas' y a continuacion 'Que problema quieres reportar?'.\n"
                    "4. A partir de ahi, continua ayudando al usuario dentro del menu elegido."
                ),
            },
            {
                "role": "assistant",
                "content": welcome_message,
            },
        ]
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # NOTE: Watch out! This will save all the conversation in memory. You can
    # pass `buffer_size` to get periodic callbacks.
    audiobuffer = AudioBufferProcessor()

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            user_aggregator,
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            audiobuffer,  # Used to buffer the audio in the pipeline
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Start recording.
        await audiobuffer.start_recording()
        # Kick off the conversation with a fixed welcome message.
        await worker.queue_frames([TTSSpeakFrame(welcome_message)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await save_conversation(context.messages, call_info or {})
        await worker.cancel()

    @audiobuffer.event_handler("on_audio_data")
    async def on_audio_data(buffer, audio, sample_rate, num_channels):
        await save_audio(audio, sample_rate, num_channels)

    # We use `handle_sigint=False` because `uvicorn` is controlling keyboard
    # interruptions. We use `force_gc=True` to force garbage collection after
    # the runner finishes running a task which could be useful for long running
    # applications with multiple clients connecting.
    runner = WorkerRunner(handle_sigint=handle_sigint, force_gc=True)

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments, testing: Optional[bool] = False):
    """Main bot entry point compatible with Pipecat Cloud."""

    _, call_data = await parse_telephony_websocket(runner_args.websocket)

    # Fetch call information from Twilio REST API
    # With the call information, you can make a request to your API to get the user's information
    # and inject that information into your bot's configuration.
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
