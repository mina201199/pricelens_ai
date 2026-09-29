from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from price_lens.db.models import OfficialDocument, OfficialDocumentChunk
from price_lens.rag.documents import embed_text
from price_lens.schemas.ask import AnswerEvidence, PossibleFactor


class OfficialDocumentRetriever:
    def __init__(self, limit: int = 5) -> None:
        self.limit = limit

    def explain_price_context(
        self,
        session: Session,
        *,
        product_slug: str,
        product_name: str,
        question: str,
        as_of: date,
    ) -> list[PossibleFactor]:
        distance = OfficialDocumentChunk.embedding.cosine_distance(
            embed_text(f"{product_name} {question}")
        ).label("distance")
        rows = session.execute(
            select(OfficialDocument, OfficialDocumentChunk, distance)
            .join(OfficialDocumentChunk, OfficialDocumentChunk.document_id == OfficialDocument.id)
            .where(
                OfficialDocument.product_slugs.contains([product_slug]),
                OfficialDocument.published_at <= as_of,
                OfficialDocument.published_at >= as_of - timedelta(days=365),
                OfficialDocument.event_start <= as_of,
                OfficialDocument.event_end >= as_of - timedelta(days=60),
            )
            .order_by(distance)
            .limit(self.limit * 4)
        ).all()
        factors: list[PossibleFactor] = []
        for document, chunk, score in rows:
            if score is None or score > 0.94:
                continue
            statement = chunk.content.strip()
            if len(statement) > 500:
                statement = statement[:497].rstrip() + "..."
            citation = AnswerEvidence(
                publisher=document.publisher,
                title=document.title,
                source_url=document.source_url,
                as_of=as_of,
                published_at=document.published_at,
                event_start=document.event_start,
                event_end=document.event_end,
                document_id=document.id,
            )
            factors.append(PossibleFactor(statement=statement, evidence=citation))
            if len(factors) >= self.limit:
                break
        return factors
