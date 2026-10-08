"""UTC time helpers. Every timestamp the engine writes is UTC, ISO 8601, ending in Z."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(ISO_FORMAT)


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_iso(text: str) -> datetime:
    return datetime.strptime(text, ISO_FORMAT).replace(tzinfo=timezone.utc)


def add_months(day: date, months: int) -> date:
    """Add calendar months; a day the target month lacks becomes its last day."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def target_date(published_at: str, horizon_months: int) -> str:
    """The date whose market price a view's distribution describes: the UTC publication date plus the horizon."""
    return add_months(parse_iso(published_at).date(), horizon_months).isoformat()
