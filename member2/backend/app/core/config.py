import re
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{(ROOT / 'data' / 'app.db').as_posix()}"
    call_provider: str = "demo"            # demo | exotel
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_call_attempts: int = 3
    log_level: str = "INFO"
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
    # Real-call safety and pacing (apply to non-simulated providers only).
    exotel_max_calls_per_minute: int = 200   # Exotel documents 200 calls/minute for its call API
    real_calls_per_start: int = 0            # >0: at most this many calls per Start press (hold the rest back); 0 = no cap
    stale_call_minutes: int = 20             # a real call with no result after this long is checked with the provider; 0 = off
    webhook_log_days: int = 14               # keep received provider callbacks this long (masked); 0 = do not log
    # ElevenLabs (voice + speech-to-text for the browser demo call). Key lives in .env only.
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    elevenlabs_stt_model: str = "scribe_v1"
    # Background scheduler (off by default): starts scheduled campaigns and runs due retries.
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 30
    # Public sign-up abuse limit: max registration-form leads per client address per window.
    signup_limit: int = 30
    signup_window_seconds: int = 600
    data_location_note: str = "Local SQLite file on the machine running the backend."

    @field_validator("call_provider")
    @classmethod
    def _provider(cls, v: str) -> str:
        if v not in ("demo", "exotel"):
            raise ValueError("CALL_PROVIDER must be 'demo' or 'exotel'")
        return v

    @field_validator("exotel_base_url")
    @classmethod
    def _exotel_base(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        local = re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$", v)      # a stand-in server for local rehearsals only
        if not (v.startswith("https://") or local):
            raise ValueError("EXOTEL_BASE_URL must start with https:// (api.exotel.com or api.in.exotel.com)")
        return v

    @field_validator("public_base_url")
    @classmethod
    def _public_base(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if v and not re.match(r"^https?://[^\s/]+", v):
            raise ValueError("PUBLIC_BASE_URL must look like https://your-host (no path)")
        return v

    @field_validator("exotel_webhook_token")
    @classmethod
    def _token(cls, v: str) -> str:
        v = v.strip()
        if v and len(v) < 16:
            raise ValueError("EXOTEL_WEBHOOK_TOKEN must be at least 16 characters (use a long random string)")
        return v

    @field_validator("exotel_allowed_numbers")
    @classmethod
    def _allowed(cls, v: str) -> str:
        numbers = [n.strip() for n in v.split(",") if n.strip()]
        bad = [n for n in numbers if not re.match(r"^\+[1-9]\d{7,14}$", n)]
        if bad:
            raise ValueError("EXOTEL_ALLOWED_NUMBERS must be comma-separated E.164 numbers like +919876543210 "
                             f"({len(bad)} invalid)")
        return ",".join(numbers)

    @field_validator("exotel_max_calls_per_minute")
    @classmethod
    def _rate(cls, v: int) -> int:
        if not 1 <= v <= 600:
            raise ValueError("EXOTEL_MAX_CALLS_PER_MINUTE must be between 1 and 600")
        return v

    @field_validator("real_calls_per_start")
    @classmethod
    def _cap(cls, v: int) -> int:
        if not 0 <= v <= 10000:
            raise ValueError("REAL_CALLS_PER_START must be between 0 and 10000")
        return v

    @field_validator("stale_call_minutes")
    @classmethod
    def _stale(cls, v: int) -> int:
        if not 0 <= v <= 1440:
            raise ValueError("STALE_CALL_MINUTES must be between 0 and 1440")
        return v

    @field_validator("webhook_log_days")
    @classmethod
    def _log_days(cls, v: int) -> int:
        if not 0 <= v <= 365:
            raise ValueError("WEBHOOK_LOG_DAYS must be between 0 and 365")
        return v

    @property
    def allowed_numbers(self) -> list[str]:
        return [n for n in self.exotel_allowed_numbers.split(",") if n]

    @field_validator("log_level")
    @classmethod
    def _level(cls, v: str) -> str:
        if v.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING or ERROR")
        return v.upper()

    @field_validator("max_call_attempts")
    @classmethod
    def _attempts(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("MAX_CALL_ATTEMPTS must be between 1 and 5")
        return v

    @field_validator("retry_backoff_minutes", "signup_window_seconds")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must not be negative")
        return v

    @field_validator("scheduler_interval_seconds")
    @classmethod
    def _interval(cls, v: int) -> int:
        if v < 5:
            raise ValueError("SCHEDULER_INTERVAL_SECONDS must be at least 5")
        return v

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
