from app.connectors.base import canonicalize_url


def test_strip_utm_and_slash():
    assert (
        canonicalize_url("https://Example.com/path/?utm_source=x&id=1")
        == "https://example.com/path?id=1"
    )


def test_arxiv_normalize():
    assert canonicalize_url("https://arxiv.org/pdf/2401.12345v2.pdf") == "https://arxiv.org/abs/2401.12345"
    assert canonicalize_url("https://arxiv.org/abs/2401.12345") == "https://arxiv.org/abs/2401.12345"


def test_github_normalize():
    assert (
        canonicalize_url("https://github.com/Owner/Repo.git/issues/1")
        == "https://github.com/Owner/Repo"
    )
