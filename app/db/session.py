"""Engine and session factory (lazy init)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import ROOT_DIR, get_settings

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            # ensure parent dir exists for sqlite:///./data/brief.db
            if ":///" in url:
                raw_path = url.split(":///", 1)[1]
                db_path = Path(raw_path)
                if not db_path.is_absolute():
                    db_path = ROOT_DIR / db_path
                db_path.parent.mkdir(parents=True, exist_ok=True)
                url = f"sqlite:///{db_path.as_posix()}"
            kwargs["connect_args"] = {"check_same_thread": False}
            _engine = create_engine(url, **kwargs)

            @event.listens_for(_engine, "connect")
            def _fk_pragma(dbapi_conn, _):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        else:
            kwargs["pool_pre_ping"] = True
            _engine = create_engine(url, **kwargs)

        _SessionLocal = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, future=True
        )
    return _engine


def SessionLocal() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


class _EngineProxy:
    def __getattr__(self, name: str):
        return getattr(get_engine(), name)


engine = _EngineProxy()


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Clear cached engine (after .env change)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
