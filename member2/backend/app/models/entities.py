"""Compatibility import path; the models now live in events.py, calling.py and leads.py."""
from . import (CallAttempt, Campaign, Event, FollowUp, ImportRun, IntentResult, Lead,  # noqa: F401
               ProviderEvent, Recipient)
