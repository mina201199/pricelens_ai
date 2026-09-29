import hashlib
import json
import re
from datetime import date, timedelta
from typing import Any

ROC_DATE_PATTERN = re.compile(r"^(?P<year>\d{2,3})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})$")


def parse_roc_date(value: str) -> date:
    match = ROC_DATE_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid ROC date format: {value!r}")
    year = int(match.group("year")) + 1911
    return date(year, int(match.group("month")), int(match.group("day")))


def format_roc_date(value: date) -> str:
    if value.year <= 1911:
        raise ValueError("ROC date conversion requires Gregorian year > 1911")
    return f"{value.year - 1911:03d}.{value.month:02d}.{value.day:02d}"


def inclusive_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end date must not be before start date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def source_record_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
