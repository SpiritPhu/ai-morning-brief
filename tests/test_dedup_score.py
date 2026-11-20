from datetime import date, datetime, timezone
from types import SimpleNamespace

import numpy as np

from app.pipeline.dedup import UnionFind, cluster_items
from app.pipeline.score import freshness_score, percentile_rank


def test_union_find():
    uf = UnionFind(4)
    uf.union(0, 1)
    uf.union(2, 3)
    assert uf.find(0) == uf.find(1)
    assert uf.find(0) != uf.find(2)


def _item(i, source, url, arxiv=None, gh=None, emb=None):
    return SimpleNamespace(
        id=i,
        source_key=source,
        canonical_url=url,
        title=f"t{i}",
        organization=None,
        embedding=emb,
        extra={"arxiv_id": arxiv, "github_repo": gh},
    )


def test_cluster_exact_link_two_stories():
    # 6 items → 2 stories via shared arxiv/github keys and shared URL
    emb_a = np.array([1.0, 0.0], dtype=np.float32)
    emb_b = np.array([0.0, 1.0], dtype=np.float32)
    items = [
        _item(1, "hf_papers", "https://arxiv.org/abs/1", arxiv="1", emb=emb_a),
        _item(2, "arxiv", "https://arxiv.org/abs/1", arxiv="1", emb=emb_a),
        _item(3, "github_trending", "https://github.com/a/b", gh="a/b", emb=emb_a),
        _item(4, "hf_papers", "https://arxiv.org/abs/1", arxiv="1", gh="a/b", emb=emb_a),
        _item(5, "reddit", "https://shared.example/z", emb=emb_b),
        _item(6, "hackernews", "https://shared.example/z", emb=emb_b),
    ]
    clusters = cluster_items(items, threshold=0.99)
    assert len(clusters) == 2
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [2, 4]


def test_percentile_and_freshness():
    assert percentile_rank([1, 2, 3, 4], 3) == 0.75
    assert freshness_score(0, 36) == 1.0
    assert 0.4 < freshness_score(36, 36) < 0.6
