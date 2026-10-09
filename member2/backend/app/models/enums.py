"""Closed vocabularies. The single source of truth: models build their CHECK constraints from these, schemas
validate against them, and a test keeps the state machines in step.

Deliberately NOT here (owned by other members, so the database must not reject their additions):
provider names, `next_action` values and the language list.
"""
from enum import StrEnum


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Purpose(StrEnum):
    ATTENDANCE_CONFIRMATION = "attendance_confirmation"
    EVENT_ANNOUNCEMENT = "event_announcement"
    SCHEDULE_VENUE_UPDATE = "schedule_venue_update"
    SUBMISSION_DEADLINE_REMINDER = "submission_deadline_reminder"
    PARTICIPANT_FOLLOWUP = "participant_followup"


class Consent(StrEnum):
    GRANTED = "granted"
    UNKNOWN = "unknown"
    REVOKED = "revoked"


class Outcome(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ACKNOWLEDGED = "acknowledged"
    DECLINED = "declined"
    CALLBACK_REQUESTED = "callback_requested"
    INFORMATION_REQUESTED = "information_requested"
    UNCLEAR = "unclear"
    HUMAN_REQUIRED = "human_required"
    OPTED_OUT = "opted_out"
    NO_RESPONSE = "no_response"


class CallStatus(StrEnum):
    QUEUED = "queued"
    INITIATING = "initiating"
    RINGING = "ringing"
    ANSWERED = "answered"
    COMPLETED = "completed"
    FAILED = "failed"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    CANCELLED = "cancelled"


class CallMode(StrEnum):
    MAIN = "main"
    CLARIFY = "clarify"


class EventKind(StrEnum):
    STATUS = "status"
    RESPONSE = "response"


class Intent(StrEnum):
    CONFIRM = "confirm"
    DECLINE = "decline"
    CALLBACK_REQUESTED = "callback_requested"
    INFORMATION_REQUESTED = "information_requested"
    ACKNOWLEDGEMENT = "acknowledgement"
    OPT_OUT = "opt_out"
    UNCLEAR = "unclear"
    HUMAN_REQUIRED = "human_required"


class IntentMethod(StrEnum):
    DTMF = "dtmf"
    RULES = "rules"
    NONE = "none"


class FollowUpAction(StrEnum):
    CALLBACK = "callback"
    HUMAN_REVIEW = "human_review"
    SEND_INFORMATION = "send_information"
    CLARIFICATION = "clarification"


class FollowUpStatus(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"


class LeadSource(StrEnum):
    REGISTRATION_FORM = "registration_form"
    CSV_IMPORT = "csv_import"
    MANUAL = "manual"
    REFERRAL = "referral"
    WALK_IN = "walk_in"


class ImportKind(StrEnum):
    PARTICIPANTS = "participants"
    LEADS = "leads"


def values(enum: type[StrEnum]) -> tuple[str, ...]:
    return tuple(e.value for e in enum)
