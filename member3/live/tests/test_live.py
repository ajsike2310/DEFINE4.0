import httpx
import numpy as np
import pytest

from member3.integrations.elevenlabs.client import ElevenLabsClient
from member3.intelligence.transcription.base import TranscriptionUnavailable
from member3.intelligence.transcription.elevenlabs_stt import ElevenLabsTranscriber
from member3.live.audio import UtteranceSegmenter, chunk_pcm, pcm16_to_wav
from member3.live.session import Clear, Hangup, LiveSession, Say

RATE = 8000


def tone(ms, amp=4000):
    t = np.arange(int(RATE * ms / 1000))
    return (amp * np.sin(2 * np.pi * 300 * t / RATE)).astype("<i2").tobytes()


def quiet(ms):
    return bytes(int(RATE * ms / 1000) * 2)


def make(replies, **kw):
    """Session whose 'STT' returns the next scripted reply; TTS is 500 ms of silence."""
    events, replies = [], list(replies)
    s = LiveSession(provider_call_id="c1", greeting="Hello, will you attend?", tts=lambda t: quiet(500),
                    stt=lambda wav: replies.pop(0), emit=events.append, **kw)
    return s, events


def speak(s, replies_ms=400):
    """Skip past the bot's own speech, then play one utterance followed by silence."""
    out = s.on_audio(quiet(600))
    out += s.on_audio(tone(replies_ms))
    out += s.on_audio(quiet(900))
    return out


def test_segmenter_returns_utterance_after_silence():
    seg = UtteranceSegmenter(sample_rate=RATE)
    assert seg.feed(quiet(300)) == []
    got = seg.feed(tone(400) + quiet(900))
    assert len(got) == 1 and len(got[0]) >= len(tone(400))


def test_segmenter_ignores_blips_and_handles_odd_chunks():
    seg = UtteranceSegmenter(sample_rate=RATE)
    assert seg.feed(tone(60) + quiet(900)) == []                     # shorter than min speech
    data = tone(400) + quiet(900)
    got = [u for c in chunk_pcm(data, RATE, 7) for u in seg.feed(c)]  # 7 ms chunks split frames
    assert len(got) == 1


def test_wav_header():
    assert pcm16_to_wav(quiet(100), RATE)[:4] == b"RIFF"


def test_confirm_flow_emits_one_response_and_hangs_up():
    s, events = make(["Yes, I will come"])
    assert isinstance(s.start()[0], Say)
    out = speak(s)
    assert [type(a) for a in out] == [Say, Hangup] and out[1].delay_ms == 500
    assert "noted that you will attend" in out[0].text
    assert len(events) == 1 and events[0].kind == "response" and events[0].text == "Yes, I will come"
    assert s.decision.intent.value == "confirm" and s.done


def test_hedge_asks_once_then_hands_to_human():
    s, events = make(["maybe, I will let you know", "hmm not sure"])
    s.start()
    first = speak(s)
    assert len(first) == 1 and "yes or no" in first[0].text and not events
    second = speak(s)
    assert isinstance(second[-1], Hangup) and "team member" in second[0].text
    assert events[0].text == "hmm not sure" and s.decision.intent.value == "unclear"


def test_clarify_answer_resolves():
    s, events = make(["maybe", "yes"])
    s.start(); speak(s); speak(s)
    assert events[0].text == "yes" and s.decision.intent.value == "confirm"


def test_silence_reprompts_once_then_closes_without_text():
    s, events = make([])
    s.start()
    out = s.on_audio(quiet(600 + 7000))
    assert len(out) == 1 and "did not catch" in out[0].text
    out = s.on_audio(quiet(500 + 7000))
    assert isinstance(out[-1], Hangup) and events[0].text is None and events[0].dtmf is None


def test_dtmf_is_authoritative():
    s, events = make([])
    s.start()
    out = s.on_dtmf("2")
    assert isinstance(out[0], Clear) and events[0].dtmf == "2" and s.decision.intent.value == "decline"


def test_info_question_uses_only_approved_answer():
    s, events = make(["Where is the venue?"], info_answers={"venue": "The main auditorium"})
    s.start()
    out = speak(s)
    assert out[0].text == "The main auditorium. Goodbye."


def test_stt_failure_goes_to_human_review():
    def boom(wav):
        raise RuntimeError("down")
    ev = []
    s = LiveSession(provider_call_id="c", greeting="hi", tts=lambda t: quiet(100), stt=boom, emit=ev.append)
    s.start(); out = speak(s)
    assert isinstance(out[-1], Hangup) and s.decision.intent.value == "human_required"


def test_audio_during_bot_speech_is_ignored_without_barge_in():
    s, events = make(["yes"])
    s.start()
    assert s.on_audio(tone(400)) == [] and not events


def test_barge_in_clears_playback():
    s, events = make(["yes"], barge_in=True)
    s.start()
    out = s.on_audio(tone(400))                  # caller talks over the greeting (500 ms)
    out += s.on_audio(quiet(900))
    assert isinstance(out[0], Clear) and events[0].text == "yes"


def test_no_events_after_hangup():
    s, events = make(["yes"])
    s.start(); speak(s)
    assert s.on_audio(tone(400) + quiet(900)) == [] and len(events) == 1


def _stt_client(handler):
    return ElevenLabsClient("key", voice_id="v", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_elevenlabs_transcriber_bytes_and_failure():
    seen = {}

    def ok(req):
        seen["key"] = req.headers["xi-api-key"]
        return httpx.Response(200, json={"text": " yes "})
    assert ElevenLabsTranscriber(_stt_client(ok)).transcribe_bytes(b"x") == "yes" and seen["key"] == "key"
    with pytest.raises(TranscriptionUnavailable):
        ElevenLabsTranscriber(_stt_client(lambda r: httpx.Response(429))).transcribe_bytes(b"x")


def test_elevenlabs_transcriber_missing_file():
    with pytest.raises(TranscriptionUnavailable):
        ElevenLabsTranscriber(_stt_client(lambda r: httpx.Response(200, json={}))).transcribe("nope.wav")
