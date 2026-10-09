"""Dress rehearsal of the whole Exotel path WITHOUT an Exotel account.

    python -m member2.backend.scripts.exotel_rehearsal

Starts (1) a stand-in Exotel server that answers like Exotel's documented call API, and (2) a real backend process on a scratch
database, configured with the REAL ExotelProvider pointed at the stand-in. Then it drives the flow over HTTP the way Exotel and
the browser would: readiness, start a campaign, receive the Passthru and StatusCallback callbacks, reconcile a call whose result
"never arrived", read the webhook log. It touches none of your data and no real number.

What it proves: our provider and our backend agree with each other and with Exotel's DOCUMENTED shapes. What it cannot prove:
that Exotel really behaves as documented. That is the first live call.
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import httpx

ROOT = Path(__file__).resolve().parents[3]
SID = "rehearsal-sid"
ALLOWED = ["+919876543210", "+919876543211"]
OUTSIDE = "+919876543219"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeExotel(BaseHTTPRequestHandler):
    """POST /v1/Accounts/{sid}/Calls/connect  and  GET /v1/Accounts/{sid}/Calls/{CallSid}.json, as documented."""
    placed: list[dict] = []
    status_of: dict[str, str] = {}

    def log_message(self, *a):
        pass

    def _json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()).items()}
        if not self.path.endswith("/Calls/connect") or not self.headers.get("Authorization", "").startswith("Basic "):
            return self._json(401, {})
        sid = f"CA{len(FakeExotel.placed) + 1:04d}"
        FakeExotel.placed.append({"sid": sid, **form})
        FakeExotel.status_of[sid] = "in-progress"
        self._json(200, {"Call": {"Sid": sid, "Status": "queued"}})

    def do_GET(self):
        sid = self.path.rsplit("/", 1)[-1].removesuffix(".json")
        self._json(200, {"Call": {"Sid": sid, "Status": FakeExotel.status_of.get(sid, "in-progress")}})


def main() -> int:
    results: list[tuple[bool, str]] = []

    def check(ok: bool, what: str, detail: str = "") -> None:
        results.append((ok, what))
        print(("  PASS  " if ok else "  FAIL  ") + what + (f"   [{detail}]" if detail and not ok else ""))

    exo_port, api_port = free_port(), free_port()
    fake = HTTPServer(("127.0.0.1", exo_port), FakeExotel)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    token = secrets.token_urlsafe(24)
    tmp = Path(tempfile.mkdtemp(prefix="cadence-rehearsal-"))
    env = {**os.environ, "PYTHONPATH": str(ROOT), "DATABASE_URL": f"sqlite:///{(tmp / 'rehearsal.db').as_posix()}",
           "CALL_PROVIDER": "exotel", "EXOTEL_ACCOUNT_SID": SID, "EXOTEL_API_KEY": "key", "EXOTEL_API_TOKEN": "secret",
           "EXOTEL_BASE_URL": f"http://127.0.0.1:{exo_port}", "EXOTEL_CALLER_ID": "0800000000",
           "EXOTEL_FLOW_URL": f"http://my.exotel.com/{SID}/exoml/start_voice/1", "EXOTEL_WEBHOOK_TOKEN": token,
           "PUBLIC_BASE_URL": f"http://127.0.0.1:{api_port}", "EXOTEL_ALLOWED_NUMBERS": ",".join(ALLOWED),
           "REAL_CALLS_PER_START": "2", "EXOTEL_MAX_CALLS_PER_MINUTE": "600", "ELEVENLABS_API_KEY": "",
           "SCHEDULER_ENABLED": "false", "WEBHOOK_LOG_DAYS": "14", "STALE_CALL_MINUTES": "20"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "member2.backend.app.main:app", "--port", str(api_port)],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{api_port}/api"
    try:
        with httpx.Client(timeout=20) as c:
            for _ in range(60):
                try:
                    if c.get(f"{base}/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.5)
            else:
                print("backend did not start")
                return 2
            print(f"\nRehearsal: backend on :{api_port}, stand-in Exotel on :{exo_port}, scratch database in {tmp}\n")

            print("1. readiness")
            r = c.get(f"{base}/settings/exotel-readiness", params={"probe": "true"}).json()
            check(r["ready"], "readiness is green, including the probe of PUBLIC_BASE_URL", json.dumps(r["next_steps"]))
            check(token not in json.dumps(r), "the webhook token is never shown")

            print("2. a real (non-sample) campaign with three participants, one outside the allow-list")
            ev = c.post(f"{base}/events", json={"name": "Rehearsal Event"}).json()
            camp = c.post(f"{base}/campaigns", json={"event_id": ev["id"], "name": "Rehearsal campaign",
                                                     "messages": {"en": "Press 1 to confirm"}, "languages": ["en"]}).json()
            check(camp["is_demo"] is False, "the campaign is real (not simulated)")
            for phone in ALLOWED + [OUTSIDE]:
                c.post(f"{base}/campaigns/{camp['id']}/recipients", json={"name": "Person " + phone[-2:], "phone": phone,
                                                                         "consent_status": "granted"})
            start = c.post(f"{base}/campaigns/{camp['id']}/start").json()
            check(start["dispatched"] == 2 and len(FakeExotel.placed) == 2, "two calls placed with Exotel", str(start))
            check(len(start["skipped"]) == 1 and start["skipped"][0]["reason"].startswith("phone not in EXOTEL_ALLOWED_NUMBERS"),
                  "the third number was skipped by the allow-list, not dialled", str(start["skipped"]))
            first = FakeExotel.placed[0]
            check(first["From"] == ALLOWED[0] and first["CallerId"] == "0800000000" and first["Url"].endswith("/start_voice/1")
                  and first["CallType"] == "trans", "the call request has Exotel's documented fields")
            check(f"token={token}" in first["StatusCallback"] and first["StatusCallbackEvents[0]"] == "terminal",
                  "StatusCallback carries our token and asks for terminal events")
            attempts = c.get(f"{base}/campaigns/{camp['id']}/attempts").json()
            check(all(a["provider"] == "exotel" and a["is_simulated"] is False for a in attempts), "attempts are labelled Real")
            check(first["CustomField"] == str(attempts[0]["id"]), "our attempt id travels as CustomField")

            print("3. Exotel calls us back")
            sid1, sid2 = attempts[0]["provider_call_id"], attempts[1]["provider_call_id"]
            ok = c.get(f"{base}/webhooks/exotel/response", params={"token": token, "CallSid": sid1, "digits": '"1"',
                                                                  "CustomField": str(attempts[0]["id"])})
            check(ok.status_code == 200, "Passthru with digits \"1\" accepted (quotes stripped)", ok.text)
            done = c.post(f"{base}/webhooks/exotel", params={"token": token}, data={"CallSid": sid1, "Status": "completed"})
            check(done.status_code == 200, "StatusCallback (form post) accepted", done.text)
            by_custom = c.get(f"{base}/webhooks/exotel/response", params={"token": token, "digits": '"9"',
                                                                         "CustomField": str(attempts[1]["id"])})
            check(by_custom.status_code == 200, "Passthru found its call by CustomField when CallSid was absent", by_custom.text)
            recs = {r["phone"]: r for r in c.get(f"{base}/campaigns/{camp['id']}/recipients").json()}
            check(recs[ALLOWED[0]]["outcome"] == "confirmed", "pressing 1 confirmed the first participant")
            check(recs[ALLOWED[1]]["outcome"] == "opted_out" and recs[ALLOWED[1]]["opted_out"], "pressing 9 opted the second out")
            dup = c.post(f"{base}/webhooks/exotel", params={"token": token}, data={"CallSid": sid1, "Status": "completed"})
            check(dup.json()["result"] == "duplicate", "a repeated callback is recognised and ignored")
            bad = c.post(f"{base}/webhooks/exotel", params={"token": "wrong"}, data={"CallSid": sid1, "Status": "completed"})
            check(bad.status_code == 401, "a callback with the wrong token is refused")

            print("4. a call whose result never arrived")
            second_status = next(a["status"] for a in c.get(f"{base}/campaigns/{camp['id']}/attempts").json() if a["provider_call_id"] == sid2)
            check(second_status == "answered", "the second call is stuck 'answered' (no StatusCallback came)", second_status)
            FakeExotel.status_of[sid2] = "completed"
            rec = c.post(f"{base}/campaigns/{camp['id']}/reconcile", params={"minutes": 0}).json()
            check(len(rec["updated"]) == 1 and rec["updated"][0]["provider_status"] == "completed",
                  "reconcile asked Exotel (Call Details) and closed it", json.dumps(rec))

            print("5. the log of what Exotel sent")
            log = c.get(f"{base}/webhooks/log", params={"provider": "exotel"}).json()
            check(len(log) == 4, "the four authenticated callbacks were kept (the wrong-token one was not)", str(len(log)))
            check(token not in json.dumps(log) and "token" not in {k for row in log for k in row["payload"]},
                  "the token is not in the log")
            check(any(row["result"] == "duplicate" for row in log), "the duplicate is visible in the log")
            check(c.get(f"{base}/health/database").json()["check"]["ok"], "database integrity and consistency are clean")
    finally:
        server.terminate()
        fake.shutdown()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    failed = [w for ok, w in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed" + ("" if not failed else "; FAILED: " + "; ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
