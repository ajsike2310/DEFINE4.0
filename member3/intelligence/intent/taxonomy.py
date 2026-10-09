from enum import Enum


class Intent(str, Enum):
    CONFIRM = "confirm"
    DECLINE = "decline"
    CALLBACK = "callback_requested"
    INFO = "information_requested"
    ACK = "acknowledgement"
    OPT_OUT = "opt_out"
    UNCLEAR = "unclear"
    HUMAN = "human_required"


class NextAction(str, Enum):
    RECORD_OUTCOME = "record_outcome"
    CREATE_FOLLOWUP = "create_followup"
    CLARIFY = "ask_clarification"
    HUMAN_REVIEW = "human_review"
    SUPPRESS_CONTACT = "suppress_contact"
    SEND_INFO = "send_information"


# Keypad mapping used by the demo provider and the IVR prompt text.
DTMF_MAP = {"1": Intent.CONFIRM, "2": Intent.DECLINE, "3": Intent.CALLBACK,
            "4": Intent.INFO, "9": Intent.OPT_OUT}
