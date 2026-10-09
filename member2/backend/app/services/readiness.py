"""Is the backend ready to place real Exotel calls? Names and yes/no only; no secret value is ever returned.

`probe=True` additionally asks the public URL for /api/health, which proves the tunnel (ngrok, cloudflared ...) reaches this
backend: the one thing Exotel's callbacks depend on and nothing else can check from the inside.
"""
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..repositories import webhook_logs as log_repo

REGIONS = {"https://api.exotel.com": "Singapore cluster (api.exotel.com)",
           "https://api.in.exotel.com": "Mumbai cluster (api.in.exotel.com)"}

HINTS = {
    "EXOTEL_ACCOUNT_SID": "Exotel dashboard > API settings: account SID",
    "EXOTEL_API_KEY": "Exotel dashboard > API settings: API key",
    "EXOTEL_API_TOKEN": "Exotel dashboard > API settings: API token",
    "EXOTEL_CALLER_ID": "your ExoPhone number",
    "EXOTEL_FLOW_URL": "the call flow URL (Gather, then Passthru): http://my.exotel.com/<sid>/exoml/start_voice/<app_id>",
    "EXOTEL_WEBHOOK_TOKEN": "a long random string (16+ characters); the same token goes into the Passthru URL",
    "PUBLIC_BASE_URL": "the public https address of this backend, for example from `ngrok http 8000`",
    "CALL_PROVIDER=exotel": "set CALL_PROVIDER=exotel in .env and restart the backend",
    "backend reachable at PUBLIC_BASE_URL": "start the tunnel, set PUBLIC_BASE_URL to its https address, restart the backend",
}


def _check(name, ok, required=True, detail=None):
    c = {"name": name, "ok": bool(ok), "required": required}
    if detail:
        c["detail"] = detail
    return c


def _probe(base: str, client: httpx.Client | None) -> tuple[bool, str]:
    if not base:
        return False, "PUBLIC_BASE_URL is not set"
    try:
        r = (client or httpx.Client(timeout=6)).get(f"{base}/api/health", headers={"ngrok-skip-browser-warning": "1"})
    except httpx.HTTPError as exc:
        return False, f"could not reach it ({type(exc).__name__})"
    if r.status_code != 200:
        return False, f"it answered HTTP {r.status_code}"
    try:
        return (r.json().get("status") == "ok"), "the public URL reaches this backend" if r.json().get("status") == "ok" \
            else "it answered, but not with this backend's health response"
    except ValueError:
        return False, "it answered, but not with this backend's health response (a tunnel warning page?)"


def exotel_readiness(db: Session, s, *, probe: bool = False, client: httpx.Client | None = None) -> dict:
    required = [("EXOTEL_ACCOUNT_SID", s.exotel_account_sid), ("EXOTEL_API_KEY", s.exotel_api_key),
                ("EXOTEL_API_TOKEN", s.exotel_api_token), ("EXOTEL_CALLER_ID", s.exotel_caller_id),
                ("EXOTEL_FLOW_URL", s.exotel_flow_url), ("EXOTEL_WEBHOOK_TOKEN", s.exotel_webhook_token),
                ("PUBLIC_BASE_URL", s.public_base_url)]
    checks = [_check(n, v) for n, v in required]
    checks += [
        _check("EXOTEL_ALLOWED_NUMBERS", s.exotel_allowed_numbers.strip(), False,
               "recommended: restricts real calls to approved test numbers"),
        _check("EXOTEL_CLARIFY_FLOW_URL", s.exotel_clarify_flow_url, False, "needed for clarify-once calls on Exotel"),
        _check("CALL_PROVIDER=exotel", s.call_provider == "exotel"),
        _check("PUBLIC_BASE_URL uses https", s.public_base_url.startswith("https://"), False,
               "recommended: callbacks carry the shared token in the URL"),
        _check("EXOTEL_BASE_URL region", s.exotel_base_url in REGIONS, False,
               REGIONS.get(s.exotel_base_url, "not one of the documented clusters; a wrong region fails authentication")),
        _check("REAL_CALLS_PER_START cap", s.real_calls_per_start > 0, False,
               "optional: set a small cap (for example 3) for the first live test"),
    ]
    if probe:
        ok, detail = _probe(s.public_base_url, client)
        checks.append(_check("backend reachable at PUBLIC_BASE_URL", ok, True, detail))
    base = s.public_base_url
    missing = [c["name"] for c in checks if c["required"] and not c["ok"]]
    return {
        "ready": not missing,
        "checks": checks,
        "next_steps": [f"{n}: {HINTS.get(n, 'see docs/EXOTEL_INTEGRATION.md')}" for n in missing],
        "urls": {
            "status_callback": f"{base}/api/webhooks/exotel?token=<EXOTEL_WEBHOOK_TOKEN>" if base else None,
            "passthru_response": f"{base}/api/webhooks/exotel/response?token=<EXOTEL_WEBHOOK_TOKEN>" if base else None,
        },
        "limits": {"max_calls_per_minute": s.exotel_max_calls_per_minute, "real_calls_per_start": s.real_calls_per_start,
                   "allowed_numbers": len(s.allowed_numbers)},
        "webhooks_seen_last_24h": {**{"status": 0, "response": 0},
                                   **log_repo.counts_since(db, utcnow() - timedelta(hours=24), "exotel")},
        "note": "Real operation has never been verified from this codebase; run scripts/exotel_check.py first.",
    }
