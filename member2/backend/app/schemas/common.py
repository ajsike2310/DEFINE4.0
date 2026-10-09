"""Shared validation helpers and constants."""
import re

from pydantic import BaseModel, ConfigDict

from ..models.enums import Purpose, values

SUPPORTED_LANGUAGES = {"en": "English", "ml": "Malayalam"}
PURPOSES = set(values(Purpose))          # one list: the database CHECK is built from the same enum
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(raw: str) -> str:
    cleaned = re.sub(r"[\s\-().]", "", raw or "")
    if not E164.match(cleaned):
        raise ValueError("phone must be E.164, e.g. +919876543210")
    return cleaned


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)
