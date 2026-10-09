"""Data & AI quality, computed from stored rows (plus one deterministic check of the rule engine).

Honesty notes (also shown in the UI):
- Integrity checks count violations of rules the code is meant to enforce. 0 means "no violation found in this
  data", not "bug-free".
- AI figures describe how the rule engine behaved on the responses it received. There is no ground truth for real
  calls, so nothing here is an accuracy figure. The phrase check uses a SMALL team-written synthetic set.
- Duplicate provider events are rejected before they are stored, so they cannot be counted here.
"""
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from member2.backend.app.models import (CallAttempt, Campaign, FollowUp, ImportRun, IntentResult, Lead, ProviderEvent,
                                        Recipient)
from member3.intelligence.eval_cases import CASES
from member3.intelligence.intent.taxonomy import Intent
from member3.intelligence.pipeline import ResponseInput, process_response

INTENT_OUTCOMES = {"confirmed", "acknowledged", "declined", "callback_requested", "information_requested",
                   "unclear", "human_required"}
DEFINITE = {"confirm", "decline", "acknowledgement", "callback_requested", "information_requested", "opt_out"}


def _pct(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def phrase_check() -> dict:
    """Run the labelled synthetic phrases through the live pipeline. Deterministic; NOT an accuracy claim."""
    groups: dict[str, dict] = defaultdict(lambda: {"cases": 0, "passed": 0})
    failures, false_confirms = [], 0
    safe_cats = {"ambiguous", "conflict", "empty"}
    for cat, text, expected in CASES:
        got = process_response(ResponseInput(text=text)).intent
        lang = cat.split("-")[0]
        g = groups[lang]
        g["cases"] += 1
        if got == expected:
            g["passed"] += 1
        else:
            failures.append({"category": cat, "text": text, "expected": expected.value, "got": got.value})
        if cat in safe_cats and got == Intent.CONFIRM:
            false_confirms += 1
    total = sum(g["cases"] for g in groups.values())
    passed = sum(g["passed"] for g in groups.values())
    return {"cases": total, "passed": passed, "failures": failures[:20], "false_confirms_on_ambiguous": false_confirms,
            "by_group": [{"group": k, **v} for k, v in sorted(groups.items())],
            "note": "Small synthetic set written by the team. It checks the rules still behave as designed; "
                    "it says nothing about accuracy on real calls."}


def compute(db: Session, event_id: int | None = None, source: str = "all") -> dict:
    cq = select(Campaign)
    if event_id:
        cq = cq.where(Campaign.event_id == event_id)
    campaigns = [c for c in db.scalars(cq) if source == "all" or c.is_demo == (source == "simulated")]
    cids = [c.id for c in campaigns]
    cmap = {c.id: c for c in campaigns}
    recipients = list(db.scalars(select(Recipient).where(Recipient.campaign_id.in_(cids)))) if cids else []
    attempts = list(db.scalars(select(CallAttempt).where(CallAttempt.campaign_id.in_(cids)))) if cids else []
    intents = list(db.scalars(select(IntentResult).where(IntentResult.campaign_id.in_(cids)))) if cids else []
    followups = list(db.scalars(select(FollowUp).where(FollowUp.campaign_id.in_(cids)))) if cids else []

    lq = select(Lead)
    iq = select(ImportRun)
    if event_id:
        lq, iq = lq.where(Lead.event_id == event_id), iq.where(ImportRun.event_id == event_id)
    leads = [l for l in db.scalars(lq) if source == "all" or l.is_demo == (source == "simulated")]
    imports = [i for i in db.scalars(iq) if source == "all" or i.is_demo == (source == "simulated")]
    att_ids = [a.id for a in attempts]
    pevents = list(db.scalars(select(ProviderEvent).where(ProviderEvent.call_attempt_id.in_(att_ids)))) if att_ids else []

    # ---- data gathering -------------------------------------------------------------------------
    n = len(recipients)
    consent = Counter(r.consent_status for r in recipients)
    rows_in = sum(i.rows_total for i in imports)
    imported = sum(i.imported for i in imports)
    reasons: Counter = Counter()
    for i in imports:
        reasons.update(i.reasons or {})
    complete = sum(1 for r in recipients if r.consent_status == "granted" and r.preferred_language)
    gathering = {
        "participants": n,
        "consent": {"granted": consent["granted"], "unknown": consent["unknown"], "revoked": consent["revoked"]},
        "consent_recorded_rate": _pct(consent["granted"] + consent["revoked"], n),   # (granted + revoked) / participants
        "language_known_rate": _pct(sum(1 for r in recipients if r.preferred_language), n),
        "participant_id_rate": _pct(sum(1 for r in recipients if r.external_ref), n),
        "complete_profile_rate": _pct(complete, n),     # consent granted AND language known / participants
        "imports": {"runs": len(imports), "rows": rows_in, "imported": imported, "rejected": rows_in - imported,
                    "acceptance_rate": _pct(imported, rows_in),    # imported / rows received
                    "top_rejections": [{"reason": k, "rows": v} for k, v in reasons.most_common(5)]},
        "leads": {"total": len(leads), "with_email": sum(1 for l in leads if l.email),
                  "consented": sum(1 for l in leads if l.consent_status == "granted"),
                  "sources": dict(Counter(l.source for l in leads))},
    }

    # ---- call data & provider events -------------------------------------------------------------
    terminal = {"completed", "failed", "busy", "no_answer", "voicemail", "cancelled"}
    ev_results = Counter("applied" if e.result == "applied" else "ignored" for e in pevents)
    ignored_reasons = Counter(e.result.split(":", 1)[1] if ":" in e.result else e.result
                              for e in pevents if e.result != "applied")
    calls = {
        "attempts": len(attempts),
        "settled": sum(1 for a in attempts if a.status in terminal),
        "in_flight": sum(1 for a in attempts if a.status not in terminal),
        "provider_events": {"stored": len(pevents), "applied": ev_results["applied"], "ignored": ev_results["ignored"],
                            "ignored_reasons": [{"reason": k, "events": v} for k, v in ignored_reasons.most_common(5)],
                            "note": "Exact duplicates are rejected before storage and are not counted here."},
    }

    # ---- integrity checks (violations should be 0) -----------------------------------------------
    intents_by_attempt = Counter(i.call_attempt_id for i in intents)
    has_intent = {i.recipient_id for i in intents}
    clarify_per = Counter(a.recipient_id for a in attempts if a.mode == "clarify")
    main_per = Counter(a.recipient_id for a in attempts if a.mode == "main")
    rec_by_id = {r.id: r for r in recipients}
    checks = [
        ("outcome_has_response", "Every answer-based outcome traces to a recorded response",
         sum(1 for r in recipients if r.outcome in INTENT_OUTCOMES and r.id not in has_intent), n),
        ("one_response_per_call", "No call has more than one classified response",
         sum(1 for v in intents_by_attempt.values() if v > 1), len(intents_by_attempt)),
        ("optout_wins", "Opted-out people keep the opted-out outcome and revoked consent",
         sum(1 for r in recipients if r.opted_out and (r.outcome != "opted_out" or r.consent_status != "revoked")),
         sum(1 for r in recipients if r.opted_out)),
        ("retries_bounded", "Retries never exceed the campaign limit",
         sum(1 for rid, k in main_per.items() if k > cmap[rec_by_id[rid].campaign_id].max_attempts), len(main_per)),
        ("clarify_once", "Nobody received more than one clarification call",
         sum(1 for v in clarify_per.values() if v > 1), len(clarify_per)),
        ("consent_before_call", "No call to someone without recorded consent (when the campaign requires it)",
         sum(1 for r in recipients if r.attempts and cmap[r.campaign_id].require_consent
             and r.consent_status == "unknown"),
         sum(1 for r in recipients if r.attempts)),
        ("simulated_separate", "Simulated campaigns have no real-provider calls",
         sum(1 for a in attempts if cmap[a.campaign_id].is_demo and not a.is_simulated),
         sum(1 for a in attempts if cmap[a.campaign_id].is_demo)),
        ("lead_links", "Converted leads point at an existing participant",
         sum(1 for l in leads if l.status == "converted" and not (l.recipient_id and db.get(Recipient, l.recipient_id))),
         sum(1 for l in leads if l.status == "converted")),
    ]
    integrity = [{"key": k, "label": label, "violations": v, "checked": d} for k, label, v, d in checks]

    # ---- AI behaviour ------------------------------------------------------------------------------
    total = len(intents)
    by_method = Counter(i.method for i in intents)
    by_intent = Counter(i.intent for i in intents)
    by_lang = Counter(i.detected_language for i in intents)
    scores: dict[str, list[float]] = defaultdict(list)
    for i in intents:
        scores[i.method].append(i.score)
    definite = sum(1 for i in intents if i.intent in DEFINITE and not i.needs_review)
    clar = [a for a in attempts if a.mode == "clarify"]
    resolved_clar = sum(1 for a in clar if any(i.call_attempt_id == a.id and i.intent in ("confirm", "decline")
                                                for i in intents))
    info_q = [f for f in followups if f.action_type in ("send_information",) or
              (f.action_type == "human_review" and f.note.startswith("asked about"))]
    answered_from_approved = sum(1 for f in info_q if f.action_type == "send_information")
    ai = {
        "responses": total,
        "by_method": {"keypad": by_method["dtmf"], "phrase_rules": by_method["rules"], "none": by_method["none"]},
        "by_intent": dict(by_intent),
        "by_language": dict(by_lang),
        "auto_handled_rate": _pct(definite, total),     # definite intent AND not flagged for review / responses
        "unclear_rate": _pct(by_intent["unclear"] + by_intent["human_required"], total),
        "review_rate": _pct(sum(1 for i in intents if i.needs_review), total),
        "clarification": {"attempted": len(clar), "resolved": resolved_clar,
                          "resolution_rate": _pct(resolved_clar, len(clar))},
        "info_questions": {"asked": len(info_q), "answered_from_approved_info": answered_from_approved,
                           "sent_to_a_person": len(info_q) - answered_from_approved},
        "avg_heuristic_score": {k: round(sum(v) / len(v), 3) for k, v in scores.items()},
        "score_note": "Internal heuristic, not a probability.",
        "phrase_check": phrase_check(),
    }
    return {"source": source, "event_id": event_id, "data_gathering": gathering, "calls": calls,
            "integrity": integrity,
            "integrity_summary": {"checks": len(integrity), "clean": sum(1 for c in integrity if c["violations"] == 0)},
            "ai": ai}
