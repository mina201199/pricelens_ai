import hashlib
import math
import re
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from price_lens.db.models import OfficialDocument, OfficialDocumentChunk

EMBEDDING_DIMENSIONS = 256
MAX_DOCUMENT_BYTES = 2_000_000
ALLOWED_PUBLISHERS = {
    "moa.gov.tw": "農業部",
    "agrstat.moa.gov.tw": "農業部統計處",
    "afa.gov.tw": "農業部農糧署",
}


class OfficialSourceError(ValueError):
    pass


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._skip_depth += 1
        if tag.casefold() == "title":
            self._in_title = True
        if tag.casefold() == "meta":
            key = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if key and content:
                self.meta[key.casefold()] = content.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag.casefold() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text and not self._skip_depth:
            self.parts.append(text)
            if self._in_title:
                self.title_parts.append(text)


def source_publisher(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise OfficialSourceError("僅接受 HTTPS 官方來源網址。")
    matches = [
        domain
        for domain in ALLOWED_PUBLISHERS
        if host == domain or host.endswith("." + domain)
    ]
    if not matches:
        raise OfficialSourceError("來源網域不在 Phase 5 官方白名單內。")
    return ALLOWED_PUBLISHERS[max(matches, key=len)]


def fetch_official_document(url: str, timeout_seconds: float = 15.0) -> tuple[str, str]:
    publisher = source_publisher(url)
    try:
        response = httpx.get(
            url,
            follow_redirects=False,
            timeout=timeout_seconds,
            headers={"User-Agent": "PriceLens/0.1 (official document provenance)"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OfficialSourceError("無法取得官方文件。") from exc
    if len(response.content) > MAX_DOCUMENT_BYTES:
        raise OfficialSourceError("官方文件超過 2 MB 上限。")
    if response.headers.get("content-type", "").split(";")[0].strip() not in {
        "text/html", "application/xhtml+xml"
    }:
        raise OfficialSourceError("目前只支援官方 HTML 文件。")
    if source_publisher(str(response.url)) != publisher:
        raise OfficialSourceError("官方文件重新導向至未允許的網域。")

    parser = _VisibleTextParser()
    parser.feed(response.text)
    title = parser.meta.get("og:title") or " ".join(parser.title_parts)
    content = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    if len(content) < 100 or not title:
        raise OfficialSourceError("官方頁面缺少可用標題或正文。")
    return title[:500], content[:500_000]


def chunk_document(content: str, *, max_chars: int = 700) -> list[str]:
    sentences = [part.strip() for part in re.split(r"(?<=[。！？；\n])", content) if part.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def embed_text(text: str) -> list[float]:
    normalized = "".join(text.casefold().split())
    features: dict[int, float] = {}
    for size in (1, 2, 3):
        for index in range(max(0, len(normalized) - size + 1)):
            gram = normalized[index : index + size]
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            sign = 1.0 if digest[4] & 1 else -1.0
            features[bucket] = features.get(bucket, 0.0) + sign
    vector = [features.get(index, 0.0) for index in range(EMBEDDING_DIMENSIONS)]
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def ingest_url(
    session: Session,
    url: str,
    *,
    published_at: date,
    product_slugs: list[str],
    event_start: date,
    event_end: date,
    publisher: str | None = None,
    title: str | None = None,
) -> tuple[OfficialDocument, bool]:
    derived_publisher = source_publisher(url)
    if publisher and publisher != derived_publisher:
        raise OfficialSourceError("publisher 必須符合來源網域。")
    if event_end < event_start:
        raise OfficialSourceError("事件結束日期不可早於開始日期。")
    if not product_slugs:
        raise OfficialSourceError("至少指定一個已映射商品 slug。")
    fetched_title, content = fetch_official_document(url)
    document_title = (title or fetched_title).strip()
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    document = session.scalar(select(OfficialDocument).where(OfficialDocument.source_url == url))
    inserted = document is None
    if document is None:
        document = OfficialDocument(
            publisher=derived_publisher,
            title=document_title,
            source_url=url,
            published_at=published_at,
            retrieved_at=datetime.now(UTC),
            content_hash=content_hash,
            product_slugs=sorted(set(product_slugs)),
            event_start=event_start,
            event_end=event_end,
            metadata_json={"content_type": "text/html"},
        )
        session.add(document)
        session.flush()
    elif document.content_hash != content_hash:
        session.execute(
            delete(OfficialDocumentChunk).where(OfficialDocumentChunk.document_id == document.id)
        )
        document.content_hash = content_hash
        document.retrieved_at = datetime.now(UTC)
        document.title = document_title
        document.published_at = published_at
        document.product_slugs = sorted(set(product_slugs))
        document.event_start = event_start
        document.event_end = event_end
        document.publisher = derived_publisher
        session.flush()
    else:
        document.retrieved_at = datetime.now(UTC)
        document.title = document_title
        document.published_at = published_at
        document.product_slugs = sorted(set(product_slugs))
        document.event_start = event_start
        document.event_end = event_end
        document.publisher = derived_publisher
        return document, False

    for index, chunk in enumerate(chunk_document(content)):
        session.add(
            OfficialDocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=chunk,
                embedding=embed_text(chunk),
            )
        )
    session.flush()
    return document, inserted
