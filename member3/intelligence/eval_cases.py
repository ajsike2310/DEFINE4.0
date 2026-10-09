"""Labelled SYNTHETIC phrases written by the team (not real call data). Shared by the unit tests and the live
"AI check" on the Data & AI page. Passing them says nothing about real-world accuracy."""
from .intent.taxonomy import Intent

CASES = [
    # (category, text, expected)
    ("en-confirm", "Yes, I'll attend.", Intent.CONFIRM),
    ("en-confirm", "okay sure", Intent.CONFIRM),
    ("en-decline", "No, I can't come", Intent.DECLINE),
    ("en-decline", "no thanks", Intent.DECLINE),
    ("en-callback", "I'm busy now. Call me tomorrow.", Intent.CALLBACK),
    ("en-info", "What time is it?", Intent.INFO),
    ("en-optout", "Please stop calling me", Intent.OPT_OUT),
    ("en-optout", "don't call me again", Intent.OPT_OUT),
    ("ml-confirm", "അതെ, വരാം", Intent.CONFIRM),
    ("ml-decline", "വരില്ല", Intent.DECLINE),
    ("ml-callback", "നാളെ വിളിക്കൂ", Intent.CALLBACK),
    ("ml-optout", "ഇനി വിളിക്കരുത്", Intent.OPT_OUT),
    ("manglish-confirm", "athe varam", Intent.CONFIRM),
    ("manglish-decline", "illa, varilla", Intent.DECLINE),
    ("mixed-confirm", "അതെ I will come", Intent.CONFIRM),
    ("mixed-decline", "sorry, വരില്ല", Intent.DECLINE),
    ("en-confirm", "Yes, I'll be there.", Intent.CONFIRM),
    ("en-confirm", "yes thanks", Intent.CONFIRM),
    ("en-callback", "I'm busy. Call me after 5 PM.", Intent.CALLBACK),
    ("en-info", "Where is the venue?", Intent.INFO),
    ("en-ack", "Noted, thank you", Intent.ACK),
    ("en-ack", "got it", Intent.ACK),
    ("ml-ack", "നന്ദി", Intent.ACK),
    ("en-decline", "no thanks", Intent.DECLINE),
    ("ambiguous", "Maybe. I'll see.", Intent.UNCLEAR),
    ("ambiguous", "ഒരുപക്ഷേ", Intent.UNCLEAR),
    ("ambiguous", "hmm what", Intent.UNCLEAR),
    ("conflict", "yes but no", Intent.UNCLEAR),
    ("empty", "", Intent.UNCLEAR),
    ("empty", "   ...  ", Intent.UNCLEAR),
]
