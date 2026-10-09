from sqlalchemy import text
from sqlalchemy.orm import Session


def ping(db: Session) -> None:
    """Raises if the database cannot answer a trivial query."""
    db.execute(text("SELECT 1"))
