"""
SQLAlchemy session and engine management.

FastAPI usage (Day 4):
    from db.session import get_db

    @app.get("/products")
    def list_products(db: Session = Depends(get_db)):
        ...

Usage in scripts/tests:
    from db.session import SessionLocal, engine
    from db.models import Base

    Base.metadata.create_all(engine)   # creates tables
    with SessionLocal() as db:
        ...
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

from config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────

def _make_engine():
    db_url = settings.database_url
    kwargs = {
        "echo": False,          # True to see all queries in console
        "pool_pre_ping": True,  # Verify connection before use
    }

    if db_url.startswith("sqlite"):
        # SQLite needs check_same_thread=False for FastAPI
        kwargs["connect_args"] = {"check_same_thread": False}
        # Simple pool for SQLite
        kwargs["pool_size"] = 1 if "memory" in db_url else 5
    else:
        # PostgreSQL: connection pool
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_timeout"] = 30

    engine = create_engine(db_url, **kwargs)

    # SQLite: enable WAL mode and foreign keys
    if db_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    logger.info(f"[db] Engine created: {db_url.split('?')[0]}")
    return engine


engine = _make_engine()

# ── Session factory ───────────────────────────────────────────────────────────

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # avoids lazy queries post-commit
)


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency — injects a DB session per request.

        @app.get("/products")
        def list(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Context manager para scripts ──────────────────────────────────────────────

@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context manager for use outside FastAPI (scripts, jobs, tests).

        with db_session() as db:
            products = db.query(Product).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Utilities ─────────────────────────────────────────────────────────────────

def ping() -> bool:
    """Verifies that the DB is accessible."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error(f"[db] ping failed: {exc}")
        return False
