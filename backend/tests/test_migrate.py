from sqlalchemy import create_engine, inspect, text

from app.db.base import Base
from app.db.migrate import add_missing_columns
from app.models import *  # noqa: F401,F403  (registers every model on Base.metadata)


def test_existing_users_gain_the_two_factor_columns_without_losing_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, "
                "hashed_password VARCHAR(255) NOT NULL, created_at DATETIME)"
            )
        )
        connection.execute(text("INSERT INTO users (id, email, hashed_password) VALUES (1, 'old@example.com', 'x')"))

    add_missing_columns(engine, Base.metadata)

    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert {"totp_secret", "totp_enabled", "totp_last_step", "recovery_code_hashes"} <= columns
    with engine.connect() as connection:
        row = connection.execute(text("SELECT email, totp_enabled FROM users")).one()
    assert row.email == "old@example.com"
    assert not row.totp_enabled


def test_running_it_twice_is_harmless(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)

    add_missing_columns(engine, Base.metadata)
    add_missing_columns(engine, Base.metadata)


def test_existing_findings_gain_the_source_column_defaulting_to_model(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old_findings.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE risk_findings (id INTEGER PRIMARY KEY, clause_id INTEGER NOT NULL, "
                "risk_type VARCHAR(100) NOT NULL, severity VARCHAR(8) NOT NULL, "
                "confidence FLOAT NOT NULL, explanation TEXT NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO risk_findings VALUES (1, 1, 'exclusivity', 'MEDIUM', 0.8, 'why')")
        )

    add_missing_columns(engine, Base.metadata)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT source FROM risk_findings")).scalar_one() == "model"
