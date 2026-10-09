from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'app.db').as_posix()}"
    call_provider: str = "demo"            # demo | exotel
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_call_attempts: int = 3
    retry_backoff_minutes: int = 30
    # Exotel (names only in .env.example; values never logged)
    exotel_account_sid: str = ""
    exotel_api_key: str = ""
    exotel_api_token: str = ""
    exotel_base_url: str = "https://api.exotel.com"
    exotel_caller_id: str = ""
    exotel_flow_url: str = ""
    exotel_clarify_flow_url: str = ""     # optional second flow (one yes/no question) for clarification calls
    exotel_webhook_token: str = ""
    exotel_allowed_numbers: str = ""      # comma-separated E.164 test numbers; empty = no restriction
    public_base_url: str = ""
    # ElevenLabs (voice + speech-to-text for the browser demo call). Key lives in .env only.
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    elevenlabs_stt_model: str = "scribe_v1"
    data_location_note: str = "Local SQLite file on the machine running the backend."


@lru_cache
def get_settings() -> Settings:
    return Settings()
