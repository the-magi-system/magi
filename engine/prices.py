"""Price quotes (spec 5.12, 10.3). The engine never accepts a price from a proposer."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from .errors import E_PRICE, E_PRICE_STALE, MagiError
from .timeutil import iso, parse_iso

STALE_AFTER = timedelta(days=7)
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
USER_AGENT = "Mozilla/5.0 (compatible; magi-engine)"


@dataclass(frozen=True)
class Quote:
    value: float
    currency: str
    as_of: str
    source: str

    def to_dict(self) -> dict:
        return {"value": self.value, "currency": self.currency, "as_of": self.as_of, "source": self.source}


class PriceError(Exception):
    """No usable price could be obtained; maps to E_PRICE."""


class PriceProvider(Protocol):
    def quote(self, asset: dict) -> Quote: ...


class YahooProvider:
    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 15.0):
        self._open = opener
        self._timeout = timeout

    def quote(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        request = urllib.request.Request(
            YAHOO_URL.format(symbol=urllib.parse.quote(symbol, safe="")), headers={"User-Agent": USER_AGENT}
        )
        try:
            with self._open(request, timeout=self._timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise PriceError(f"price request for {symbol} failed: {exc}") from exc
        try:
            meta = data["chart"]["result"][0]["meta"]
            value = float(meta["regularMarketPrice"])
            moment = datetime.fromtimestamp(int(meta["regularMarketTime"]), timezone.utc)
            currency = str(meta.get("currency") or "")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return Quote(value, currency, iso(moment), "yahoo")


class FixedPrices:
    """Quotes the same value for every asset, stamped at `now`. Used by dry runs."""

    def __init__(self, value: float, now: datetime):
        self.value, self.now = value, now

    def quote(self, asset: dict) -> Quote:
        return Quote(self.value, asset["currency"], iso(self.now), "fixed")


def fetch(prices: PriceProvider, asset: dict, now: datetime) -> tuple[Quote | None, MagiError | None]:
    """Fetch a quote and apply the freshness rule. Exactly one of the two results is None."""
    try:
        quote = prices.quote(asset)
    except PriceError as exc:
        return None, MagiError(E_PRICE, "", str(exc))
    if now - parse_iso(quote.as_of) > STALE_AFTER:
        message = f"the latest price of {asset['id']} is from {quote.as_of}, more than 7 calendar days old"
        return None, MagiError(E_PRICE_STALE, "", message)
    return quote, None
