"""Exotel readiness check. Never prints secret values.

  .venv\\Scripts\\python.exe scripts\\exotel_check.py
      -> shows which settings are present/missing and the URLs to paste into your Exotel flow.

  .venv\\Scripts\\python.exe scripts\\exotel_check.py --call +91XXXXXXXXXX --yes
      -> places ONE real test call through the Exotel adapter, then polls Call Details.
         Refuses unless the number is listed in EXOTEL_ALLOWED_NUMBERS and you pass --yes.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from member2.backend.app.core.config import get_settings  # noqa: E402
from member3.integrations.base import ProviderError  # noqa: E402
from member3.integrations.factory import build_provider  # noqa: E402

REQUIRED = [("EXOTEL_ACCOUNT_SID", "exotel_account_sid"), ("EXOTEL_API_KEY", "exotel_api_key"),
            ("EXOTEL_API_TOKEN", "exotel_api_token"), ("EXOTEL_CALLER_ID", "exotel_caller_id"),
            ("EXOTEL_FLOW_URL", "exotel_flow_url"), ("EXOTEL_WEBHOOK_TOKEN", "exotel_webhook_token"),
            ("PUBLIC_BASE_URL", "public_base_url")]
OPTIONAL = [("EXOTEL_ALLOWED_NUMBERS", "exotel_allowed_numbers"), ("EXOTEL_CLARIFY_FLOW_URL", "exotel_clarify_flow_url")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--call", metavar="E164", help="place one real test call to this approved number")
    ap.add_argument("--yes", action="store_true", help="confirm that a REAL call may be placed")
    args = ap.parse_args()
    s = get_settings()

    print(f"CALL_PROVIDER = {s.call_provider}  (campaigns use Exotel only when this is 'exotel')")
    missing = []
    for env, attr in REQUIRED:
        ok = bool(getattr(s, attr))
        print(f"  [{'x' if ok else ' '}] {env}")
        if not ok:
            missing.append(env)
    for env, attr in OPTIONAL:
        print(f"  [{'x' if getattr(s, attr) else '-'}] {env} (optional/recommended)")
    base = s.public_base_url.rstrip("/") or "<PUBLIC_BASE_URL>"
    print("\nIn the Exotel dashboard, build the call flow as:  Greeting/Gather (keypad) -> Passthru applet")
    print(f"  Passthru URL (GET):      {base}/api/webhooks/exotel/response?token=<EXOTEL_WEBHOOK_TOKEN>")
    print(f"  StatusCallback (auto):   {base}/api/webhooks/exotel?token=<EXOTEL_WEBHOOK_TOKEN>  (sent by Cadence per call)")
    print("  Keypad meaning: 1 attend, 2 decline, 3 callback, 4 more info, 9 stop calls.")
    print("  Clarify flow (optional): Gather 1 = yes / 2 = no -> same Passthru URL.")

    if not args.call:
        print("\nREADY for a test call." if not missing else f"\nNOT ready; missing: {', '.join(missing)}")
        return 1 if missing else 0

    if missing:
        print(f"\nRefusing: missing {', '.join(missing)}")
        return 1
    allowed = [n.strip() for n in s.exotel_allowed_numbers.split(",") if n.strip()]
    if not allowed or args.call not in allowed:
        print("\nRefusing: set EXOTEL_ALLOWED_NUMBERS to your approved test number(s) and pass one of them.")
        return 1
    if not args.yes:
        print("\nRefusing: add --yes to confirm a REAL call to an authorised test number.")
        return 1
    try:
        p = build_provider(s, "exotel")
        res = p.initiate_call(attempt_id=0, attempt_number=1, to=args.call, language="en", message="setup check")
    except ProviderError as exc:
        print(f"\nExotel call failed: {exc}")
        return 1
    print(f"\nCall placed. Exotel Sid = {res.provider_call_id}")
    for _ in range(6):
        time.sleep(5)
        try:
            call = p.get_call_status(res.provider_call_id)
        except ProviderError as exc:
            print(f"  status check failed: {exc}")
            break
        print(f"  Status={call.get('Status')} Duration={call.get('Duration')} AnsweredBy={call.get('AnsweredBy')}")
        if call.get("Status") in ("completed", "failed", "busy", "no-answer"):
            break
    print("\nNote: attempt id 0 is not in the database, so webhooks for this smoke-test call return 404 (expected).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
