"""
Gestión de la sesión y engine de SQLAlchemy.

Uso en FastAPI (Día 4):
    from db.session import get_db

    @app.get("/products")
    def list_products(db: Session = Depends(get_db)):
        ...

Uso en scripts/tests:
    from db.session import SessionLocal, engine
    from db.models import Base

    Base.metadata.create_all(engine)   # crea tablas
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
        "echo": False,          # True para ver todas las queries en consola
        "pool_pre_ping": True,  # Verifica conexión antes de usarla
    }

    if db_url.startswith("sqlite"):
        # SQLite necesita check_same_thread=False para FastAPI
        kwargs["connect_args"] = {"check_same_thread": False}
        # Pool simple para SQLite
        kwargs["pool_size"] = 1 if "memory" in db_url else 5
    else:
        # PostgreSQL: connection pool
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_timeout"] = 30

    engine = create_engine(db_url, **kwargs)

    # SQLite: habilitar WAL mode y foreign keys
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
    expire_on_commit=False,  # evita queries lazy post-commit
)


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency — inyecta una sesión de DB por request.

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
    Context manager para uso fuera de FastAPI (scripts, jobs, tests).

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
    """Verifica que la DB esté accesible."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error(f"[db] ping failed: {exc}")
        return False
