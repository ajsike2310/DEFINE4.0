"""Lead generation, campaign management and the Data & AI quality report."""
import io

from member4.quality.conftest import add_recipient, new_campaign, new_event


def lead(client, eid, phone, **over):
    r = client.post(f"/api/events/{eid}/leads", json={"name": "L " + phone[-2:], "phone": phone, **over})
    return r


# ---- leads ---------------------------------------------------------------------------------
def test_capture_validates_and_blocks_duplicates(client):
    eid = new_event(client)["id"]
    ok = lead(client, eid, "+919876543210", consent_status="granted", source="registration_form",
              email="A@Example.com", preferred_language="ml")
    assert ok.status_code == 201
    body = ok.json()
    assert body["email"] == "a@example.com" and body["status"] == "new"
    assert lead(client, eid, "+919876543210").status_code == 409
    assert lead(client, eid, "98765").status_code == 422
    assert lead(client, eid, "+919876543211", source="bought_list").status_code == 422
    assert lead(client, eid, "+919876543211", email="nope").status_code == 422
    assert client.post("/api/events/999/leads", json={"name": "x", "phone": "+919876543212"}).status_code == 404


def test_score_is_a_transparent_checklist_and_revoked_is_zero(client):
    eid = new_event(client)["id"]
    best = lead(client, eid, "+919876543210", consent_status="granted", source="registration_form",
                email="a@b.co", preferred_language="en", interest="Web").json()
    bare = lead(client, eid, "+919876543211").json()
    gone = lead(client, eid, "+919876543212", consent_status="revoked", email="a@b.co").json()
    assert best["score"] == 100 and any("consent granted" in r for r in best["score_reasons"])
    assert bare["score"] == 10 + 5 and any("consent not recorded" in r for r in bare["score_reasons"])
    assert gone["score"] == 0
    listed = client.get(f"/api/events/{eid}/leads").json()
    assert [x["id"] for x in listed][0] == best["id"] and listed[-1]["id"] == gone["id"]   # most ready first


def test_filters_and_search(client):
    eid = new_event(client)["id"]
    lead(client, eid, "+919876543210", name="Anita Rao", source="referral")
    lead(client, eid, "+919876543211", name="Ben Joy", email="ben@x.io")
    assert len(client.get(f"/api/events/{eid}/leads", params={"source": "referral"}).json()) == 1
    assert [x["name"] for x in client.get(f"/api/events/{eid}/leads", params={"q": "ben"}).json()] == ["Ben Joy"]
    assert len(client.get(f"/api/events/{eid}/leads", params={"status": "qualified"}).json()) == 0


def test_csv_import_reports_rejections_and_logs_the_run(client):
    eid = new_event(client)["id"]
    csv_text = ("name,phone,email,interest,language\n"
                "Asha,+919876543210,asha@x.io,AI,en\n"
                "Bijo,+919876543211,,Web,ml\n"
                "Bad,12345,,,\n"
                "Asha again,+919876543210,,,\n")
    r = client.post(f"/api/events/{eid}/leads/import", data={"consent_confirmed": "true"},
                    files={"file": ("leads.csv", io.BytesIO(csv_text.encode()), "text/csv")})
    assert r.status_code == 200
    assert r.json()["imported"] == 2 and r.json()["rejected"] == 2
    leads = client.get(f"/api/events/{eid}/leads").json()
    assert all(x["consent_status"] == "granted" and x["source"] == "csv_import" for x in leads)
    q = client.get("/api/quality", params={"event_id": eid}).json()["data_gathering"]["imports"]
    assert q["rows"] == 4 and q["imported"] == 2 and q["rejected"] == 2 and q["acceptance_rate"] == 0.5
    assert {x["reason"] for x in q["top_rejections"]} >= {"duplicate phone"}
    # without the consent tick nothing is marked as consented
    r2 = client.post(f"/api/events/{eid}/leads/import",
                     files={"file": ("l.csv", io.BytesIO(b"name,phone\nNew,+919876543299\n"), "text/csv")})
    assert r2.json()["imported"] == 1
    assert client.get(f"/api/events/{eid}/leads", params={"q": "new"}).json()[0]["consent_status"] == "unknown"
    assert client.post(f"/api/events/{eid}/leads/import",
                       files={"file": ("l.csv", io.BytesIO(b"x,y\n1,2\n"), "text/csv")}).status_code == 422


