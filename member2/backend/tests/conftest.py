import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"   # must be set before the app module is imported

import pytest
from fastapi.testclient import TestClient

from member2.backend.app.core.config import get_settings
from member2.backend.app.main import create_app


@pytest.fixture
def client():
    app = create_app("sqlite:///:memory:")
    with TestClient(app) as c:
        c.app_ = app
        yield c


@pytest.fixture
def real_data(monkeypatch):
    """Campaigns created from now on are treated as real (not sample) data, as with CALL_PROVIDER=exotel."""
    monkeypatch.setattr(get_settings(), "call_provider", "exotel")


def new_event(client, **over):
    r = client.post("/api/events", json={"name": "Test Event", **over})
    assert r.status_code == 201, r.text
    return r.json()


def new_campaign(client, event_id=None, **over):
    body = {"event_id": event_id or new_event(client)["id"], "name": "Test campaign",
            "purpose": "attendance_confirmation", "messages": {"en": "Press 1 to confirm."}, "languages": ["en"], **over}
    r = client.post("/api/campaigns", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def add_recipient(client, cid, phone, consent="granted", expect=201, **over):
    r = client.post(f"/api/campaigns/{cid}/recipients",
                    json={"name": "P " + phone[-2:], "phone": phone, "consent_status": consent, **over})
    assert r.status_code == expect, r.text
    return r.json()


def recipient(client, cid, phone):
    return next(r for r in client.get(f"/api/campaigns/{cid}/recipients").json() if r["phone"] == phone)
