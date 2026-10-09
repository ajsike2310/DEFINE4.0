"""ElevenLabs text-to-speech and speech-to-text over plain HTTPS (httpx).

Endpoints used (from ElevenLabs' public API reference; not yet exercised against a live account from this
codebase until a key is supplied):
  POST /v1/text-to-speech/{voice_id}   JSON {text, model_id}           -> audio/mpeg
  POST /v1/speech-to-text              multipart {model_id, file, ...} -> JSON {text, language_code, ...}
The key is sent in the `xi-api-key` header and never logged or returned to the browser.
"""
import httpx

from ..base import ProviderError

BASE = "https://api.elevenlabs.io"


class ElevenLabsError(ProviderError):
    pass


class ElevenLabsClient:
    def __init__(self, api_key: str, *, voice_id: str, tts_model: str = "eleven_multilingual_v2",
                 stt_model: str = "scribe_v2", client: httpx.Client | None = None):
        if not api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not set")
        self._key, self.voice_id, self.tts_model, self.stt_model = api_key, voice_id, tts_model, stt_model
        self._http = client or httpx.Client(timeout=40)

    def _post(self, url: str, **kw) -> httpx.Response:
        """One retry for transient network failures and 502/503/504, so a hiccup does not drop a live call."""
        last: Exception | None = None
        for attempt in range(2):
            try:
                r = self._http.post(url, **kw)
            except httpx.TransportError as exc:          # connection reset, timeout, protocol error
                last = exc
                continue
            if r.status_code in (502, 503, 504) and attempt == 0:
                continue
            return r
        raise ElevenLabsError(f"ElevenLabs unreachable ({type(last).__name__})")

    def _fail(self, what: str, r: httpx.Response) -> ElevenLabsError:
        # Status code only: response bodies can echo request details.
        hint = {401: "key rejected", 403: "key lacks permission", 422: "request rejected", 429: "rate or quota limit"}
        return ElevenLabsError(f"ElevenLabs {what} failed (HTTP {r.status_code}: {hint.get(r.status_code, 'error')})")

    def speak(self, text: str, output_format: str | None = None) -> bytes:
        try:
            r = self._post(f"{BASE}/v1/text-to-speech/{self.voice_id}", headers={"xi-api-key": self._key},
                           params={"output_format": output_format} if output_format else None,
                           json={"text": text, "model_id": self.tts_model})
        except httpx.HTTPError as exc:
            raise ElevenLabsError(f"ElevenLabs unreachable ({type(exc).__name__})")
        if r.status_code != 200:
            raise self._fail("text-to-speech", r)
        return r.content

    def speak_pcm(self, text: str, sample_rate: int = 8000) -> bytes:
        """Raw 16-bit mono little-endian PCM at `sample_rate`, the format Exotel's Voicebot stream expects.
        `pcm_<rate>` is the documented ElevenLabs output_format naming; confirm your plan accepts it."""
        if sample_rate not in (8000, 16000, 24000):
            raise ElevenLabsError(f"unsupported sample rate {sample_rate}")
        return self.speak(text, output_format=f"pcm_{sample_rate}")

    def transcribe(self, audio: bytes, filename: str = "reply.webm", content_type: str = "audio/webm",
                   language_hint: str | None = None) -> str:
        data = {"model_id": self.stt_model}
        if language_hint:
            data["language_code"] = language_hint     # ISO 639-1/3 hint; omitted when unknown
        try:
            r = self._post(f"{BASE}/v1/speech-to-text", headers={"xi-api-key": self._key}, data=data,
                           files={"file": (filename, audio, content_type)})
        except httpx.HTTPError as exc:
            raise ElevenLabsError(f"ElevenLabs unreachable ({type(exc).__name__})")
        if r.status_code != 200:
            raise self._fail("speech-to-text", r)
        return (r.json().get("text") or "").strip()
