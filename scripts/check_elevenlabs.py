"""Tiny ElevenLabs check: one short text-to-speech request in phone format (8 kHz PCM). Uses a few characters of quota.

    python scripts/check_elevenlabs.py

Reads ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID from .env. Never prints the key. Writes scripts/_tts_check.wav so you
can listen to the voice.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from member3.integrations.elevenlabs.client import ElevenLabsClient, ElevenLabsError
from member3.live.audio import pcm16_to_wav

load_dotenv()
key, voice = os.getenv("ELEVENLABS_API_KEY", ""), os.getenv("ELEVENLABS_VOICE_ID", "")
if not key or not voice:
    sys.exit("Missing ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID in .env")
try:
    pcm = ElevenLabsClient(key, voice_id=voice).speak_pcm("Hello, this is a test call.", 8000)
except ElevenLabsError as exc:
    sys.exit(f"FAILED: {exc}")
out = Path(__file__).parent / "_tts_check.wav"
out.write_bytes(pcm16_to_wav(pcm, 8000))
print(f"OK: {len(pcm)} bytes of 8 kHz PCM ({len(pcm) / 16000:.1f} s). Saved {out.name}; play it to hear the voice.")
