# Native-speaker review checklist (Hindi and Tamil)

Everything below was written without a native reviewer. Please check wording, politeness level, gender neutrality
(the agent's voice has no fixed gender, so lines avoid gendered verb forms) and whether a phone caller would actually say it.

| What | Where | What to look for |
|---|---|---|
| Phrases people SAY (confirm, decline, callback, info, opt-out, ack, hedges) | `intelligence/intent/rules_hi_ta.py` | Missing everyday phrasings; phrases that mean something else; words that start longer unrelated words (Tamil is matched as substrings) |
| Goodbyes, clarification question, "didn't catch that" | `intelligence/policies/closing_lines.py` (`hi`, `ta` entries) | Natural, polite, clear on a phone line |
| Greeting and "where / when" answers, month names, parts of the day | `live/campaign.py` (`build_greeting`, `info_answers`, `_MONTHS`, `_DAY_PARTS`) | Sentence flow; "15 नवंबर को सुबह 10 बजे" / "நவம்பர் 15 ஆம் தேதி காலை 10 மணிக்கு" |

Most useful review method: run `python -m scripts.check_languages "<sentence>" <expected_intent>` on sentences real
participants would say, then add the misses to `rules_hi_ta.py` and `intelligence/tests/test_hi_ta.py`.

Known limits: Devanagari is reported as Hindi (Marathi/Nepali speakers would get Hindi lines); Malayalam greetings do
not exist yet (Malayalam campaigns greet in English); the Malayalam voice needs a different ElevenLabs model (see below).
