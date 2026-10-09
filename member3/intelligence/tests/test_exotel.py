import httpx
import pytest

from member3.integrations.base import ProviderError
from member3.integrations.exotel.provider import ExotelProvider

CFG = dict(account_sid="sid", api_key="k", api_token="t", caller_id="0800", flow_url="http://my.exotel.com/sid/exoml/start_voice/1")


def test_requires_config():
    with pytest.raises(ProviderError):
        ExotelProvider(**{**CFG, "api_key": ""})


def test_request_shape_with_mock_transport():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], req.content.decode()
        return httpx.Response(200, json={"Call": {"Sid": "abc123", "Status": "queued"}})

    p = ExotelProvider(**CFG, client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = p.initiate_call(attempt_id=7, attempt_number=1, to="+15550100100", language="en", message="hi")
    assert res.provider_call_id == "abc123" and res.events == []
    assert seen["url"] == "https://api.exotel.com/v1/Accounts/sid/Calls/connect.json"
    assert seen["auth"].startswith("Basic ") and "CustomField=7" in seen["body"]


def test_allowlist_blocks_unapproved_numbers():
    hit = []
    p = ExotelProvider(**CFG, allowed_numbers=["+15550100100"],
                       client=httpx.Client(transport=httpx.MockTransport(lambda r: hit.append(1) or httpx.Response(200, json={"Call": {"Sid": "s"}}))))
    with pytest.raises(ProviderError):
        p.initiate_call(attempt_id=1, attempt_number=1, to="+15550100101", language="en", message="")
    assert not hit


def test_http_error_becomes_provider_error():
    p = ExotelProvider(**CFG, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(ProviderError):
        p.initiate_call(attempt_id=1, attempt_number=1, to="+15550100100", language="en", message="")


def test_stream_mode_sends_streamurl_instead_of_flow():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"Call": {"Sid": "s1"}})

    cfg = {k: v for k, v in CFG.items() if k != "flow_url"}
    p = ExotelProvider(**cfg, flow_url="", stream_url="wss://h.example/live/exotel?token=t",
                       client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert p.initiate_call(attempt_id=3, attempt_number=1, to="+15550100100", language="en", message="").provider_call_id == "s1"
    assert "StreamUrl=wss" in seen["body"] and "StreamType=bidirectional" in seen["body"] and "Url=" not in seen["body"].replace("StreamUrl=", "")


def test_needs_flow_or_stream_url():
    with pytest.raises(ProviderError):
        ExotelProvider(**{**CFG, "flow_url": ""})


def test_xml_reply_is_still_understood():
    xml = "<TwilioResponse><Call><Sid>xml123</Sid><Status>queued</Status></Call></TwilioResponse>"
    p = ExotelProvider(**CFG, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=xml))))
    assert p.initiate_call(attempt_id=1, attempt_number=1, to="+15550100100", language="en", message="").provider_call_id == "xml123"


def test_garbage_reply_is_a_clean_error():
    p = ExotelProvider(**CFG, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="oops"))))
    with pytest.raises(ProviderError):
        p.initiate_call(attempt_id=1, attempt_number=1, to="+15550100100", language="en", message="")
