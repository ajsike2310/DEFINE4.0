"""Helpers shared by the model modules."""
from enum import StrEnum

from sqlalchemy import CheckConstraint, text

from .enums import values

PHONE_CHECK = "length(phone) BETWEEN 9 AND 16 AND substr(phone, 1, 1) = '+'"     # E.164: + and 8-15 digits


def one_of(column: str, enum: type[StrEnum], name: str | None = None) -> CheckConstraint:
    """CHECK (column IN (...)) generated from an enum, so the database and the code can never disagree."""
    listed = ", ".join(f"'{v}'" for v in values(enum))
    return CheckConstraint(f"{column} IN ({listed})", name=name or column)


def now_default():
    return text("CURRENT_TIMESTAMP")


def false_default():
    return text("0")
