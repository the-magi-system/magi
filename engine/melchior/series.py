"""The benchmark and market-state series of the benchmark policies (protocol section 10 Benchmarks, design 22.4).

Melchior.Magi registers every series of every policy version that is not registered yet, as a system write
that passes the checks of register_asset, then backfills three years of closes and corporate actions.
"""
from __future__ import annotations

from datetime import date, datetime

from ..changes import ChangeSet
from ..consistency import Finding
from ..errors import MagiError
from ..prices import PriceProvider, fetch
from ..repo import RepoState
from ..schemas import validate_payload
from ..semantic import CHECKS
from ..sysagent import system_log_entry
from ..timeutil import iso
from .common import MELCHIOR

PAYLOAD_FIELDS = ("name", "type", "sector", "currency", "price_source")
BACKFILL_YEARS = 3


class SeriesError(Exception):
    """A series that cannot be registered; the reason goes into the run summary and a finding."""


def missing_series(state: RepoState, policies: list[dict]) -> tuple[list[tuple[str, dict]], list[Finding]]:
    """The series of every policy version that are not registered yet, and the ids registered for something else."""
    missing: list[tuple[str, dict]] = []
    findings: list[Finding] = []
    seen: set[str] = set()
    for policy in sorted(policies, key=lambda p: p["version"]):
        for series_id, spec in policy["series"].items():
            if series_id in seen:
                continue
            seen.add(series_id)
            asset = state.assets.get(series_id)
            if asset is None:
                missing.append((series_id, spec))
                continue
            wanted, found = spec["price_source"], asset["price_source"]
            if (found["provider"], found["symbol"]) != (wanted["provider"], wanted["symbol"]):
                findings.append(Finding(
                    f"registry/assets/{series_id}.yaml",
                    f"'{series_id}' is registered for {found['provider']} {found['symbol']}, so the benchmark policy "
                    f"needs another id for {wanted['symbol']}", "maintainer"))
    return missing, findings


def _first(errors: list[MagiError]) -> str:
    return f"{errors[0].path}: {errors[0].message}"


def register_series(state: RepoState, series_id: str, spec: dict, prices: PriceProvider, now: datetime,
                    run: int) -> ChangeSet:
    payload = {"id": series_id, **{key: spec[key] for key in PAYLOAD_FIELDS}}
    errors = validate_payload(state.root, "register_asset", payload) or CHECKS["register_asset"](state, MELCHIOR, payload)[0]
    if errors:
        raise SeriesError(f"{series_id} fails the checks of register_asset: {_first(errors)}")
    quote, error = fetch(prices, payload, now)
    if error is not None:
        raise SeriesError(f"{series_id} has no usable quote: {error.message}")
    if quote.currency and quote.currency != payload["currency"]:
        raise SeriesError(f"the price source quotes {spec['price_source']['symbol']} in {quote.currency}, not "
                          f"{payload['currency']}; {series_id} is not registered")
    record = {"schema": "magi/asset@1", **payload, "registered_by": MELCHIOR, "registered_at": iso(now),
              "registered_via_run": run}
    path = f"registry/assets/{series_id}.yaml"
    changes = ChangeSet(f"register_asset: {series_id}", writes={path: record}, created={"asset_id": series_id})
    changes.log.append(system_log_entry(now, run, "register_asset", MELCHIOR, path))
    return changes


def backfill_start(today: date) -> date:
    """The same day three years earlier; 29 February becomes the 28th."""
    day = 28 if (today.month, today.day) == (2, 29) else today.day
    return date(today.year - BACKFILL_YEARS, today.month, day)
