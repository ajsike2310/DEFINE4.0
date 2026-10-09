import pytest
from sqlalchemy import create_engine, text

from member2.backend.app.main import create_app


def test_old_schema_database_fails_with_clear_message(tmp_path):
    url = f"sqlite:///{(tmp_path / 'old.db').as_posix()}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE campaigns (id INTEGER PRIMARY KEY, name TEXT)"))
    eng.dispose()
    with pytest.raises(RuntimeError, match="older version"):
        create_app(url)
