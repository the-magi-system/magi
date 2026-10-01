"""Shared types for turning an accepted proposal into file changes (pipeline step 7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .errors import E_INTERNAL, E_SEMANTIC, MagiError
from .prices import PriceProvider, Quote, fetch
from .proposal import Proposal
from .repo import RepoState
from .timeutil import iso


@dataclass
class Context:
    state: RepoState
    proposal: Proposal
    issue: int
    owner: str
    now: datetime
    prices: PriceProvider

    @property
    def actor(self) -> str:
        return self.proposal.actor

    @property
    def payload(self) -> dict:
        return self.proposal.payload


@dataclass
class ChangeSet:
    summary: str
    writes: dict[str, dict] = field(default_factory=dict)
    log: list[dict] = field(default_factory=list)
    created: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    mention_maintainers: bool = False


class ApplyError(Exception):
    def __init__(self, error: MagiError):
        super().__init__(error.message)
        self.error = error


def entity(path: str) -> str:
    return path.removesuffix(".yaml")


def log_entry(ctx: Context, path: str, **extra) -> dict:
    entry = {"at": iso(ctx.now), "issue": ctx.issue, "action": ctx.proposal.action,
             "actor": ctx.actor, "owner": ctx.owner, "entity": entity(path)}
    entry.update({key: value for key, value in extra.items() if value is not None})
    return entry


def quote_for(ctx: Context, asset: dict, registering: bool = False) -> Quote:
    quote, error = fetch(ctx.prices, asset, ctx.now)
    if error is not None:
        raise ApplyError(error)
    if quote.currency and quote.currency != asset["currency"]:
        symbol = asset["price_source"]["symbol"]
        if registering:
            raise ApplyError(MagiError(
                E_SEMANTIC, "/payload/currency",
                f"the price source quotes {symbol} in {quote.currency}, not {asset['currency']}"))
        raise ApplyError(MagiError(
            E_INTERNAL, "",
            f"the price source quotes {symbol} in {quote.currency} but registry/assets/{asset['id']}.yaml "
            f"says {asset['currency']}; a maintainer must correct the asset record"))
    return quote