def test_convert_respects_consent_event_and_duplicates(client):
    ev = new_event(client)
    other = new_event(client)
    camp = new_campaign(client, event_id=ev["id"], languages=["en"], messages={"en": "Press 1."})
    a = lead(client, ev["id"], "+919876543210", consent_status="granted", preferred_language="ml",
             interest="Web").json()
    unk = lead(client, ev["id"], "+919876543211").json()
    rev = lead(client, ev["id"], "+919876543212", consent_status="revoked").json()
    foreign = lead(client, other["id"], "+919876543213", consent_status="granted").json()
    add_recipient(client, camp["id"], "+919876543214")
    dup = lead(client, ev["id"], "+919876543214", consent_status="granted").json()

    res = client.post("/api/leads/convert", json={"campaign_id": camp["id"],
                      "lead_ids": [a["id"], unk["id"], rev["id"], foreign["id"], dup["id"], 9999]}).json()
    assert res["converted"] == 1
    reasons = {s["lead_id"]: s["reason"] for s in res["skipped"]}
    assert "consent not recorded" in reasons[unk["id"]] and reasons[rev["id"]] == "consent revoked"
    assert "different event" in reasons[foreign["id"]] and "already a participant" in reasons[dup["id"]]
    assert reasons[9999] == "lead not found"

    recs = {r["phone"]: r for r in client.get(f"/api/campaigns/{camp['id']}/recipients").json()}
    r = recs["+919876543210"]
    assert r["consent_status"] == "granted" and r["segment"] == "Web"
    assert r["preferred_language"] is None            # 'ml' is not enabled on this campaign
    got = [x for x in client.get(f"/api/events/{ev['id']}/leads").json() if x["id"] == a["id"]][0]
    assert got["status"] == "converted" and got["campaign_id"] == camp["id"] and got["recipient_outcome"] == "pending"
    # converting again is refused
    again = client.post("/api/leads/convert", json={"campaign_id": camp["id"], "lead_ids": [a["id"]]}).json()
    assert again["converted"] == 0 and again["skipped"][0]["reason"] == "already converted"


def test_revoking_consent_closes_a_lead_and_opts_out_a_converted_one(client):
    ev = new_event(client)
    camp = new_campaign(client, event_id=ev["id"])
    a = lead(client, ev["id"], "+919876543210", consent_status="granted").json()
    b = lead(client, ev["id"], "+919876543211", consent_status="granted").json()
    client.post("/api/leads/convert", json={"campaign_id": camp["id"], "lead_ids": [b["id"]]})
    ra = client.patch(f"/api/leads/{a['id']}", json={"consent_status": "revoked"}).json()
    assert ra["status"] == "lost" and ra["score"] == 0
    client.patch(f"/api/leads/{b['id']}", json={"consent_status": "revoked"})
    rec = client.get(f"/api/campaigns/{camp['id']}/recipients").json()[0]
    assert rec["opted_out"] and rec["outcome"] == "opted_out" and rec["consent_status"] == "revoked"
    # manual status rules
    c = lead(client, ev["id"], "+919876543212").json()
    assert client.patch(f"/api/leads/{c['id']}", json={"status": "qualified"}).json()["status"] == "qualified"
    assert client.patch(f"/api/leads/{c['id']}", json={"status": "converted"}).status_code == 422
    assert client.patch(f"/api/leads/{b['id']}", json={"status": "new"}).status_code == 409


def test_summary_uses_documented_denominators(client):
    ev = new_event(client)
    camp = new_campaign(client, event_id=ev["id"])
    empty = client.get(f"/api/events/{ev['id']}/leads/summary").json()
    assert empty["total"] == 0 and empty["conversion_rate"] is None and empty["consent_rate"] is None
    a = lead(client, ev["id"], "+919876543210", consent_status="granted", source="referral").json()
    lead(client, ev["id"], "+919876543211", source="referral")
    lead(client, ev["id"], "+919876543212", consent_status="granted", source="walk_in")
    client.post("/api/leads/convert", json={"campaign_id": camp["id"], "lead_ids": [a["id"]]})
    s = client.get(f"/api/events/{ev['id']}/leads/summary").json()
    assert s["total"] == 3 and s["by_status"]["converted"] == 1
    assert s["conversion_rate"] == round(1 / 3, 4) and s["consent_rate"] == round(2 / 3, 4)
    assert s["ready_to_convert"] == 1
    ref = next(x for x in s["by_source"] if x["source"] == "referral")
    assert ref["leads"] == 2 and ref["converted"] == 1 and ref["conversion_rate"] == 0.5


# ---- campaign management -----------------------------------------------------------------------
def test_overview_gives_progress_and_next_step(client):
    ev = new_event(client)
    empty = new_campaign(client, event_id=ev["id"], name="Empty one")
    ready = new_campaign(client, event_id=ev["id"], name="Ready one")
    add_recipient(client, ready["id"], "+919876543210")
    add_recipient(client, ready["id"], "+919876543211", consent="unknown")
    rows = {r["name"]: r for r in client.get("/api/campaigns/overview", params={"event_id": ev["id"]}).json()["campaigns"]}
    assert rows["Empty one"]["next_step"] == "Add participants" and rows["Empty one"]["progress"] is None
    assert rows["Ready one"]["next_step"].startswith("Ready to start") and rows["Ready one"]["missing_consent"] == 1
    client.post(f"/api/campaigns/{ready['id']}/start")
    ov = client.get("/api/campaigns/overview", params={"event_id": ev["id"]}).json()
    assert ov["by_status"]["draft"] == 1 and sum(ov["by_status"].values()) == 2
    assert empty["id"] != ready["id"]


