import pytest

from price_lens.rag.documents import (
    OfficialSourceError,
    chunk_document,
    embed_text,
    source_publisher,
)


def test_official_allowlist_accepts_ministry_subdomains() -> None:
    assert source_publisher("https://www.afa.gov.tw/news") == "農業部農糧署"
    assert source_publisher("https://agrstat.moa.gov.tw/report") == "農業部統計處"


def test_official_allowlist_rejects_lookalike_hosts_and_plain_http() -> None:
    for url in (
        "https://afa.gov.tw.attacker.example/news",
        "http://www.afa.gov.tw/news",
        "https://example.com/news",
    ):
        try:
            source_publisher(url)
        except OfficialSourceError:
            continue
        raise AssertionError(f"unexpectedly accepted {url}")


def test_chunks_keep_sentence_boundaries_and_respect_size() -> None:
    chunks = chunk_document("甲" * 900 + "。乙。丙。", max_chars=100)
    assert chunks
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "乙。" in "".join(chunks)


def test_character_embedding_is_fixed_size_normalized_and_repeatable() -> None:
    first = embed_text("高麗菜價格供應")
    second = embed_text("高麗菜價格供應")
    assert len(first) == 256
    assert first == second
    assert sum(value * value for value in first) == pytest.approx(1.0)
