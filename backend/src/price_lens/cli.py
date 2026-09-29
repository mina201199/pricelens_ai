import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config

from price_lens.analytics.refresh import AnalyticsRefresher
from price_lens.config import get_settings
from price_lens.data_quality import build_data_quality_report
from price_lens.db.session import SessionLocal
from price_lens.ingestion.jobs.market_etl import MarketEtlJob
from price_lens.logging_config import configure_logging


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected ISO date YYYY-MM-DD") from exc


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="price-lens",
        description="Price Lens Phase 1 data foundation commands",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="Upgrade PostgreSQL to the latest Alembic migration")

    etl = subparsers.add_parser("etl", help="Fetch and load official wholesale market data")
    etl.add_argument("--start", type=_parse_iso_date)
    etl.add_argument("--end", type=_parse_iso_date)
    etl.add_argument("--days", type=int, default=7)
    etl.add_argument("--job-type", default="manual")
    etl.add_argument(
        "--mapped-products-only",
        action="store_true",
        help="Backfill only explicitly mapped MVP source product codes",
    )

    subparsers.add_parser("data-quality", help="Print the PostgreSQL data-quality report")
    subparsers.add_parser(
        "analytics-refresh",
        help="Rebuild deterministic daily product metrics from normalized facts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)

    if args.command == "migrate":
        command.upgrade(_alembic_config(), "head")
        return 0

    if args.command == "data-quality":
        with SessionLocal() as session:
            report = build_data_quality_report(session)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "analytics-refresh":
        with SessionLocal.begin() as session:
            result = AnalyticsRefresher().refresh(session)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "etl":
        if args.days < 1:
            raise SystemExit("--days must be at least 1")
        taipei_today = datetime.now(ZoneInfo("Asia/Taipei")).date()
        end = args.end or (taipei_today - timedelta(days=1))
        start = args.start or (end - timedelta(days=args.days - 1))
        if args.start and not args.end:
            end = args.start + timedelta(days=args.days - 1)
        if args.end and not args.start:
            start = args.end - timedelta(days=args.days - 1)
        run = asyncio.run(
            MarketEtlJob(settings, SessionLocal).run(
                start,
                end,
                job_type=args.job_type,
                mapped_products_only=args.mapped_products_only,
            )
        )
        print(
            json.dumps(
                {
                    "ingestion_run_id": run.id,
                    "status": run.status,
                    "window_start": run.window_start.isoformat(),
                    "window_end": run.window_end.isoformat(),
                    "records_received": run.records_received,
                    "records_inserted": run.records_inserted,
                    "records_updated": run.records_updated,
                    "records_unchanged": run.records_unchanged,
                    "records_excluded": run.records_excluded,
                    "records_quarantined": run.records_quarantined,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