def test_duplicate_copies_settings_and_safe_participants_only(client):
    ev = new_event(client)
    src = new_campaign(client, event_id=ev["id"], name="Original", max_attempts=2)
    add_recipient(client, src["id"], "+919876543210")
    gone = add_recipient(client, src["id"], "+919876543211")
    client.post(f"/api/recipients/{gone['id']}/opt-out")
    r = client.post(f"/api/campaigns/{src['id']}/duplicate", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["campaign"]["status"] == "draft" and body["campaign"]["name"] == "Original (copy)"
    assert body["campaign"]["max_attempts"] == 2 and body["copied"] == 1 and body["skipped"] == 1
    got = client.get(f"/api/campaigns/{body['campaign']['id']}/recipients").json()
    assert [g["phone"] for g in got] == ["+919876543210"] and got[0]["outcome"] == "pending"
    bare = client.post(f"/api/campaigns/{src['id']}/duplicate", json={"name": "Just settings", "copy_participants": False}).json()
    assert bare["copied"] == 0 and bare["campaign"]["recipient_count"] == 0
    assert client.post("/api/campaigns/999/duplicate", json={}).status_code == 404


# ---- data & AI quality ----------------------------------------------------------------------------
def test_quality_on_empty_data_has_no_fake_numbers(client):
    q = client.get("/api/quality").json()
    assert q["data_gathering"]["participants"] == 0 and q["data_gathering"]["consent_recorded_rate"] is None
    assert q["data_gathering"]["imports"]["acceptance_rate"] is None
    assert q["ai"]["responses"] == 0 and q["ai"]["auto_handled_rate"] is None
    assert q["integrity_summary"]["clean"] == q["integrity_summary"]["checks"]
    assert client.get("/api/quality", params={"source": "bogus"}).status_code == 422


def test_quality_after_full_simulation_is_clean_and_consistent(client):
    client.post("/api/demo/seed-all", params={"run": "true"})
    q = client.get("/api/quality", params={"source": "simulated"}).json()
    bad = [c for c in q["integrity"] if c["violations"]]
    assert not bad, bad
    assert q["integrity_summary"]["checks"] == len(q["integrity"]) >= 8
    ai = q["ai"]
    assert ai["responses"] > 0 and ai["by_method"]["keypad"] + ai["by_method"]["phrase_rules"] + ai["by_method"]["none"] == ai["responses"]
    assert 0 < ai["auto_handled_rate"] <= 1 and ai["clarification"]["attempted"] == 0
    assert ai["info_questions"]["asked"] == ai["info_questions"]["answered_from_approved_info"] + ai["info_questions"]["sent_to_a_person"]
    assert q["calls"]["provider_events"]["stored"] == q["calls"]["provider_events"]["applied"] + q["calls"]["provider_events"]["ignored"]
    # the real filter sees none of the simulated data
    real = client.get("/api/quality", params={"source": "real"}).json()
    assert real["data_gathering"]["participants"] == 0 and real["ai"]["responses"] == 0


def test_integrity_check_actually_detects_a_violation(client):
    """A check that can never fail proves nothing: corrupt one row and watch it flag."""
    from member2.backend.app.models import Recipient
    camp = new_campaign(client)
    add_recipient(client, camp["id"], "+919876543210")
    with client.app_.state.session_factory() as db:
        r = db.query(Recipient).first()
        r.outcome = "confirmed"                       # an answer-based outcome with no recorded response
        r.opted_out = True                            # and an opt-out that does not hold
        db.commit()
    checks = {c["key"]: c for c in client.get("/api/quality").json()["integrity"]}
    assert checks["outcome_has_response"]["violations"] == 1
    assert checks["optout_wins"]["violations"] == 1


def test_phrase_check_reports_groups_and_no_false_confirms(client):
    pc = client.get("/api/quality").json()["ai"]["phrase_check"]
    assert pc["cases"] >= 30 and pc["passed"] == pc["cases"] and pc["failures"] == []
    assert pc["false_confirms_on_ambiguous"] == 0
    assert {"en", "ml", "manglish", "mixed", "ambiguous"} <= {g["group"] for g in pc["by_group"]}
    assert "accuracy" in pc["note"]


def test_sample_leads_are_seeded_labelled_and_removed_with_the_samples(client):
    client.post("/api/demo/seed-all")
    evs = client.get("/api/events").json()
    for e in evs:
        ls = client.get(f"/api/events/{e['id']}/leads").json()
        assert len(ls) == 10 and all(x["is_demo"] for x in ls)
        assert any(x["consent_status"] == "revoked" and x["status"] == "lost" for x in ls)
    # re-seeding must not duplicate the leads
    client.post("/api/demo/seed-all")
    assert len(client.get(f"/api/events/{evs[0]['id']}/leads").json()) == 10
    client.delete("/api/demo")
    from member2.backend.app.models import ImportRun, Lead
    with client.app_.state.session_factory() as db:
        assert db.query(Lead).count() == 0 and db.query(ImportRun).count() == 0


def test_seed_sample_leads_backfills_existing_sample_events_once(client):
    client.post("/api/demo/seed-all")
    from member2.backend.app.models import Lead
    with client.app_.state.session_factory() as db:
        db.query(Lead).delete()
        db.commit()
    assert client.post("/api/demo/seed-leads").json() == {"leads_added": 30}
    assert client.post("/api/demo/seed-leads").json() == {"leads_added": 0}
