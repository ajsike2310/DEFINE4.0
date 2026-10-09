"""Hindi and Tamil tests. All phrases are SYNTHETIC and NOT native-reviewed; passing them says nothing about real-world
accuracy. They pin down the matching mechanics (spelling variants, whole-word vs substring, hedges, conflicts)."""
import pytest

from member3.intelligence.intent.taxonomy import Intent
from member3.intelligence.language.detect import detect_language
from member3.intelligence.language.normalize import normalize_text
from member3.intelligence.pipeline import ResponseInput, process_response
from member3.intelligence.policies.closing_lines import CLARIFY_LINE, LINES, REPROMPT_LINE, closing_line
from member3.intelligence.policies.next_action import info_topic

C, D, CB, I, O, U = (Intent.CONFIRM, Intent.DECLINE, Intent.CALLBACK, Intent.INFO, Intent.OPT_OUT, Intent.UNCLEAR)

CASES = [
    # Hindi
    ("हाँ, मैं आऊँगा।", C), ("जी हां", C), ("ठीक है", C), ("ज़रूर आऊँगी", C), ("बिल्कुल", C), ("haan main aaunga", C),
    ("नहीं, मैं नहीं आ सकता।", D), ("नहीं आऊँगा", D), ("जी नहीं", D), ("मुझे रुचि नहीं है", D), ("nahi aa sakta", D),
    ("बाद में फोन करना", CB), ("अभी बात नहीं कर सकता", CB), ("मैं अभी व्यस्त हूँ", CB), ("abhi busy hoon", CB),
    ("कार्यक्रम कहाँ है?", I), ("कितने बजे है", I), ("कब है", I),
    ("फोन मत करो", O), ("मेरा नंबर हटा दो", O), ("दोबारा कॉल मत करना", O),
    ("शायद", U), ("पता नहीं", U), ("मैं देखता हूँ", U), ("हाँ लेकिन नहीं", U),
    # Tamil
    ("ஆமாம், நான் வருவேன்", C), ("கண்டிப்பாக", C), ("சரி", C),
    ("இல்லை, நான் வரமாட்டேன்", D), ("வர முடியாது", D), ("வேண்டாம்", D),
    ("பிறகு அழைக்கவும்", CB), ("இப்போ பேச முடியாது", CB),
    ("எங்கே நடக்கிறது", I), ("எப்போது நடக்கும்", I),
    ("கூப்பிடாதீங்க", O), ("அழைக்க வேண்டாம்", O),
    ("பார்க்கலாம்", U), ("தெரியாது", U), ("ஒருவேளை வருவேன்", U),
]


@pytest.mark.parametrize("text,expected", CASES, ids=[t[:24] for t, _ in CASES])
def test_hindi_and_tamil_intents(text, expected):
    assert process_response(ResponseInput(text=text)).intent == expected


def test_spelling_variants_collapse_and_danda_is_punctuation():
    assert normalize_text("हाँ") == normalize_text("हां")
    assert normalize_text("ज़रूर") == normalize_text("जरूर")
    assert normalize_text("हाँ, मैं आऊँगा।") == "हां मैं आऊंगा"
    assert normalize_text("நான் வருவேன்") == "நான் வருவேன்"          # vowel signs survive


def test_language_detection_by_script():
    assert detect_language("हाँ") == "hi" and detect_language("வருவேன்") == "ta" and detect_language("അതെ") == "ml"
    assert detect_language("yes") == "en" and detect_language("ठीक है, I will come") == "mixed"
    assert detect_language("123 ...") == "unknown"


def test_short_hindi_words_do_not_match_inside_longer_words():
    # "कब" (when) must not fire inside "कबूल", and "ना" is deliberately not a phrase.
    assert process_response(ResponseInput(text="कबूल")).intent == U


def test_tamil_prefixes_that_start_other_words_do_not_trigger_info():
    assert process_response(ResponseInput(text="எங்கள் நண்பர்கள்")).intent == U      # "our friends", not "where"
    assert process_response(ResponseInput(text="எப்படி இருக்கிறீர்கள்")).intent == U   # "how are you", not "when"


def test_conflicts_and_hedges_never_confirm():
    assert process_response(ResponseInput(text="ठीक है, नहीं आ सकता")).intent == U
    assert process_response(ResponseInput(text="சரி, வரமாட்டேன்")).intent == U
    assert process_response(ResponseInput(text="पक्का नहीं")).intent == U           # "not sure": hedge beats "पक्का"


def test_info_topic_in_hindi_and_tamil():
    assert info_topic(normalize_text("कार्यक्रम कहाँ है")) == "venue"
    assert info_topic(normalize_text("कितने बजे है")) == "schedule"
    assert info_topic(normalize_text("எங்கே நடக்கிறது")) == "venue"
    assert info_topic(normalize_text("எப்போது நடக்கும்")) == "schedule"


def test_every_intent_has_a_line_in_all_four_languages():
    for intent, by_lang in LINES.items():
        assert {"en", "ml", "hi", "ta"} <= set(by_lang), intent
    for table in (CLARIFY_LINE, REPROMPT_LINE):
        assert {"en", "ml", "hi", "ta"} <= set(table)


def test_approved_answer_uses_the_language_specific_ending():
    assert closing_line("information_requested", "hi", "कार्यक्रम का स्थान मुख्य सभागार है") == \
        "कार्यक्रम का स्थान मुख्य सभागार है। अलविदा।"
    assert closing_line("information_requested", "ta", "x").endswith("வணக்கம்.")
    assert closing_line("information_requested", "xx", "x") == "x. Goodbye."          # unknown language -> English


@pytest.mark.parametrize("text,expected", [
    ("बाद में phone करना", CB),                    # mixed script, as Scribe actually returned it
    ("बाद में फोन करना", CB),                      # same sentence fully in Devanagari
    ("कृपया दोबारा phone मत करना", O),
    ("मेरा number हटा दो", O),
    ("अभी busy हूँ", CB),
    ("பிறகு call பண்ணுங்க", CB),
    ("இனி அயக்க வேண்டாம்", O),                     # opt-out with a misheard verb, as Scribe returned it
    ("இனி வேண்டாம்", O),
])
def test_mixed_script_and_garbled_optout_from_real_scribe_output(text, expected):
    assert process_response(ResponseInput(text=text)).intent == expected


def test_plain_vendam_is_still_a_decline_not_an_optout():
    assert process_response(ResponseInput(text="வேண்டாம்")).intent == D
