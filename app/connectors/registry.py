"""Connector registry."""

from __future__ import annotations

from typing import Type

from app.config import Settings, load_yaml
from app.connectors.arxiv import ArxivConnector
from app.connectors.base import BaseConnector
from app.connectors.github_search import GitHubSearchConnector
from app.connectors.github_trending import GitHubTrendingConnector
from app.connectors.hackernews import HackerNewsConnector
from app.connectors.hf_models import HFModelsConnector
from app.connectors.hf_papers import HFPapersConnector
from app.connectors.hf_spaces import HFSpacesConnector
from app.connectors.reddit import RedditConnector
from app.connectors.rss import RSSConnector

_REGISTRY: dict[str, Type[BaseConnector]] = {
    "hf_papers": HFPapersConnector,
    "hf_models": HFModelsConnector,
    "hf_spaces": HFSpacesConnector,
    "github_trending": GitHubTrendingConnector,
    "github_search": GitHubSearchConnector,
    "arxiv": ArxivConnector,
    "rss": RSSConnector,
    "hackernews": HackerNewsConnector,
    "reddit": RedditConnector,
}


def list_connectors() -> list[str]:
    return list(_REGISTRY.keys())


def get_connector(key: str, settings: Settings, source_cfg: dict | None = None) -> BaseConnector:
    cls = _REGISTRY[key]
    sources = load_yaml("sources")
    cfg = source_cfg or (sources.get("connectors") or {}).get(key) or {}
    return cls(settings, cfg)


def enabled_connectors(settings: Settings) -> list[BaseConnector]:
    sources = load_yaml("sources")
    connectors_cfg = sources.get("connectors") or {}
    out: list[BaseConnector] = []
    for key, cls in _REGISTRY.items():
        cfg = connectors_cfg.get(key) or {}
        if cfg.get("enabled", True):
            out.append(cls(settings, cfg))
    return out
