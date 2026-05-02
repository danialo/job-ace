from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def init_db() -> None:
    from backend.models import models  # noqa: F401 - ensure models import

    Base.metadata.create_all(bind=engine)
    _migrate(engine)


def _migrate(eng) -> None:
    """Add columns that may be missing from older databases."""
    from sqlalchemy import inspect, text

    inspector = inspect(eng)
    if "resume_block" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("resume_block")}
    new_columns = {
        "job_title": "VARCHAR",
        "company": "VARCHAR",
        "start_date": "VARCHAR",
        "end_date": "VARCHAR",
    }

    with eng.begin() as conn:
        for col_name, col_type in new_columns.items():
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE resume_block ADD COLUMN {col_name} {col_type}"))



@contextmanager
def get_session() -> Session:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    with get_session() as session:
        yield session
