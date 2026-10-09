"""Browser demo call: ElevenLabs voice + speech-to-text, replies classified by the same rules as any provider."""
import httpx
import pytest

from member3.integrations.base import ProviderError
from member3.integrations.elevenlabs.client import ElevenLabsClient, ElevenLabsError
from member2.backend.app.core.config import get_settings
from member4.quality.conftest import add_recipient, new_campaign, new_event


class FakeVoice:
    def __init__(self, heard="Yes, I will be there", fail=False):
        self.heard, self.fail, self.spoken = heard, fail, []

    def speak(self, text):
        self.spoken.append(text)
        return b"ID3-fake-mp3"

    def transcribe(self, audio, filename="x", content_type="audio/webm", language_hint=None):
        if self.fail:
            raise ElevenLabsError("ElevenLabs speech-to-text failed (HTTP 429: rate or quota limit)")
        return self.heard


def start(client, cid, rid, mode="main"):
    return client.post(f"/api/campaigns/{cid}/recipients/{rid}/browser-call", params={"mode": mode})


def setup(client, **camp):
    c = new_campaign(client, **camp)
    r = add_recipient(client, c["id"], "+919876543210")
    return c, r


# ---- ElevenLabs client (request shape only; the real service is untested until a key is supplied) --------
def test_client_request_shape_and_error_hides_body():
    seen = {}

    def handler(req: httpx.Request):
        seen[req.url.path] = (req.headers.get("xi-api-key"), req.content)
        if req.url.path.endswith("speech-to-text"):
            return httpx.Response(200, json={"text": " yes "})
        return httpx.Response(200, content=b"mp3")

    c = ElevenLabsClient("k-test", voice_id="v1", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.speak("hello") == b"mp3"
    assert c.transcribe(b"audio") == "yes"
    assert seen["/v1/text-to-speech/v1"][0] == "k-test" and b'"model_id"' in seen["/v1/text-to-speech/v1"][1]
    bad = ElevenLabsClient("k", voice_id="v", client=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"detail": "secret echo"}))))
    with pytest.raises(ProviderError) as e:
        bad.speak("x")
    assert "401" in str(e.value) and "secret echo" not in str(e.value)
    with pytest.raises(ElevenLabsError):
        ElevenLabsClient("", voice_id="v")


# ---- the call ------------------------------------------------------------------------------------------
def test_keypad_reply_sets_outcome_and_is_simulated(client):
    c, r = setup(client)
    call = start(client, c["id"], r["id"]).json()
    assert call["simulated"] is True and call["message"] == "Press 1 to confirm."
    res = client.post(f"/api/browser-calls/{call['attempt_id']}/respond", json={"dtmf": "1"}).json()
    assert res["outcome"] == "confirmed" and res["method"] == "dtmf" and res["status"] == "completed"
    att = client.get(f"/api/campaigns/{c['id']}/attempts").json()[0]
    assert att["provider"] == "browser_demo" and att["is_simulated"] is True


def test_spoken_reply_is_transcribed_then_classified_by_rules(client):
    c, r = setup(client)
    client.app_.state.elevenlabs_override = FakeVoice(heard="Please stop calling me")
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    res = client.post(f"/api/browser-calls/{a}/respond-audio", files={"file": ("r.webm", b"abc", "audio/webm")}).json()
    assert res["heard"] == "Please stop calling me" and res["outcome"] == "opted_out"
    rec = client.get(f"/api/campaigns/{c['id']}/recipients").json()[0]
    assert rec["opted_out"] is True


def test_ambiguous_speech_is_not_confirmation(client):
    c, r = setup(client)
    client.app_.state.elevenlabs_override = FakeVoice(heard="hmm maybe, I will see")
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    res = client.post(f"/api/browser-calls/{a}/respond-audio", files={"file": ("r.webm", b"abc", "audio/webm")}).json()
    assert res["outcome"] == "unclear" and res["needs_review"] is True


def test_failed_transcription_records_nothing_and_call_stays_open(client):
    c, r = setup(client)
    client.app_.state.elevenlabs_override = FakeVoice(fail=True)
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    bad = client.post(f"/api/browser-calls/{a}/respond-audio", files={"file": ("r.webm", b"abc", "audio/webm")})
    assert bad.status_code == 502 and bad.json()["error"]["code"] == "transcription_failed"
    assert client.get(f"/api/campaigns/{c['id']}/recipients").json()[0]["outcome"] == "pending"
    assert client.post(f"/api/browser-calls/{a}/respond", json={"dtmf": "2"}).json()["outcome"] == "declined"


def test_speak_uses_only_the_call_script_and_needs_a_key(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "elevenlabs_api_key", "")    # tests never depend on the developer's real .env key
    c, r = setup(client)
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    off = client.post(f"/api/browser-calls/{a}/speak")
    assert off.status_code == 503 and off.json()["error"]["code"] == "voice_unavailable"
    voice = FakeVoice()
    client.app_.state.elevenlabs_override = voice
    ok = client.post(f"/api/browser-calls/{a}/speak")
    assert ok.status_code == 200 and ok.headers["content-type"] == "audio/mpeg" and voice.spoken == ["Press 1 to confirm."]


