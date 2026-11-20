"""Portable helpers: detect SQLite and embedding column type."""

from __future__ import annotations

from sqlalchemy import JSON, TypeDecorator


def is_sqlite() -> bool:
    from app.config import get_settings

    url = (get_settings().database_url or "").lower()
    return url.startswith("sqlite")


class EmbeddingType(TypeDecorator):
    """JSON list on SQLite; pgvector on Postgres."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 384):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(JSON())
        from pgvector.sqlalchemy import Vector

        return dialect.type_descriptor(Vector(self.dim))
