"""Read-only Exotel credential check + list the ExoPhones you OWN. Places no call, buys nothing.

    python scripts/check_exotel.py

Reads .env (EXOTEL_ACCOUNT_SID / EXOTEL_API_KEY / EXOTEL_API_TOKEN / EXOTEL_BASE_URL). Never prints credentials.
Endpoints are from Exotel's docs (v2_beta list); a 404 just means that path isn't enabled for your cluster.
"""
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
sid, key, token = (os.getenv(k, "") for k in ("EXOTEL_ACCOUNT_SID", "EXOTEL_API_KEY", "EXOTEL_API_TOKEN"))
base = (os.getenv("EXOTEL_BASE_URL") or "https://api.exotel.com").rstrip("/")
missing = [n for n, v in (("EXOTEL_ACCOUNT_SID", sid), ("EXOTEL_API_KEY", key), ("EXOTEL_API_TOKEN", token)) if not v]
if missing:
    sys.exit("Missing in .env: " + ", ".join(missing))
if not base.startswith("http"):
    base = "https://" + base

PATHS = [f"/v2_beta/Accounts/{sid}/IncomingPhoneNumbers", f"/v2/accounts/{sid}/incoming-phone-numbers"]
for path in PATHS:
    try:
        r = httpx.get(base + path, auth=(key, token), timeout=20)
    except httpx.HTTPError as exc:
        sys.exit(f"Could not reach {base}: {type(exc).__name__}")
    print(f"GET {path.replace(sid, '<sid>')} -> HTTP {r.status_code}")
    if r.status_code == 401:
        sys.exit("Credentials rejected (check key, token, SID, and that EXOTEL_BASE_URL matches your region: "
                 "api.exotel.com = Singapore, api.in.exotel.com = Mumbai).")
    if r.status_code != 200:
        continue
    data = r.json()
    items = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
    if not items:
        print("Credentials work, but the response lists no numbers:", list(data)[:6] if isinstance(data, dict) else data)
    for it in items:
        num = it.get("phone_number") or it.get("PhoneNumber") or it.get("friendly_name") or "?"
        print(f"  ExoPhone: {num}   type={it.get('number_type') or it.get('Type') or '-'}   "
              f"voice={((it.get('capabilities') or {}).get('voice', '-'))}")
    sys.exit(0)
sys.exit("Neither list endpoint answered 200. Check the ExoPhones page in the dashboard instead.")
