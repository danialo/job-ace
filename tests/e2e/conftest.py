"""E2E test fixtures: launches a test server with an isolated DB."""
from __future__ import annotations

import threading
import time

import pytest
import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.app import app
from backend.db.session import Base, get_db
from backend.models import models  # noqa: F401

TEST_PORT = 3099


class TestServer:
    """Runs uvicorn in a background thread for E2E tests."""

    def __init__(self, app, host="127.0.0.1", port=TEST_PORT):
        self.config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        # Wait for server to be ready
        for _ in range(50):
            if self.server.started:
                break
            time.sleep(0.1)
        if not self.server.started:
            raise RuntimeError("Test server failed to start")

    def stop(self):
        self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=5)


@pytest.fixture(scope="session")
def _test_db():
    """Create a shared in-memory DB for all E2E tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield engine, SessionLocal
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def live_server(_test_db):
    """Start a live test server for Playwright to connect to."""
    from unittest.mock import patch

    with patch("backend.api.app.init_db"):
        server = TestServer(app, port=TEST_PORT)
        server.start()
        yield f"http://127.0.0.1:{TEST_PORT}"
        server.stop()


@pytest.fixture()
def e2e_session(_test_db):
    """Return a session for seeding test data."""
    _, SessionLocal = _test_db
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
