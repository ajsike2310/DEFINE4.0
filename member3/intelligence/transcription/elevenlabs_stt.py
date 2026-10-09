"""ElevenLabs speech-to-text behind the replaceable `Transcriber` interface.

`audio_ref` is resolved by a loader (default: a local file path) so the pipeline stays storage-agnostic.
Live calls skip the loader and use `transcribe_bytes` directly with in-memory WAV audio.
"""
import mimetypes
from collections.abc import Callable
from pathlib import Path

from ...integrations.base import ProviderError
from ...integrations.elevenlabs.client import ElevenLabsClient
from .base import TranscriptionUnavailable

Loader = Callable[[str], tuple[bytes, str, str]]   # audio_ref -> (bytes, filename, content_type)


def _load_local_file(audio_ref: str) -> tuple[bytes, str, str]:
    path = Path(audio_ref)
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return path.read_bytes(), path.name, ctype


class ElevenLabsTranscriber:
    def __init__(self, client: ElevenLabsClient, loader: Loader = _load_local_file):
        self._client, self._loader = client, loader

    def transcribe_bytes(self, audio: bytes, filename: str = "reply.wav", content_type: str = "audio/wav",
                         language_hint: str | None = None) -> str:
        try:
            return self._client.transcribe(audio, filename, content_type, language_hint)
        except ProviderError as exc:
            raise TranscriptionUnavailable(str(exc)) from exc

    def transcribe(self, audio_ref: str, language_hint: str | None = None) -> str:
        try:
            audio, name, ctype = self._loader(audio_ref)
        except OSError as exc:
            raise TranscriptionUnavailable(f"audio not readable ({type(exc).__name__})") from exc
        return self.transcribe_bytes(audio, name, ctype, language_hint)
