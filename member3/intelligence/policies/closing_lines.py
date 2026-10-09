"""What the agent says after a reply in a browser demo call.

Fixed, reviewable lines chosen by the classified intent. Nothing is generated: the agent never improvises, never
promises more than the system will do, and answers a question only with text the organiser approved.
Malayalam, Hindi and Tamil lines have not been reviewed by a native speaker (see docs/KNOWN_ISSUES.md).
"""

LINES: dict[str, dict[str, str]] = {
    "confirm": {"en": "Thank you. We have noted that you will attend. Goodbye.",
                "ml": "നന്ദി. നിങ്ങൾ പങ്കെടുക്കുമെന്ന് ഞങ്ങൾ രേഖപ്പെടുത്തി. വിട.",
                "hi": "धन्यवाद। हमने नोट कर लिया है कि आप शामिल होंगे। अलविदा।",
                "ta": "நன்றி. நீங்கள் கலந்துகொள்வதை பதிவு செய்துவிட்டோம். வணக்கம்."},
    "decline": {"en": "Understood, thank you for letting us know. Goodbye.",
                "ml": "ശരി, അറിയിച്ചതിന് നന്ദി. വിട.",
                "hi": "ठीक है, बताने के लिए धन्यवाद। अलविदा।",
                "ta": "சரி, தெரிவித்ததற்கு நன்றி. வணக்கம்."},
    "acknowledgement": {"en": "Thank you. Goodbye.", "ml": "നന്ദി. വിട.",
                        "hi": "धन्यवाद। अलविदा।", "ta": "நன்றி. வணக்கம்."},
    "callback_requested": {"en": "Understood. We will call you back later. Goodbye.",
                           "ml": "ശരി. ഞങ്ങൾ പിന്നീട് വിളിക്കാം. വിട.",
                           "hi": "ठीक है। हम आपको बाद में फिर से कॉल करेंगे। अलविदा।",
                           "ta": "சரி. நாங்கள் உங்களை பிறகு மீண்டும் அழைக்கிறோம். வணக்கம்."},
    "opt_out": {"en": "Understood. We will not call you again. Goodbye.",
                "ml": "ശരി. ഇനി ഞങ്ങൾ വിളിക്കില്ല. വിട.",
                "hi": "ठीक है। हम आपको दोबारा कॉल नहीं करेंगे। अलविदा।",
                "ta": "சரி. இனி உங்களை அழைக்க மாட்டோம். வணக்கம்."},
    "information_requested": {"en": "Thank you for asking. A team member will get back to you with that. Goodbye.",
                              "ml": "ചോദിച്ചതിന് നന്ദി. ഞങ്ങളുടെ ടീം അംഗം നിങ്ങളെ ബന്ധപ്പെടും. വിട.",
                              "hi": "पूछने के लिए धन्यवाद। हमारी टीम का कोई सदस्य आपसे संपर्क करेगा। अलविदा।",
                              "ta": "கேட்டதற்கு நன்றி. எங்கள் குழுவினர் உங்களைத் தொடர்புகொள்வார்கள். வணக்கம்."},
    "unclear": {"en": "Thank you. A team member will follow up with you personally. Goodbye.",
                "ml": "നന്ദി. ഞങ്ങളുടെ ടീം അംഗം നിങ്ങളെ നേരിട്ട് ബന്ധപ്പെടും. വിട.",
                "hi": "धन्यवाद। हमारी टीम का कोई सदस्य आपसे व्यक्तिगत रूप से संपर्क करेगा। अलविदा।",
                "ta": "நன்றி. எங்கள் குழுவினர் உங்களை நேரடியாகத் தொடர்புகொள்வார்கள். வணக்கம்."},
    "human_required": {"en": "Thank you. A team member will follow up with you personally. Goodbye.",
                       "ml": "നന്ദി. ഞങ്ങളുടെ ടീം അംഗം നിങ്ങളെ നേരിട്ട് ബന്ധപ്പെടും. വിട.",
                       "hi": "धन्यवाद। हमारी टीम का कोई सदस्य आपसे व्यक्तिगत रूप से संपर्क करेगा। अलविदा।",
                       "ta": "நன்றி. எங்கள் குழுவினர் உங்களை நேரடியாகத் தொடர்புகொள்வார்கள். வணக்கம்."},
}


# Mid-call prompts for the live conversation (same rules: fixed text, Malayalam not native-reviewed).
CLARIFY_LINE = {"en": "Sorry, I want to be sure. Will you attend the event? Please say yes or no.",
                "ml": "ക്ഷമിക്കണം, ഉറപ്പാക്കാൻ ചോദിക്കുകയാണ്. നിങ്ങൾ പങ്കെടുക്കുമോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
                "hi": "माफ़ कीजिए, पक्का करने के लिए पूछ रहे हैं। क्या आप कार्यक्रम में शामिल होंगे? कृपया हाँ या ना कहें।",
                "ta": "மன்னிக்கவும், உறுதிப்படுத்திக்கொள்ள கேட்கிறோம். நீங்கள் நிகழ்ச்சியில் கலந்துகொள்வீர்களா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்."}
REPROMPT_LINE = {"en": "Sorry, I did not catch that. Will you be attending the event?",
                 "ml": "ക്ഷമിക്കണം, കേൾക്കാൻ കഴിഞ്ഞില്ല. നിങ്ങൾ പങ്കെടുക്കുമോ?",
                 "hi": "माफ़ कीजिए, आवाज़ साफ़ नहीं सुनाई दी। क्या आप कार्यक्रम में शामिल होंगे?",
                 "ta": "மன்னிக்கவும், உங்கள் குரல் தெளிவாகக் கேட்கவில்லை. நீங்கள் நிகழ்ச்சியில் கலந்துகொள்வீர்களா?"}


def prompt_line(table: dict[str, str], language: str) -> str:
    return table.get(language) or table["en"]


_TAIL = {"en": (".", " Goodbye."), "ml": (".", " വിട."), "hi": ("।", " अलविदा।"), "ta": (".", " வணக்கம்.")}


def closing_line(intent: str, language: str, approved_answer: str | None = None) -> str:
    """Line spoken at the end. An information question is answered only when an approved answer exists."""
    if intent == "information_requested" and approved_answer:
        stop, tail = _TAIL.get(language, _TAIL["en"])
        return approved_answer.strip().rstrip(".।") + stop + tail
    by_lang = LINES.get(intent) or LINES["unclear"]
    return by_lang.get(language) or by_lang["en"]
