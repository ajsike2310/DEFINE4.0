"""Drive the SIMULATED sample-event workflow against a running backend and print the results.
Usage: .venv\\Scripts\\python.exe member4/scripts/demo_e2e.py [http://127.0.0.1:8000]
Creates a new [SAMPLE] campaign in the sample DEFINE 4.0 event; remove everything with DELETE /api/demo."""
import sys

import httpx

base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000") + "/api"
with httpx.Client(timeout=30) as c:
    camp = c.post(f"{base}/demo/seed").json()
    ev = c.get(f"{base}/events/{camp['event_id']}").json()
    print(f"event: {ev['name']} (approved info keys: {sorted(ev['approved_info'])})")
    print("campaign:", camp["id"], camp["name"])
    print("start:", c.post(f"{base}/campaigns/{camp['id']}/start").json())
    for _ in range(3):
        res = c.post(f"{base}/campaigns/{camp['id']}/retry-due", params={"force": True}).json()
        print("retries:", res)
        if "error" in res:      # campaign already completed
            break
    def headcount(label):
        h = c.get(f"{base}/analytics", params={"event_id": ev["id"]}).json()["headcount"]
        print(f"headcount {label}: {h['floor']}-{h['ceiling']} of {h['participants']}, certainty {h['certainty']:.0%}")
    headcount("before clarification")
    print("clarify-once:", c.post(f"{base}/campaigns/{camp['id']}/clarify").json())
    print("clarify again (must do nothing):", c.post(f"{base}/campaigns/{camp['id']}/clarify").json()["dispatched"])
    headcount("after clarification ")
    print("participants:")
    for r in c.get(f"{base}/campaigns/{camp['id']}/recipients").json():
        print(f"  {r['external_ref']:<11} {r['name']:<22} {r['outcome']}")
    print("follow-up queue (priority order):")
    for i in c.get(f"{base}/followups/queue", params={"event_id": ev["id"]}).json():
        print(f"  P{i['priority']} {i['participant_name']:<22} {i['action_type']:<16} {i['note'][:70]}")
    a = c.get(f"{base}/analytics", params={"event_id": ev["id"]}).json()
    print("outcomes:", {k: v for k, v in a["outcomes"].items() if v})
    print("rates:", a["rates"])
    assert a["totals"]["real_calls"] == 0, "demo run must not place real calls"
    print("OK (all calls simulated)")
