import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from price_lens.db.models import (
    DataSource,
    Market,
    MarketPriceObservation,
    Product,
    ProductAlias,
    ProductFamily,
    RawMarketRecord,
)
from price_lens.ingestion.mapping import ProductMappingRegistry, normalize_alias
from price_lens.ingestion.normalize import source_record_hash
from price_lens.ingestion.validation.schemas import MoaMarketRecord, validate_market_record

logger = logging.getLogger(__name__)

SOURCE_CODE = "moa_farm_trans_v1"


class ConflictingSourceDuplicateError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadCounts:
    received: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    excluded: int = 0
    quarantined: int = 0

    def __add__(self, other: "LoadCounts") -> "LoadCounts":
        return LoadCounts(
            received=self.received + other.received,
            inserted=self.inserted + other.inserted,
            updated=self.updated + other.updated,
            unchanged=self.unchanged + other.unchanged,
            excluded=self.excluded + other.excluded,
            quarantined=self.quarantined + other.quarantined,
        )


@dataclass(frozen=True)
class _PreparedRecord:
    payload: dict[str, Any]
    record_hash: str
    validation_status: str
    validation_errors: list[dict[str, Any]]
    record: MoaMarketRecord | None


def ensure_data_source(session: Session, api_base_url: str) -> DataSource:
    statement = (
        pg_insert(DataSource)
        .values(
            code=SOURCE_CODE,
            name="農產品交易行情",
            publisher="農業部農糧署",
            dataset_url="https://data.moa.gov.tw/open_detail.aspx?id=037",
            api_url=f"{api_base_url.rstrip('/')}/AgriProductsTransType/",
            license_name="政府資料開放授權條款－第1版",
            active=True,
        )
        .on_conflict_do_update(
            index_elements=[DataSource.code],
            set_={
                "name": "農產品交易行情",
                "publisher": "農業部農糧署",
                "dataset_url": "https://data.moa.gov.tw/open_detail.aspx?id=037",
                "api_url": f"{api_base_url.rstrip('/')}/AgriProductsTransType/",
                "license_name": "政府資料開放授權條款－第1版",
                "active": True,
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(DataSource.id)
    )
    source_id = session.execute(statement).scalar_one()
    return session.get(DataSource, source_id)  # type: ignore[return-value]


def seed_product_mapping(session: Session, registry: ProductMappingRegistry) -> dict[str, int]:
    family_ids: dict[str, int] = {}
    for family in registry.families:
        statement = (
            pg_insert(ProductFamily)
            .values(
                canonical_name=family.canonical_name,
                slug=family.slug,
                display_name=family.display_name,
                category=family.category,
                default_include_imported=family.default_include_imported,
                mapping_version=registry.version,
                active=True,
            )
            .on_conflict_do_update(
                index_elements=[ProductFamily.canonical_name],
                set_={
                    "display_name": family.display_name,
                    "slug": family.slug,
                    "category": family.category,
                    "default_include_imported": family.default_include_imported,
                    "mapping_version": registry.version,
                    "active": True,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(ProductFamily.id)
        )
        family_id = session.execute(statement).scalar_one()
        family_ids[family.canonical_name] = family_id

        # Mapping files are authoritative for active aliases. Disable aliases
        # removed by a later mapping revision before reactivating current ones.
        session.execute(
            update(ProductAlias)
            .where(ProductAlias.family_id == family_id)
            .values(active=False)
        )

        for priority, alias in enumerate(family.aliases, start=1):
            alias_statement = (
                pg_insert(ProductAlias)
                .values(
                    family_id=family_id,
                    alias=alias,
                    normalized_alias=normalize_alias(alias),
                    locale="zh-TW",
                    source="manual",
                    priority=priority,
                    active=True,
                )
                .on_conflict_do_update(
                    index_elements=[ProductAlias.family_id, ProductAlias.normalized_alias],
                    set_={"alias": alias, "priority": priority, "active": True},
                )
            )
            session.execute(alias_statement)
    return family_ids


class MarketDataLoader:
    def __init__(self, registry: ProductMappingRegistry) -> None:
        self.registry = registry

    def load(
        self,
        session: Session,
        *,
        source_id: int,
        ingestion_run_id: int,
        payloads: list[dict[str, Any]],
        fetched_at: datetime | None = None,
    ) -> LoadCounts:
        fetched_at = fetched_at or datetime.now(UTC)
        prepared = self._prepare(payloads)
        self._insert_raw_records(
            session,
            source_id=source_id,
            ingestion_run_id=ingestion_run_id,
            fetched_at=fetched_at,
            records=prepared,
        )

        valid = [item for item in prepared if item.validation_status == "valid" and item.record]
        excluded = sum(item.validation_status == "excluded_closure" for item in prepared)
        quarantined = sum(item.validation_status == "quarantined" for item in prepared)

        family_ids = seed_product_mapping(session, self.registry)
        session.flush()
        market_ids: dict[str, int] = {}
        product_ids: dict[str, int] = {}
        normalized: list[dict[str, Any]] = []

        for item in valid:
            record = item.record
            assert record is not None
            market_id = market_ids.get(record.source_market_code)
            if market_id is None:
                market_id = self._upsert_market(session, source_id, record, fetched_at)
                market_ids[record.source_market_code] = market_id

            product_id = product_ids.get(record.source_product_code)
            if product_id is None:
                product_id = self._upsert_product(
                    session, source_id, record, fetched_at, family_ids
                )
                product_ids[record.source_product_code] = product_id

            normalized.append(
                {
                    "source_id": source_id,
                    "ingestion_run_id": ingestion_run_id,
                    "trade_date": record.trade_date,
                    "market_id": market_id,
                    "product_id": product_id,
                    "upper_price": record.upper_price,
                    "middle_price": record.middle_price,
                    "lower_price": record.lower_price,
                    "average_price": record.average_price,
                    "volume_kg": record.volume_kg,
                    "source_record_hash": item.record_hash,
                    "fetched_at": fetched_at,
                }
            )

        inserted, updated, unchanged = self._upsert_observations(
            session, source_id=source_id, rows=normalized
        )
        counts = LoadCounts(
            received=len(payloads),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            excluded=excluded,
            quarantined=quarantined,
        )
        logger.info("market_records_loaded", extra=counts.__dict__)
        return counts

    def _prepare(self, payloads: list[dict[str, Any]]) -> list[_PreparedRecord]:
        prepared: list[_PreparedRecord] = []
        valid_natural_keys: dict[tuple[date, str, str], str] = {}

        for payload in payloads:
            record_hash = source_record_hash(payload)
            result = validate_market_record(payload)
            item = _PreparedRecord(
                payload=payload,
                record_hash=record_hash,
                validation_status=result.status,
                validation_errors=result.errors,
                record=result.record,
            )
            if result.status == "valid" and result.record is not None:
                key = (
                    result.record.trade_date,
                    result.record.source_market_code,
                    result.record.source_product_code,
                )
                previous_hash = valid_natural_keys.get(key)
                if previous_hash == record_hash:
                    continue
                if previous_hash is not None:
                    raise ConflictingSourceDuplicateError(
                        "Official API returned different values for the same "
                        f"date/market/product natural key: {key}"
                    )
                valid_natural_keys[key] = record_hash
            prepared.append(item)
        return prepared

    @staticmethod
    def _insert_raw_records(
        session: Session,
        *,
        source_id: int,
        ingestion_run_id: int,
        fetched_at: datetime,
        records: list[_PreparedRecord],
    ) -> None:
        for offset in range(0, len(records), 1000):
            batch = records[offset : offset + 1000]
            if not batch:
                continue
            statement = (
                pg_insert(RawMarketRecord)
                .values(
                    [
                        {
                            "ingestion_run_id": ingestion_run_id,
                            "source_id": source_id,
                            "source_record_hash": item.record_hash,
                            "payload": item.payload,
                            "fetched_at": fetched_at,
                            "validation_status": item.validation_status,
                            "validation_errors": item.validation_errors,
                        }
                        for item in batch
                    ]
                )
                .on_conflict_do_nothing(
                    index_elements=[RawMarketRecord.source_id, RawMarketRecord.source_record_hash]
                )
            )
            session.execute(statement)

    @staticmethod
    def _upsert_market(
        session: Session,
        source_id: int,
        record: MoaMarketRecord,
        seen_at: datetime,
    ) -> int:
        statement = (
            pg_insert(Market)
            .values(
                source_id=source_id,
                source_market_code=record.source_market_code,
                source_market_name=record.source_market_name,
                canonical_name=record.source_market_name,
                active=True,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            .on_conflict_do_update(
                index_elements=[Market.source_id, Market.source_market_code],
                set_={
                    "source_market_name": record.source_market_name,
                    "canonical_name": record.source_market_name,
                    "active": True,
                    "last_seen_at": seen_at,
                },
            )
            .returning(Market.id)
        )
        return session.execute(statement).scalar_one()

    def _upsert_product(
        self,
        session: Session,
        source_id: int,
        record: MoaMarketRecord,
        seen_at: datetime,
        family_ids: dict[str, int],
    ) -> int:
        decision = self.registry.resolve(record.source_product_code, record.source_product_name)
        family_id = family_ids.get(decision.family_name) if decision.family_name else None
        if decision.reason == "source_name_mismatch":
            logger.warning(
                "product_mapping_name_mismatch",
                extra={
                    "source_product_code": record.source_product_code,
                    "source_product_name": record.source_product_name,
                    "mapping_version": decision.mapping_version,
                },
            )
        statement = (
            pg_insert(Product)
            .values(
                source_id=source_id,
                family_id=family_id,
                source_product_code=record.source_product_code,
                source_product_name=record.source_product_name,
                category_code=record.category_code,
                variety=decision.variety,
                origin_type=decision.origin_type,
                analytics_included=decision.analytics_included,
                mapping_version=decision.mapping_version,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
            )
            .on_conflict_do_update(
                index_elements=[Product.source_id, Product.source_product_code],
                set_={
                    "family_id": family_id,
                    "source_product_name": record.source_product_name,
                    "category_code": record.category_code,
                    "variety": decision.variety,
                    "origin_type": decision.origin_type,
                    "analytics_included": decision.analytics_included,
                    "mapping_version": decision.mapping_version,
                    "last_seen_at": seen_at,
                },
            )
            .returning(Product.id)
        )
        return session.execute(statement).scalar_one()

    @staticmethod
    def _upsert_observations(
        session: Session, *, source_id: int, rows: list[dict[str, Any]]
    ) -> tuple[int, int, int]:
        if not rows:
            return 0, 0, 0
        trade_dates = {row["trade_date"] for row in rows}
        existing = session.execute(
            select(
                MarketPriceObservation.trade_date,
                MarketPriceObservation.market_id,
                MarketPriceObservation.product_id,
                MarketPriceObservation.source_record_hash,
            ).where(
                MarketPriceObservation.source_id == source_id,
                MarketPriceObservation.trade_date.in_(trade_dates),
            )
        ).all()
        existing_hashes = {
            (row.trade_date, row.market_id, row.product_id): row.source_record_hash
            for row in existing
        }

        inserted = 0
        updated = 0
        unchanged = 0
        changed_rows: list[dict[str, Any]] = []
        for row in rows:
            key = (row["trade_date"], row["market_id"], row["product_id"])
            previous_hash = existing_hashes.get(key)
            if previous_hash is None:
                inserted += 1
                changed_rows.append(row)
            elif previous_hash != row["source_record_hash"]:
                updated += 1
                changed_rows.append(row)
            else:
                unchanged += 1

        for offset in range(0, len(changed_rows), 1000):
            batch = changed_rows[offset : offset + 1000]
            if not batch:
                continue
            statement = pg_insert(MarketPriceObservation).values(batch)
            statement = statement.on_conflict_do_update(
                index_elements=[
                    MarketPriceObservation.source_id,
                    MarketPriceObservation.trade_date,
                    MarketPriceObservation.market_id,
                    MarketPriceObservation.product_id,
                ],
                set_={
                    "ingestion_run_id": statement.excluded.ingestion_run_id,
                    "upper_price": statement.excluded.upper_price,
                    "middle_price": statement.excluded.middle_price,
                    "lower_price": statement.excluded.lower_price,
                    "average_price": statement.excluded.average_price,
                    "volume_kg": statement.excluded.volume_kg,
                    "source_record_hash": statement.excluded.source_record_hash,
                    "fetched_at": statement.excluded.fetched_at,
                },
            )
            session.execute(statement)
        return inserted, updated, unchanged
