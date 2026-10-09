"""CSV exports: masked by default, spreadsheet-safe."""
import csv
import io

from member2.backend.app.services.csv_io import safe_cell, to_csv

from .conftest import add_recipient, new_campaign, new_event


def rows(resp):
    return list(csv.DictReader(io.StringIO(resp.text)))


def test_safe_cell_neutralises_formulas_only():
    assert safe_cell("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert safe_cell("+91 98765") == "'+91 98765" and safe_cell("-1") == "'-1" and safe_cell("@cmd") == "'@cmd"
    assert safe_cell("Asha K") == "Asha K" and safe_cell(None) == "" and safe_cell(7) == "7"
    assert to_csv(["a", "b"], [["x,y", '"q"']]).splitlines()[1] == '"x,y","""q"""'


def test_participant_export_has_outcomes_masks_numbers_and_is_an_attachment(client):
    ev = new_event(client)["id"]
    cid = new_campaign(client, event_id=ev)["id"]
    add_recipient(client, cid, "+919876543210", name="=EVIL()")
    add_recipient(client, cid, "+919876543215")
    client.post(f"/api/campaigns/{cid}/start")
    r = client.get(f"/api/events/{ev}/export/participants.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert f"event-{ev}-participants.csv" in r.headers["content-disposition"]
    data = {x["name"] if x["name"] != "'=EVIL()" else "evil": x for x in rows(r)}
    assert "'=EVIL()" in r.text and data["evil"]["outcome"] == "confirmed" and data["evil"]["last_intent"] == "confirm"
    assert "9876543210" not in r.text and data["evil"]["phone"].startswith("+91") and "*" in data["evil"]["phone"]
    stopped = next(x for x in rows(r) if x["opted_out"] == "yes")
    assert stopped["outcome"] == "opted_out" and stopped["consent"] == "revoked" and stopped["calls"] == "1"
    assert "+919876543210" in client.get(f"/api/events/{ev}/export/participants.csv", params={"masked": "false"}).text


def test_lead_export_includes_score_and_status(client):
    ev = new_event(client)["id"]
    client.post(f"/api/events/{ev}/leads", json={"name": "Lead One", "phone": "+919876543211", "consent_status": "granted",
                                                 "source": "registration_form", "email": "a@b.co", "interest": "AI",
                                                 "preferred_language": "en"})
    out = rows(client.get(f"/api/events/{ev}/export/leads.csv"))
    assert out[0]["readiness_score"] == "100" and out[0]["status"] == "new" and "*" in out[0]["phone"]


def test_export_of_unknown_event_is_404_and_empty_event_is_just_a_header(client):
    assert client.get("/api/events/999/export/leads.csv").status_code == 404
    ev = new_event(client)["id"]
    assert len(client.get(f"/api/events/{ev}/export/participants.csv").text.strip().splitlines()) == 1
