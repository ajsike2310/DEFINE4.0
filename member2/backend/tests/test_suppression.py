"""Opt-out wins everywhere in scope, not only in the campaign where it was said."""
import io

from .conftest import add_recipient, new_campaign, new_event, recipient

PHONE = "+919876543215"        # the simulated provider answers numbers ending in 5 with "Please stop calling me"


def test_spoken_opt_out_in_one_campaign_stops_the_same_number_in_another(client):
    ev = new_event(client)["id"]
    a, b = new_campaign(client, event_id=ev, name="First"), new_campaign(client, event_id=ev, name="Second")
    add_recipient(client, a["id"], PHONE)
    add_recipient(client, b["id"], PHONE)
    assert client.post(f"/api/campaigns/{a['id']}/start").status_code == 200
    assert recipient(client, a["id"], PHONE)["outcome"] == "opted_out"
    other = recipient(client, b["id"], PHONE)
    assert other["opted_out"] is True and other["outcome"] == "opted_out" and other["consent_status"] == "revoked"
    started = client.post(f"/api/campaigns/{b['id']}/start").json()
    assert started["dispatched"] == 0                                           # never dialled


def test_operator_opt_out_applies_everywhere_and_cancels_follow_ups(client):
    ev = new_event(client)["id"]
    a, b = new_campaign(client, event_id=ev), new_campaign(client, event_id=ev, name="Second")
    ra = add_recipient(client, a["id"], "+919876543210")
    add_recipient(client, b["id"], "+919876543210")
    assert client.post(f"/api/recipients/{ra['id']}/opt-out").status_code == 200
    assert recipient(client, b["id"], "+919876543210")["opted_out"] is True


def test_a_suppressed_number_cannot_be_added_again(client):
    ev = new_event(client)["id"]
    a, b = new_campaign(client, event_id=ev), new_campaign(client, event_id=ev, name="Second")
    ra = add_recipient(client, a["id"], "+919876543211")
    client.post(f"/api/recipients/{ra['id']}/opt-out")
    r = client.post(f"/api/campaigns/{b['id']}/recipients", json={"name": "Again", "phone": "+919876543211",
                                                                  "consent_status": "granted"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "suppressed"


def test_csv_import_rejects_suppressed_numbers_and_records_the_reason(client):
    ev = new_event(client)["id"]
    a, b = new_campaign(client, event_id=ev), new_campaign(client, event_id=ev, name="Second")
    ra = add_recipient(client, a["id"], "+919876543212")
    client.post(f"/api/recipients/{ra['id']}/opt-out")
    csv = "name,phone\nBack Again,+919876543212\nFresh,+919876543213\n"
    res = client.post(f"/api/campaigns/{b['id']}/recipients/import", data={"consent_confirmed": "true"},
                      files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")}).json()
    assert res["imported"] == 1 and res["rejected"] == 1 and "opted out" in res["errors"][0]["error"]


def test_copy_and_duplicate_skip_numbers_that_opted_out_elsewhere(client):
    ev = new_event(client)["id"]
    a, b, c = (new_campaign(client, event_id=ev, name=n) for n in ("Camp A", "Camp B", "Camp C"))
    add_recipient(client, a["id"], "+919876543214")
    add_recipient(client, a["id"], "+919876543216")
    rb = add_recipient(client, b["id"], "+919876543214")
    client.post(f"/api/recipients/{rb['id']}/opt-out")                        # opted out in B, not in A
    copied = client.post(f"/api/campaigns/{c['id']}/recipients/copy-from/{a['id']}").json()
    assert copied["copied"] == 1 and copied["skipped"] == 1
    dup = client.post(f"/api/campaigns/{a['id']}/duplicate", json={"copy_participants": True}).json()
    assert dup["copied"] == 1 and dup["skipped"] == 1


def test_lead_conversion_skips_numbers_that_opted_out(client):
    ev = new_event(client)["id"]
    a, b = new_campaign(client, event_id=ev), new_campaign(client, event_id=ev, name="Second")
    ra = add_recipient(client, a["id"], "+919876543217")
    lead = client.post(f"/api/events/{ev}/leads", json={"name": "L", "phone": "+919876543218",
                                                        "consent_status": "granted"}).json()
    client.post(f"/api/recipients/{ra['id']}/opt-out")
    ok = client.post("/api/leads/convert", json={"campaign_id": b["id"], "lead_ids": [lead["id"]]}).json()
    assert ok["converted"] == 1
    again = client.post(f"/api/events/{ev}/leads", json={"name": "Same person", "phone": "+919876543217",
                                                         "consent_status": "granted"}).json()
    res = client.post("/api/leads/convert", json={"campaign_id": b["id"], "lead_ids": [again["id"]]}).json()
    assert res["converted"] == 0 and res["skipped"][0]["reason"] in ("number opted out earlier", "consent revoked")


def test_opt_out_revokes_consent_on_matching_leads(client):
    ev = new_event(client)["id"]
    camp = new_campaign(client, event_id=ev)
    lead = client.post(f"/api/events/{ev}/leads", json={"name": "L", "phone": "+919876543219",
                                                        "consent_status": "granted"}).json()
    r = add_recipient(client, camp["id"], "+919876543219")
    client.post(f"/api/recipients/{r['id']}/opt-out")
    got = next(x for x in client.get(f"/api/events/{ev}/leads").json() if x["id"] == lead["id"])
    assert got["consent_status"] == "revoked" and got["status"] == "lost"


def test_sample_events_stay_isolated_from_each_other(client):
    e1, e2 = new_event(client, name="Sample One")["id"], new_event(client, name="Sample Two")["id"]
    a, b = new_campaign(client, event_id=e1), new_campaign(client, event_id=e2)
    ra = add_recipient(client, a["id"], "+919876543210")
    client.post(f"/api/recipients/{ra['id']}/opt-out")
    add_recipient(client, b["id"], "+919876543210")                           # sample data: different event, allowed
    assert recipient(client, b["id"], "+919876543210")["opted_out"] is False


def test_real_data_is_suppressed_across_events(client, real_data):
    e1, e2 = new_event(client, name="Real One")["id"], new_event(client, name="Real Two")["id"]
    a, b = new_campaign(client, event_id=e1), new_campaign(client, event_id=e2)
    assert a["is_demo"] is False
    ra = add_recipient(client, a["id"], "+919876543210")
    other = add_recipient(client, b["id"], "+919876543210")                   # both rows exist before the opt-out
    client.post(f"/api/recipients/{ra['id']}/opt-out")
    assert recipient(client, b["id"], "+919876543210")["opted_out"] is True and other["id"]
    new = client.post(f"/api/campaigns/{b['id']}/recipients", json={"name": "N", "phone": "+919876543210"})
    assert new.status_code == 409
