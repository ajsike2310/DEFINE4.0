"""Place ONE real test call through Exotel to a number on EXOTEL_ALLOWED_NUMBERS.

    python -m scripts.place_test_call +91XXXXXXXXXX

Exotel calls that number first, then runs your flow (the Voicebot applet -> your /live/exotel WebSocket).
Requires uvicorn + the tunnel to be running. Prints the call Sid and the final Exotel status; never prints credentials.
"""
import os
import sys
import time

from dotenv import load_dotenv

from member3.integrations.base import ProviderError
from member3.integrations.exotel.provider import ExotelProvider

load_dotenv()
if len(sys.argv) != 2:
    sys.exit("usage: python -m scripts.place_test_call +91XXXXXXXXXX")
to = sys.argv[1].strip()
allowed = [n.strip() for n in os.getenv("EXOTEL_ALLOWED_NUMBERS", "").split(",") if n.strip()]
if not allowed:
    sys.exit("Set EXOTEL_ALLOWED_NUMBERS in .env to your own test phone(s) first.")
try:
    p = ExotelProvider(account_sid=os.getenv("EXOTEL_ACCOUNT_SID", ""), api_key=os.getenv("EXOTEL_API_KEY", ""),
                       api_token=os.getenv("EXOTEL_API_TOKEN", ""), caller_id=os.getenv("EXOTEL_CALLER_ID", ""),
                       flow_url=os.getenv("EXOTEL_FLOW_URL", ""), stream_url=os.getenv("EXOTEL_STREAM_URL", ""),
                       base_url=os.getenv("EXOTEL_BASE_URL") or "https://api.exotel.com", allowed_numbers=allowed)
    res = p.initiate_call(attempt_id=0, attempt_number=1, to=to, language="en", message="")
except ProviderError as exc:
    sys.exit(f"FAILED: {exc}")
print(f"Call requested. Sid={res.provider_call_id}. Your phone should ring in a few seconds.")
for _ in range(12):
    time.sleep(5)
    try:
        c = p.get_call_status(res.provider_call_id)
    except ProviderError as exc:
        print("status check failed:", exc)
        break
    print(f"  status={c.get('Status')} duration={c.get('Duration')}")
    if c.get("Status") in ("completed", "failed", "busy", "no-answer"):
        break
