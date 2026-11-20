"""Base connector, NormalizedItem, shared HTTP helpers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from loguru import logger
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings


class NormalizedItem(BaseModel):
    source_key: str
    external_id: str
    item_type: str
    title: str
    url: str
    description: str = ""
    authors: list[Any] = Field(default_factory=list)
    organization: Optional[str] = None
    published_at: Optional[datetime] = None
    metrics: dict[str, float] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    def ensure_utc(self) -> NormalizedItem:
        if self.published_at and self.published_at.tzinfo is None:
            self.published_at = self.published_at.replace(tzinfo=timezone.utc)
        elif self.published_at:
            self.published_at = self.published_at.astimezone(timezone.utc)
        return self


def canonicalize_url(url: str) -> str:
    """Normalize URL: drop utm_*, trailing slash; arxiv/github shortcuts."""
    if not url:
        return ""
    url = url.strip()
    # arxiv abs/pdf → abs
    m = re.match(
        r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/([0-9]+\.[0-9]+)(?:v\d+)?(?:\.pdf)?",
        url,
        re.I,
    )
    if m:
        return f"https://arxiv.org/abs/{m.group(1)}"

    # github → github.com/owner/repo
    gm = re.match(
        r"https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)",
        url,
        re.I,
    )
    if gm:
        owner, repo = gm.group(1), gm.group(2).removesuffix(".git")
        return f"https://github.com/{owner}/{repo}"

    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=False)
    cleaned = {k: v for k, v in qs.items() if not k.lower().startswith("utm_")}
    query = urlencode({k: v[0] if len(v) == 1 else v for k, v in cleaned.items()}, doseq=True)
    path = parsed.path.rstrip("/") or ""
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", query, ""))


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class HttpClient:
    """Shared httpx client with retry."""

    def __init__(self, user_agent: str, timeout: float = 20.0):
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    @retry(
        retry=retry_if_exception(_should_retry),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        resp = self.client.get(url, **kwargs)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                logger.warning("429 Retry-After={} for {}", retry_after, url)
            resp.raise_for_status()
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp


class BaseConnector(ABC):
    key: str = ""
    item_type: str = ""

    def __init__(self, settings: Settings, source_cfg: dict[str, Any]):
        self.settings = settings
        self.source_cfg = source_cfg
        self.params = source_cfg.get("params") or {}
        self.http = HttpClient(settings.user_agent)

    def close(self) -> None:
        self.http.close()

    @abstractmethod
    def fetch(self, target_date: date) -> list[NormalizedItem]:
        """Fetch items for target_date (UTC-aware published_at)."""

    def safe_fetch(self, target_date: date) -> list[NormalizedItem]:
        try:
            items = self.fetch(target_date)
            return [i.ensure_utc() for i in items]
        except Exception as exc:
            logger.exception("Connector {} failed: {}", self.key, exc)
            raise
        finally:
            self.close()
