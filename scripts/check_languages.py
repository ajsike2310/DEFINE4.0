"""Check each language through the real pipeline: speak (TTS) -> listen (Scribe) -> understand (intent rules).

    python -m scripts.check_languages              # built-in sentences
    python -m scripts.check_languages "sentence" confirm    # your own sentence + the intent it should give

For every sentence it synthesises the speech with the configured voice model, transcribes that audio with the configured
Scribe model, classifies the transcript, and saves the audio to scripts/_lang_check/ so you can listen to it.
Caveat: the audio is a clean synthetic voice, so this is an OPTIMISTIC test of listening. Real accents on a phone line
are harder; for that, call yourself with LIVE_LOG_TRANSCRIPT=1 in .env (dev only) and read the transcript in the log.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from member3.integrations.base import ProviderError
from member3.integrations.elevenlabs.client import ElevenLabsClient
from member3.intelligence.pipeline import ResponseInput, process_response
from member3.live.audio import pcm16_to_wav

load_dotenv()                      # a variable set in the shell wins, so you can try another model for one run

CASES = [  # (language, sentence, expected intent)
    ("English", "Yes, I will come.", "confirm"),
    ("English", "Sorry, I can't make it.", "decline"),
    ("English", "Please call me later.", "callback_requested"),
    ("Malayalam", "അതെ, ഞാൻ വരാം.", "confirm"),
    ("Malayalam", "ഇല്ല, എനിക്ക് വരാൻ പറ്റില്ല.", "decline"),
    ("Malayalam", "പിന്നീട് വിളിക്കൂ.", "callback_requested"),
    ("Hindi", "हाँ, मैं आऊँगा।", "confirm"),
    ("Hindi", "नहीं, मैं नहीं आ सकता।", "decline"),
    ("Hindi", "बाद में फोन करना।", "callback_requested"),
    ("Hindi", "कार्यक्रम कहाँ है?", "information_requested"),
    ("Hindi", "कृपया दोबारा फोन मत करना।", "opt_out"),
    ("Tamil", "ஆமாம், நான் வருவேன்.", "confirm"),
    ("Tamil", "இல்லை, நான் வரமாட்டேன்.", "decline"),
    ("Tamil", "பிறகு அழைக்கவும்.", "callback_requested"),
    ("Tamil", "நிகழ்ச்சி எங்கே நடக்கிறது?", "information_requested"),
    ("Tamil", "இனி அழைக்க வேண்டாம்.", "opt_out"),
]

if len(sys.argv) == 3:
    CASES = [("Custom", sys.argv[1], sys.argv[2])]

key, voice = os.getenv("ELEVENLABS_API_KEY", ""), os.getenv("ELEVENLABS_VOICE_ID", "")
if not key or not voice:
    sys.exit("Missing ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID in .env")
client = ElevenLabsClient(key, voice_id=voice, tts_model=os.getenv("ELEVENLABS_TTS_MODEL") or "eleven_multilingual_v2",
                          stt_model=os.getenv("ELEVENLABS_STT_MODEL") or "scribe_v2")
out_dir = Path(__file__).parent / "_lang_check"
out_dir.mkdir(exist_ok=True)
print(f"voice model={client.tts_model}   listening model={client.stt_model}\n")

ok = 0
for i, (lang, said, expected) in enumerate(CASES, 1):
    try:
        pcm = client.speak_pcm(said, 8000)
    except ProviderError as exc:
        print(f"{i}. [{lang}] VOICE FAILED: {exc}")
        continue
    wav = pcm16_to_wav(pcm, 8000)
    (out_dir / f"{i}_{lang.lower()}.wav").write_bytes(wav)
    try:
        heard = client.transcribe(wav, "x.wav", "audio/wav")
    except ProviderError as exc:
        print(f"{i}. [{lang}] LISTEN FAILED: {exc}")
        continue
    d = process_response(ResponseInput(text=heard))
    good = d.intent.value == expected
    ok += good
    print(f"{i}. [{lang}] said: {said}\n     heard: {heard}\n     intent: {d.intent.value} (expected {expected}) "
          f"{'OK' if good else 'MISMATCH'}\n")
print(f"{ok}/{len(CASES)} gave the expected intent. Audio saved in scripts/_lang_check/ (play it to judge the voice).")