def test_guards_and_one_live_call(client):
    c, r = setup(client)
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    assert start(client, c["id"], r["id"]).status_code == 409                       # already in progress
    assert client.post(f"/api/browser-calls/{a}/respond", json={}).status_code == 422   # empty reply
    assert client.post(f"/api/browser-calls/{a}/hangup").json()["status"] == "completed"
    assert client.post(f"/api/browser-calls/{a}/respond", json={"dtmf": "1"}).status_code == 409   # call over
    assert client.get(f"/api/campaigns/{c['id']}/recipients").json()[0]["outcome"] == "pending"    # nothing guessed
    assert client.post("/api/browser-calls/999/respond", json={"dtmf": "1"}).status_code == 404


def test_opted_out_and_no_consent_cannot_be_called(client):
    c = new_campaign(client)
    out = add_recipient(client, c["id"], "+919876543211")
    client.post(f"/api/recipients/{out['id']}/opt-out")
    assert start(client, c["id"], out["id"]).status_code == 409
    nc = add_recipient(client, c["id"], "+919876543212", consent="unknown")
    assert start(client, c["id"], nc["id"]).status_code == 409


def test_clarify_mode_uses_the_one_question_script(client):
    c, r = setup(client)
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    client.app_.state.elevenlabs_override = FakeVoice(heard="hmm not sure")
    client.post(f"/api/browser-calls/{a}/respond-audio", files={"file": ("r.webm", b"abc", "audio/webm")})
    q = start(client, c["id"], r["id"], mode="clarify")
    assert q.status_code == 201 and "Press 1 for yes" in q.json()["message"]
    done = client.post(f"/api/browser-calls/{q.json()['attempt_id']}/respond", json={"dtmf": "1"}).json()
    assert done["outcome"] == "confirmed"
    assert start(client, c["id"], r["id"], mode="clarify").status_code == 409        # only once


def test_voice_status_never_returns_a_key(client):
    body = client.get("/api/voice/status").json()
    assert "configured" in body and not any("key" in k for k in body)


# ---- live conversation: what the agent says back ---------------------------------------------------------
def test_closing_line_follows_the_intent_and_never_improvises(client):
    from member3.intelligence.policies.closing_lines import LINES, closing_line
    assert "not call you again" in closing_line("opt_out", "en")
    assert closing_line("opt_out", "ml") == LINES["opt_out"]["ml"] and closing_line("nonsense", "en") == LINES["unclear"]["en"]
    assert closing_line("information_requested", "en", "At MBCET Block A.") == "At MBCET Block A. Goodbye."
    assert "get back to you" in closing_line("information_requested", "en")        # no approved answer -> a person


def test_reply_audio_matches_intent_and_unclear_asks_for_clarify_once(client):
    c, r = setup(client)
    voice = FakeVoice(heard="hmm maybe, not sure")
    client.app_.state.elevenlabs_override = voice
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    assert client.post(f"/api/browser-calls/{a}/speak-reply").status_code == 409          # nothing said yet
    res = client.post(f"/api/browser-calls/{a}/respond-audio", files={"file": ("r.webm", b"abc", "audio/webm")}).json()
    assert res["outcome"] == "unclear" and res["next"] == "clarify"
    q = start(client, c["id"], r["id"], mode="clarify").json()["attempt_id"]
    done = client.post(f"/api/browser-calls/{q}/respond", json={"dtmf": "2"}).json()
    assert done["outcome"] == "declined" and done["next"] == "close"
    sp = client.post(f"/api/browser-calls/{q}/speak-reply")
    assert sp.status_code == 200 and voice.spoken[-1].startswith("Understood, thank you for letting us know")


def test_clarify_answer_that_is_still_unclear_closes_instead_of_asking_again(client):
    c, r = setup(client)
    client.app_.state.elevenlabs_override = FakeVoice(heard="hmm maybe")
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    client.post(f"/api/browser-calls/{a}/respond-audio", files={"file": ("r.webm", b"abc", "audio/webm")})
    q = start(client, c["id"], r["id"], mode="clarify").json()["attempt_id"]
    res = client.post(f"/api/browser-calls/{q}/respond-audio", files={"file": ("r.webm", b"abc", "audio/webm")}).json()
    assert res["outcome"] == "unclear" and res["next"] == "close"


def test_question_is_answered_only_from_approved_info(client):
    ev = new_event(client, approved_info={"venue": "Main Auditorium, Block A"})
    c = new_campaign(client, event_id=ev["id"])
    r = add_recipient(client, c["id"], "+919876543210")
    voice = FakeVoice(heard="Where is the venue?")
    client.app_.state.elevenlabs_override = voice
    a = start(client, c["id"], r["id"]).json()["attempt_id"]
    client.post(f"/api/browser-calls/{a}/respond-audio", files={"file": ("r.webm", b"abc", "audio/webm")})
    sp = client.post(f"/api/browser-calls/{a}/speak-reply")
    assert sp.status_code == 200 and voice.spoken[-1] == "Main Auditorium, Block A. Goodbye."
    assert "Main%20Auditorium" in sp.headers["x-spoken-text"]
