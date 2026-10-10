"""Dashboard settings, read from the environment (.env). Field names match what `build_provider` expects."""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    call_provider: str = "demo"                 # demo (simulated, no real calls) | exotel
    db_path: str = "data/dashboard.db"
    dashboard_token: str = ""                   # when set, every /api call needs it (Authorization: Bearer ...)
    call_window: str = "09:00-21:00"            # local time; real calls outside it are refused. "" disables
    call_timezone_offset_min: int = 330         # IST
    dial_interval_s: float = 1.5                # pause between dials so a big list does not flood the account
    max_attempts: int = 3
    scheduler_interval_s: float = 20            # how often due automatic retries are looked for
    enforce_allowlist: bool = False             # True: only EXOTEL_ALLOWED_NUMBERS may be dialled (test mode)
    public_base_url: str = ""
    exotel_account_sid: str = ""
    exotel_api_key: str = ""
    exotel_api_token: str = ""
    exotel_caller_id: str = ""
    exotel_flow_url: str = ""
    exotel_stream_url: str = ""
    exotel_clarify_flow_url: str = ""
    exotel_base_url: str = "https://api.exotel.com"
    exotel_webhook_token: str = ""
    exotel_allowed_numbers: str = ""

    @classmethod
    def from_env(cls, env=os.environ) -> "Settings":
        def g(k, d=""):
            """A blank `KEY=   # comment` line is read by some .env parsers as the value '# comment'. Treat it as empty."""
            v = env.get(k)
            if v is None:
                return d
            return "" if v.strip().startswith("#") else v.strip()
        provider = (g("CALL_PROVIDER") or "demo").strip().lower()
        return cls(
            call_provider=provider, db_path=g("DASHBOARD_DB") or "data/dashboard.db",
            dashboard_token=g("DASHBOARD_TOKEN"), call_window=g("CALL_WINDOW", "09:00-21:00"),
            dial_interval_s=float(g("DIAL_INTERVAL_S") or (1.5 if provider == "exotel" else 0.15)),
            max_attempts=int(g("MAX_ATTEMPTS") or 3), scheduler_interval_s=float(g("SCHEDULER_INTERVAL_S") or 20),
            enforce_allowlist=g("DASHBOARD_ENFORCE_ALLOWLIST").strip().lower() in ("1", "true", "yes", "on"), public_base_url=g("PUBLIC_BASE_URL") if g("PUBLIC_BASE_URL").lower().startswith(("http://", "https://")) else "",
            exotel_account_sid=g("EXOTEL_ACCOUNT_SID"), exotel_api_key=g("EXOTEL_API_KEY"),
            exotel_api_token=g("EXOTEL_API_TOKEN"), exotel_caller_id=g("EXOTEL_CALLER_ID"),
            exotel_flow_url=g("EXOTEL_FLOW_URL"), exotel_stream_url=g("EXOTEL_STREAM_URL"),
            exotel_clarify_flow_url=g("EXOTEL_CLARIFY_FLOW_URL"),
            exotel_base_url=g("EXOTEL_BASE_URL") or "https://api.exotel.com",
            exotel_webhook_token=g("EXOTEL_WEBHOOK_TOKEN"), exotel_allowed_numbers=g("EXOTEL_ALLOWED_NUMBERS"))
