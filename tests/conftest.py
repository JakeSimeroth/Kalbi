"""
Shared pytest fixtures for the KALBI-2 test suite.

Provides an in-memory SQLite database engine and session that can be used
by any test that needs a working database without external dependencies.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.data.models import Base


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine with all KALBI-2 tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Provide a transactional SQLAlchemy session against the in-memory DB."""
    with Session(db_engine) as session:
        yield session
