import argparse
from datetime import date

from sqlalchemy import select

from price_lens.db.models import ProductFamily
from price_lens.db.session import SessionLocal
from price_lens.rag.documents import OfficialSourceError, ingest_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest one official agriculture document.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("url")
    ingest.add_argument("--published-at", required=True, type=date.fromisoformat)
    ingest.add_argument("--event-start", required=True, type=date.fromisoformat)
    ingest.add_argument("--event-end", required=True, type=date.fromisoformat)
    ingest.add_argument("--product", action="append", required=True, dest="products")
    ingest.add_argument("--title")

    args = parser.parse_args()
    try:
        with SessionLocal.begin() as session:
            valid_slugs = set(
                session.scalars(
                    select(ProductFamily.slug).where(ProductFamily.active.is_(True))
                ).all()
            )
            invalid = sorted(set(args.products) - valid_slugs)
            if invalid:
                raise OfficialSourceError(f"未知 canonical product slug: {', '.join(invalid)}")
            document, inserted = ingest_url(
                session,
                args.url,
                published_at=args.published_at,
                event_start=args.event_start,
                event_end=args.event_end,
                product_slugs=args.products,
                title=args.title,
            )
            print(
                f"{'inserted' if inserted else 'updated-or-unchanged'} document_id={document.id} "
                f"title={document.title!r} content_hash={document.content_hash}"
            )
    except OfficialSourceError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
