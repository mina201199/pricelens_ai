from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from price_lens.db.models import ProductAlias, ProductFamily
from price_lens.ingestion.mapping import normalize_alias
from price_lens.schemas.analytics import ProductIdentity


@dataclass(frozen=True)
class NormalizedProduct:
    identity: ProductIdentity
    matched_text: str
    confidence: float


@dataclass(frozen=True)
class ProductCandidate:
    identity: ProductIdentity
    alias: str
    normalized_alias: str
    priority: int


def match_product(
    question: str, candidates: list[ProductCandidate]
) -> NormalizedProduct | None:
    normalized_question = normalize_alias(question)
    matches = [
        candidate
        for candidate in candidates
        if candidate.normalized_alias
        and candidate.normalized_alias in normalized_question
    ]
    if not matches:
        return None
    candidate = max(
        matches,
        key=lambda item: (len(item.normalized_alias), -item.priority),
    )
    return NormalizedProduct(
        identity=candidate.identity,
        matched_text=candidate.alias,
        confidence=1.0,
    )


class ProductNormalizer:
    def normalize(self, session: Session, question: str) -> NormalizedProduct | None:
        rows = session.execute(
            select(
                ProductFamily,
                ProductAlias.alias,
                ProductAlias.normalized_alias,
                ProductAlias.priority,
            )
            .join(ProductAlias, ProductAlias.family_id == ProductFamily.id)
            .where(ProductFamily.active.is_(True), ProductAlias.active.is_(True))
            .order_by(ProductAlias.priority, ProductAlias.normalized_alias.desc())
        )
        candidates = [
            ProductCandidate(
                identity=ProductIdentity(
                    slug=family.slug,
                    canonical_name=family.canonical_name,
                    display_name=family.display_name,
                    category=family.category,
                ),
                alias=alias,
                normalized_alias=normalized,
                priority=priority,
            )
            for family, alias, normalized, priority in rows
        ]
        return match_product(question, candidates)
