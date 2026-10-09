import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"   # must be set before the app module is imported

import pytest
from fastapi.testclient import TestClient

from member2.backend.app.main import create_app


@pytest.fixture
def client():
    app = create_app("sqlite:///:memory:")
    with TestClient(app) as c:
        c.app_ = app
        yield c


def new_event(client, **over):
    r = client.post("/api/events", json={"name": "Test Event", **over})
    assert r.status_code == 201, r.text
    return r.json()


def new_campaign(client, **over):
    if "event_id" not in over:
        over["event_id"] = new_event(client)["id"]
    body = {"name": "Test campaign", "purpose": "attendance_confirmation",
            "messages": {"en": "Press 1 to confirm."}, "languages": ["en"], **over}
    r = client.post("/api/campaigns", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def add_recipient(client, cid, phone, consent="granted", **over):
    r = client.post(f"/api/campaigns/{cid}/recipients",
                    json={"name": "T " + phone[-2:], "phone": phone, "consent_status": consent, **over})
    assert r.status_code == 201, r.text
    return r.json()
