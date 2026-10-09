"""Replaceable speech-to-text interface. No real transcriber is wired in yet."""
from typing import Protocol


class TranscriptionUnavailable(Exception):
    pass


class Transcriber(Protocol):
    def transcribe(self, audio_ref: str, language_hint: str | None = None) -> str: ...


class NullTranscriber:
    """Used when no STT service has been verified/configured."""

    def transcribe(self, audio_ref: str, language_hint: str | None = None) -> str:
        raise TranscriptionUnavailable("No transcription service configured")
