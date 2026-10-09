"""The single object the backend embeds to get live calls.

    live = LiveService(LiveSettings.from_env(), sink=HttpResultSink(url, token))
    app.include_router(live.router)                       # serves wss://<host>/live/exotel/<secret>

    res = provider.initiate_call(...)                     # ExotelProvider with EXOTEL_STREAM_URL set
    live.register_call(CallContext(provider_call_id=res.provider_call_id, attempt_id=..., participant_id=...,
                                   campaign_id=..., campaign=CampaignInfo(...), participant_name=...))

When the call ends the sink receives one `CallResult` (participant, campaign, attendance, call outcome).
Run a single worker: the default registry lives in process memory.
"""
import logging
from collections.abc import Callable

from fastapi import APIRouter

from ..integrations.base import ProviderEvent
from ..integrations.elevenlabs.client import ElevenLabsClient
from ..intelligence.transcription.elevenlabs_stt import ElevenLabsTranscriber
from .campaign import CallContext, CallContextSource, InMemoryCallRegistry, build_greeting
from .config import LiveSettings
from .exotel_ws import StartInfo, create_router
from .results import ResultSink, build_result
from .session import LiveSession
from .tts_cache import TtsCache

log = logging.getLogger("member3.live")


class LiveService:
    def __init__(self, settings: LiveSettings, sink: ResultSink, *, source: CallContextSource | None = None,
                 tts: Callable[[str, int], bytes] | None = None, stt: Callable[[bytes], str] | None = None,
                 on_event: Callable[[ProviderEvent], None] | None = None):
        """`tts(text, sample_rate) -> PCM` and `stt(wav_bytes) -> text` default to ElevenLabs; tests inject fakes.
        `on_event` also receives the legacy ProviderEvent(kind="response") if the backend still wants it."""
        self.settings, self.sink, self.on_event = settings, sink, on_event
        if tts is None or stt is None:
            eleven = ElevenLabsClient(settings.elevenlabs_api_key, voice_id=settings.elevenlabs_voice_id,
                                      tts_model=settings.elevenlabs_tts_model, stt_model=settings.elevenlabs_stt_model)
            tts = tts or eleven.speak_pcm
            stt = stt or ElevenLabsTranscriber(eleven).transcribe_bytes
        self.tts_cache = TtsCache(tts)
        self._stt = self._logged(stt) if settings.log_transcript else stt
        self.registry = InMemoryCallRegistry(on_register=self._prewarm)
        self.source: CallContextSource = source or self.registry
        self.router: APIRouter = create_router(session_factory=self._session, token=settings.webhook_token)

    # ---- backend-facing -------------------------------------------------------------------------
    def register_call(self, ctx: CallContext) -> None:
        self.registry.register(ctx)

    # ---- internals ------------------------------------------------------------------------------
    @staticmethod
    def _logged(stt: Callable[[bytes], str]) -> Callable[[bytes], str]:
        def run(wav: bytes) -> str:
            text = stt(wav)
            log.warning("TRANSCRIPT (dev only, personal data): %r", text)
            return text
        return run

    def _prewarm(self, ctx: CallContext) -> None:
        self.tts_cache.prewarm([build_greeting(ctx.campaign, ctx.participant_name)], self.settings.default_sample_rate)

    def _deliver(self, ctx: CallContext, session: LiveSession | None, outcome: str) -> None:
        try:
            self.sink(build_result(ctx, session.decision if session else None, call_outcome=outcome))
        except Exception:                      # a sink bug must never take the live call down
            log.exception("result sink failed for call %s", ctx.provider_call_id)

    def _session(self, info: StartInfo) -> LiveSession | None:
        ctx = self.source.get(info.call_sid, wait_s=self.settings.register_wait_s)
        if ctx is None:
            log.warning("no campaign registered for call_sid=%s; refusing stream", info.call_sid)
            return None
        rate, holder = info.sample_rate, {}

        def emit(ev: ProviderEvent) -> None:
            self._deliver(ctx, holder["s"], "completed")
            if self.on_event:
                self.on_event(ev)

        s = LiveSession(
            provider_call_id=ctx.provider_call_id, greeting=build_greeting(ctx.campaign, ctx.participant_name),
            tts=lambda text: self.tts_cache.speak(text, rate), stt=self._stt, emit=emit, sample_rate=rate,
            language=ctx.campaign.language, info_answers=ctx.campaign.info_answers,
            barge_in=self.settings.barge_in, no_speech_timeout_ms=self.settings.no_speech_timeout_ms,
            on_end=lambda sess: self._deliver(ctx, sess, "hung_up"))
        holder["s"] = s
        return s
