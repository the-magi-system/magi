"""Price quotes (spec 5.12, 10.3, 16.4). The engine never accepts a price from a proposer."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from .errors import E_PRICE, E_PRICE_STALE, MagiError
from .timeutil import iso, parse_iso, utc_now

STALE_AFTER = timedelta(days=7)
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval={interval}"
NAVER_URL = "https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=5&requestType=0"
NAVER_CLOSE_UTC = "06:30:00"  # the Korea Exchange closes at 15:30 KST
USER_AGENT = "Mozilla/5.0 (compatible; magi-engine)"
_NAVER_ITEM = re.compile(r'<item data="([^"]+)"')


@dataclass(frozen=True)
class Quote:
    value: float
    currency: str
    as_of: str
    source: str
    market_date: str | None = field(default=None, compare=False)  # the exchange's own trading day

    def to_dict(self) -> dict:
        return {"value": self.value, "currency": self.currency, "as_of": self.as_of, "source": self.source}


class PriceError(Exception):
    """No usable price could be obtained; maps to E_PRICE."""


class PriceProvider(Protocol):
    def quote(self, asset: dict) -> Quote: ...

    def close(self, asset: dict) -> Quote: ...


def _download(opener: Callable, url: str, timeout: float, symbol: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=timeout) as response:
            return response.read()
    except Exception as exc:
        raise PriceError(f"price request for {symbol} failed: {exc}") from exc


def _moment(stamp: int) -> str:
    return iso(datetime.fromtimestamp(int(stamp), timezone.utc))


def _market_date(stamp: int, offset: int) -> str:
    """The exchange's own date for a bar. Yahoo stamps a daily bar at the session open, in UTC."""
    return datetime.fromtimestamp(int(stamp) + offset, timezone.utc).strftime("%Y-%m-%d")


class YahooProvider:
    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 15.0,
                 clock: Callable[[], datetime] = utc_now):
        self._open = opener
        self._timeout = timeout
        self._clock = clock

    def _chart(self, symbol: str, range_: str, interval: str) -> dict:
        url = YAHOO_URL.format(symbol=urllib.parse.quote(symbol, safe=""), range=range_, interval=interval)
        raw = _download(self._open, url, self._timeout, symbol)
        try:
            return json.loads(raw.decode("utf-8"))["chart"]["result"][0]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc

    @staticmethod
    def _bars(result: dict, symbol: str) -> list[tuple[int, float | None]]:
        try:
            stamps = result.get("timestamp") or []
            closes = result["indicators"]["quote"][0].get("close") or []
        except (KeyError, IndexError, TypeError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return list(zip(stamps, closes))

    def quote(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        result = self._chart(symbol, "5d", "1d")
        try:
            meta = result["meta"]
            value = float(meta["regularMarketPrice"])
            moment = _moment(meta["regularMarketTime"])
            currency = str(meta.get("currency") or "")
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return Quote(value, currency, moment, "yahoo")

    def close(self, asset: dict) -> Quote:
        """Last settled daily close, dated by the exchange's own day (spec 16.4).

        A session that is still trading is skipped. When the latest finished daily bar has no close
        yet, the close is that day's last 5-minute bar.
        """
        symbol = asset["price_source"]["symbol"]
        daily = self._chart(symbol, "5d", "1d")
        meta = daily.get("meta") or {}
        currency = str(meta.get("currency") or "")
        offset = int(meta.get("gmtoffset") or 0)
        bars = self._bars(daily, symbol)
        session = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        if bars and session and bars[-1][0] >= session.get("start", 0) \
                and self._clock() < datetime.fromtimestamp(session.get("end", 0), timezone.utc):
            bars = bars[:-1]
        if bars and bars[-1][1] is None:
            day_start = bars[-1][0]
            intraday = [b for b in self._bars(self._chart(symbol, "2d", "5m"), symbol)
                        if b[1] is not None and b[0] >= day_start]
            if intraday:
                stamp, value = intraday[-1]
                return Quote(float(value), currency, _moment(stamp), "yahoo-5m", _market_date(day_start, offset))
        settled = [b for b in bars if b[1] is not None]
        if not settled:
            raise PriceError(f"no settled close for {symbol}")
        stamp, value = settled[-1]
        return Quote(float(value), currency, _moment(stamp), "yahoo", _market_date(stamp, offset))


class NaverProvider:
    """Daily bars from Naver Finance, the source for Korea-listed shares (spec 16.4)."""

    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 15.0,
                 clock: Callable[[], datetime] = utc_now):
        self._open = opener
        self._timeout = timeout
        self._clock = clock

    def _daily(self, symbol: str) -> list[Quote]:
        url = NAVER_URL.format(symbol=urllib.parse.quote(symbol, safe=""))
        text = _download(self._open, url, self._timeout, symbol).decode("euc-kr", errors="replace")
        items = _NAVER_ITEM.findall(text)
        if not items:
            raise PriceError(f"unexpected price response for {symbol}: no daily bars")
        quotes = []
        try:
            for item in items:
                day, _open, _high, _low, close, _volume = item.split("|")
                date = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
                moment = f"{date}T{NAVER_CLOSE_UTC}Z"
                parse_iso(moment)
                quotes.append(Quote(float(close), "KRW", moment, "naver", date))
        except ValueError as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return quotes

    def quote(self, asset: dict) -> Quote:
        latest = self._daily(asset["price_source"]["symbol"])[-1]
        now = self._clock()
        if parse_iso(latest.as_of) > now:  # the session is still trading; never stamp a price in the future
            return Quote(latest.value, "KRW", iso(now), "naver", latest.market_date)
        return latest

    def close(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        now = self._clock()
        settled = [bar for bar in self._daily(symbol) if parse_iso(bar.as_of) <= now]
        if not settled:
            raise PriceError(f"no settled close for {symbol}")
        return settled[-1]


class PriceRouter:
    """Sends each asset to the provider named in its price_source (D14)."""

    def __init__(self, providers: dict[str, PriceProvider] | None = None):
        self.providers = providers if providers is not None else {"yahoo": YahooProvider(), "naver": NaverProvider()}

    def _provider(self, asset: dict) -> PriceProvider:
        name = asset["price_source"]["provider"]
        if name not in self.providers:
            raise PriceError(f"no price provider named {name!r}")
        return self.providers[name]

    def quote(self, asset: dict) -> Quote:
        return self._provider(asset).quote(asset)

    def close(self, asset: dict) -> Quote:
        return self._provider(asset).close(asset)


class FixedPrices:
    """Quotes the same value for every asset, stamped at `now`. Used by dry runs."""

    def __init__(self, value: float, now: datetime):
        self.value, self.now = value, now

    def quote(self, asset: dict) -> Quote:
        return Quote(self.value, asset["currency"], iso(self.now), "fixed")

    def close(self, asset: dict) -> Quote:
        return self.quote(asset)


def fetch(prices: PriceProvider, asset: dict, now: datetime) -> tuple[Quote | None, MagiError | None]:
    """Fetch a quote and apply the freshness rule. Exactly one of the two results is None."""
    try:
        quote = prices.quote(asset)
    except PriceError as exc:
        return None, MagiError(E_PRICE, "", str(exc))
    if quote.value <= 0:
        return None, MagiError(E_PRICE, "", f"{asset['id']} was quoted at {quote.value}; a price of zero or below is not used")
    if now - parse_iso(quote.as_of) > STALE_AFTER:
        message = f"the latest price of {asset['id']} is from {quote.as_of}, more than 7 calendar days old"
        return None, MagiError(E_PRICE_STALE, "", message)
    return quote, None
