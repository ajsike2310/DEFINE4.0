import os
from dataclasses import dataclass


def _flag(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class LiveSettings:
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_tts_model: str = "eleven_multilingual_v2"     # ElevenLabs Multilingual v2
    elevenlabs_stt_model: str = "scribe_v2"                   # ElevenLabs Scribe v2
    webhook_token: str = ""            # secret in the stream URL path: wss://host/live/exotel/<token>
    barge_in: bool = False             # let the caller interrupt the agent (needs a clean line; off by default)
    no_speech_timeout_ms: int = 7000
    log_transcript: bool = False       # DEV ONLY: logs what the caller said (personal data)
    result_url: str = ""               # backend endpoint that receives each CallResult
    result_token: str = ""
    dead_letter_path: str = "logs/unsent_results.jsonl"
    register_wait_s: float = 3.0
    default_sample_rate: int = 8000

    @classmethod
    def from_env(cls, env=os.environ) -> "LiveSettings":
        return cls(
            elevenlabs_api_key=env.get("ELEVENLABS_API_KEY", ""), elevenlabs_voice_id=env.get("ELEVENLABS_VOICE_ID", ""),
            elevenlabs_tts_model=env.get("ELEVENLABS_TTS_MODEL") or "eleven_multilingual_v2",
            elevenlabs_stt_model=env.get("ELEVENLABS_STT_MODEL") or "scribe_v2",
            webhook_token=env.get("EXOTEL_WEBHOOK_TOKEN", ""), barge_in=_flag(env.get("LIVE_BARGE_IN")),
            no_speech_timeout_ms=int(env.get("LIVE_NO_SPEECH_TIMEOUT_MS") or 7000),
            log_transcript=_flag(env.get("LIVE_LOG_TRANSCRIPT")),
            result_url=env.get("BACKEND_RESULT_URL", ""), result_token=env.get("BACKEND_RESULT_TOKEN", ""),
            dead_letter_path=env.get("LIVE_DEAD_LETTER_PATH", "logs/unsent_results.jsonl"))
