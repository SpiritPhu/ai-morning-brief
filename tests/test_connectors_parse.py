import json
from datetime import date
from pathlib import Path

from app.connectors.arxiv import parse_arxiv_feed
from app.connectors.github_trending import parse_trending_html
from app.connectors.hackernews import parse_hn_hits
from app.connectors.hf_models import parse_hf_models_payload
from app.connectors.hf_papers import parse_hf_papers_payload
from app.connectors.reddit import parse_reddit_listing

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 18)


def test_hf_papers_parse():
    data = json.loads((FIX / "hf_papers.json").read_text(encoding="utf-8"))
    items = parse_hf_papers_payload(data, TODAY)
    assert len(items) == 2
    assert items[0].external_id == "2401.12345"
    assert items[0].metrics["upvotes"] == 42


def test_hf_models_parse():
    data = json.loads((FIX / "hf_models.json").read_text(encoding="utf-8"))
    items = parse_hf_models_payload(data, TODAY)
    assert items[0].organization == "Qwen"
    assert items[0].extra["license"] == "apache-2.0"
    assert items[0].metrics["trending_rank"] == 1


def test_hn_parse():
    data = json.loads((FIX / "hn.json").read_text(encoding="utf-8"))
    items = parse_hn_hits(data, TODAY)
    assert items[0].metrics["points"] == 120
    assert "hn_url" in items[0].extra


def test_reddit_skips_stickied():
    data = json.loads((FIX / "reddit.json").read_text(encoding="utf-8"))
    items = parse_reddit_listing(data, "LocalLLaMA", TODAY)
    assert len(items) == 1
    assert items[0].external_id == "LocalLLaMA:abc123"


def test_arxiv_parse():
    xml = (FIX / "arxiv.xml").read_text(encoding="utf-8")
    items = parse_arxiv_feed(xml, TODAY, hours_window=48)
    assert len(items) == 1
    assert items[0].external_id == "2401.11111"


def test_github_trending_ai_filter():
    html = (FIX / "github_trending.html").read_text(encoding="utf-8")
    items = parse_trending_html(html, TODAY)
    assert any(i.external_id == "huggingface/transformers" for i in items)
    assert all("unrelated-css" not in i.external_id for i in items)
