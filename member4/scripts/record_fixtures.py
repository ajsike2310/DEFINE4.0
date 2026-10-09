"""Record REAL API responses from a running backend (seeded + simulated) as JSON fixtures for the frontend
render tests. Usage: python member4/scripts/record_fixtures.py [base_url]  (run against a THROWAWAY database)."""
import json
import sys
from pathlib import Path

import httpx

base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8011") + "/api"
out = Path(__file__).resolve().parents[2] / "member1" / "frontend" / "tests" / "fixtures"
out.mkdir(parents=True, exist_ok=True)

with httpx.Client(timeout=60) as c:
    def get(path, **params):
        r = c.get(f"{base}{path}", params=params)
        r.raise_for_status()
        return r.json()

    seeded = c.post(f"{base}/demo/seed-all", params={"run": "true"}).json()
    events = get("/events")
    ev = events[0]
    camp = next(x for x in seeded["campaigns"] if x["event_id"] == ev["id"])
    c.post(f"{base}/campaigns/{camp['id']}/clarify")           # exercise clarify-once so fixtures include it
    csv_text = "\n".join(["name,phone,email,interest,language", "Asha,+919876543210,asha@example.invalid,AI,en",
                          "Bad,12345,,,"]) + "\n"
    c.post(f"{base}/events/{ev['id']}/leads/import", data={"consent_confirmed": "true"},
           files={"file": ("recorded-leads.csv", csv_text.encode(), "text/csv")})
    unclear = next(r for r in get(f"/campaigns/{camp['id']}/recipients") if r["outcome"] == "unclear")
    files = {
        "settings": get("/settings"), "exotel": get("/settings/exotel-readiness"), "events": events,
        "campaigns": get("/campaigns", event_id=ev["id"]), "campaign": get(f"/campaigns/{camp['id']}"),
        "recipients": get(f"/campaigns/{camp['id']}/recipients"), "attempts": get(f"/campaigns/{camp['id']}/attempts"),
        "intents": get(f"/campaigns/{camp['id']}/intents"), "followups": get("/followups", campaign_id=camp["id"]),
        "queue": get("/followups/queue", event_id=ev["id"]), "participants": get("/recipients", event_id=ev["id"]),
        "history": get(f"/recipients/{unclear['id']}/history"),
        "analytics": get("/analytics", event_id=ev["id"]),
        "analytics_campaign": get("/analytics", campaign_id=camp["id"]),
        "overview": get("/campaigns/overview", event_id=ev["id"]),
        "leads": get(f"/events/{ev['id']}/leads"), "lead_summary": get(f"/events/{ev['id']}/leads/summary"),
        "quality": get("/quality", event_id=ev["id"]), "voice": get("/voice/status"),
        "meta": {"event_id": ev["id"], "campaign_id": camp["id"], "history_recipient_id": unclear["id"],
                 "event_name": ev["name"], "campaign_name": camp["name"]},
    }
    for name, data in files.items():
        (out / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print("recorded", len(files), "fixtures to", out)
