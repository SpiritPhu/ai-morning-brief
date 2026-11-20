"""Database package."""

from app.db.base import Base

__all__ = ["Base", "SessionLocal", "engine", "get_session"]


def __getattr__(name: str):
    if name in {"SessionLocal", "engine", "get_session"}:
        from app.db import session as sess

        return getattr(sess, name)
    raise AttributeError(name)
