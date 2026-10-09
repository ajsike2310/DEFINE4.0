"""The three labelled sample events and the one-click simulation (all simulated)."""


def by_ref(client, cid):
    return {r["external_ref"]: r["outcome"] for r in client.get(f"/api/campaigns/{cid}/recipients").json()}


def notes(client, cid):
    return [(f["action_type"], f["note"]) for f in client.get("/api/followups", params={"campaign_id": cid}).json()]


def test_seed_all_creates_three_labelled_events_as_drafts(client):
    r = client.post("/api/demo/seed-all")
    assert r.status_code == 201
    body = r.json()
    assert body["ran"] is False and len(body["campaigns"]) == 3
    assert all(c["status"] == "draft" and c["is_demo"] for c in body["campaigns"])
    evs = client.get("/api/events").json()
    assert len(evs) == 3 and all(e["is_demo"] and e["name"].startswith("[SAMPLE]") for e in evs)
    by = {e["name"]: e for e in evs}
    assert by["[SAMPLE] Hack Night Workshop (fictional)"]["approved_info"] == {}
    assert set(by["[SAMPLE] Campus Code Sprint (fictional)"]["approved_info"]) == {"venue", "schedule"}
    # nothing has been called yet
    assert client.get("/api/analytics").json()["totals"]["calls_attempted"] == 0


def test_seed_all_run_executes_the_simulation_end_to_end(client):
    body = client.post("/api/demo/seed-all", params={"run": "true"}).json()
    assert body["ran"] is True
    camps = {c["name"].split("] ")[1].split(" #")[0]: c for c in client.get("/api/campaigns").json()}
    assert all(c["status"] == "completed" for c in camps.values())

    d = by_ref(client, camps["Attendance confirmation"]["id"])
    assert d["SAMPLE-000"] == "confirmed" and d["SAMPLE-004"] == "unclear" and d["SAMPLE-010"] == "unclear"
    assert d["SAMPLE-006"] == "confirmed" and d["SAMPLE-007"] == "no_response"

    s = by_ref(client, camps["Schedule announcement"]["id"])
    assert s["SPRINT-000"] == "acknowledged"             # "yes" to an announcement is NOT attendance
    assert s["SPRINT-006"] == "acknowledged"             # keypad 1 on the retry
    sn = dict((n, a) for a, n in notes(client, camps["Schedule announcement"]["id"]))
    assert any("Seminar Hall A" in n for n in sn)        # venue question answered from approved info
    assert any("Saturday 10:00-18:00" in n for n in sn)  # schedule question answered from approved info

    h = notes(client, camps["Deadline reminder"]["id"])
    assert any(a == "human_review" and "no approved event information" in n for a, n in h)

    a = client.get("/api/analytics").json()
    assert a["totals"]["campaigns"] == 3 and a["totals"]["real_calls"] == 0
    assert a["totals"]["calls_attempted"] > 20
    assert client.get("/api/analytics", params={"source": "real"}).json()["totals"]["campaigns"] == 0


def test_seed_all_twice_adds_campaigns_not_duplicate_events_and_reset_removes_everything(client):
    client.post("/api/demo/seed-all")
    client.post("/api/demo/seed-all")
    assert len(client.get("/api/events").json()) == 3
    assert len(client.get("/api/campaigns").json()) == 6
    assert client.delete("/api/demo").json()["deleted_campaigns"] == 6
    assert client.get("/api/events").json() == [] and client.get("/api/campaigns").json() == []
