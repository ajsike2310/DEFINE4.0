"""Global opt-out: when a person says stop (or consent is revoked) every other record of that phone number inside the
same scope stops being contactable too. Opt-out always wins.

Scope: everything in the same event always counts. Real data (not sample/simulated) is also organisation-wide across
events; sample data stays inside its own event so the sample events never affect each other.
"""
from collections.abc import Iterable

from sqlalchemy.orm import Session

from ..models import Recipient
from ..repositories import campaigns as campaigns_repo
from ..repositories import followups as followups_repo
from ..repositories import leads as leads_repo
from ..repositories import recipients as recipients_repo

SUPPRESSED_REASON = "this number opted out of calls earlier and cannot be added again"


def find_suppressed(db: Session, phones: Iterable[str], *, event_id: int, is_demo: bool) -> set[str]:
    """Which of these numbers opted out (or had consent revoked) anywhere in scope."""
    wanted = set(phones)
    return (recipients_repo.opted_out_phones(db, wanted, event_id=event_id, is_demo=is_demo)
            | leads_repo.revoked_phones(db, wanted, event_id=event_id, is_demo=is_demo))


def is_suppressed(db: Session, phone: str, *, event_id: int, is_demo: bool) -> bool:
    return phone in find_suppressed(db, [phone], event_id=event_id, is_demo=is_demo)


def record_opt_out(db: Session, rec: Recipient) -> dict:
    """Apply an opt-out of `rec` to everything else in scope: other participant rows with the same number become opted
    out (their open follow-ups are cancelled) and matching leads get consent revoked. Caller commits."""
    camp = campaigns_repo.get(db, rec.campaign_id)
    others = recipients_repo.still_contactable_with_phone(db, rec.phone, exclude_id=rec.id, event_id=camp.event_id,
                                                          is_demo=camp.is_demo)
    for o in others:
        o.opted_out, o.consent_status, o.outcome = True, "revoked", "opted_out"
        for fu in followups_repo.open_for_recipient(db, o.id):
            fu.status, fu.note = "cancelled", "recipient opted out"
    leads = leads_repo.with_consent_not_revoked(db, rec.phone, event_id=camp.event_id, is_demo=camp.is_demo)
    for lead in leads:
        lead.consent_status = "revoked"
        if lead.status != "converted":
            lead.status = "lost"
    return {"participants": len(others), "leads": len(leads)}
