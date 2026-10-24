"""Price quotes (spec 5.12, 10.3, 16.4). The engine never accepts a price from a proposer."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from .errors import E_PRICE, E_PRICE_STALE, MagiError
from .timeutil import iso, parse_iso, utc_now

STALE_AFTER = timedelta(days=7)
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
YAHOO_EVENTS = "interval=1d&events=div%2Csplits"
NAVER_URL = "https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count={count}&requestType=0"
NAVER_CLOSE_UTC = "06:30:00"  # the Korea Exchange closes at 15:30 KST
NAVER_HISTORY_BARS = 30
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

    @property
    def trading_date(self) -> str:
        """The trading day a close belongs to: the exchange's own day, else the date of as_of."""
        return self.market_date or self.as_of[:10]

    def as_close(self) -> dict:
        return {"date": self.trading_date, "value": self.value, "currency": self.currency, "as_of": self.as_of,
                "source": self.source}


@dataclass(frozen=True)
class Session:
    """When a trading day's regular session closes: in an exchange time zone, at the end of a UTC day, or fixed."""
    kind: str  # exchange, utc-day or fixed
    timezone: str | None = None
    close_local: str | None = None  # HH:MM in `timezone`
    fixed_utc: str | None = None  # HH:MM in UTC

    def close_at(self, day: str) -> datetime:
        on = date.fromisoformat(day)
        if self.kind == "utc-day":
            return datetime.combine(on + timedelta(days=1), time(0, 0), timezone.utc)
        if self.kind == "fixed":
            return datetime.combine(on, time.fromisoformat(self.fixed_utc), timezone.utc)
        local = datetime.combine(on, time.fromisoformat(self.close_local), ZoneInfo(self.timezone))
        return local.astimezone(timezone.utc)


@dataclass(frozen=True)
class History:
    """Settled daily closes and corporate actions over a range, in as-traded values."""
    bars: list[Quote]  # oldest first, each with market_date
    actions: list[dict]  # market/actions/ lines without recorded_at
    session: Session | None
    currency: str
    rejected: list[dict] = field(default_factory=list)  # corporate actions not recorded, each with a reason


class PriceError(Exception):
    """No usable price could be obtained; maps to E_PRICE."""


class PriceProvider(Protocol):
    def quote(self, asset: dict) -> Quote: ...

    def close(self, asset: dict) -> Quote: ...

    def history(self, asset: dict, start: date | None = None) -> History: ...


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


def _whole(number) -> int | None:
    value = float(number)
    return int(value) if value.is_integer() and value >= 1 else None


def _as_traded(value: float, day: str, splits: list[tuple[str, float]]) -> float:
    """Undo the price source's adjustment for every split dated after `day` in the same response."""
    factor = 1.0
    for split_date, ratio in splits:
        if split_date > day:
            factor *= ratio
    return value if factor == 1 else round(value * factor, 6)


class YahooProvider:
    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 15.0,
                 clock: Callable[[], datetime] = utc_now):
        self._open = opener
        self._timeout = timeout
        self._clock = clock

    def _chart(self, symbol: str, query: str) -> dict:
        url = YAHOO_URL.format(symbol=urllib.parse.quote(symbol, safe=""), query=query)
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
        result = self._chart(symbol, "range=5d&interval=1d")
        try:
            meta = result["meta"]
            value = float(meta["regularMarketPrice"])
            moment = _moment(meta["regularMarketTime"])
            currency = str(meta.get("currency") or "")
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return Quote(value, currency, moment, "yahoo")

    def _settled_bars(self, daily: dict, symbol: str) -> list[Quote]:
        """The settled daily closes of a response, dated by the exchange's own day (spec 16.4).

        A session that is still trading is skipped. When the latest finished daily bar has no close
        yet, its close is that day's last 5-minute bar; other bars without a close are dropped.
        """
        meta = daily.get("meta") or {}
        currency = str(meta.get("currency") or "")
        offset = int(meta.get("gmtoffset") or 0)
        bars = self._bars(daily, symbol)
        session = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        if bars and session and bars[-1][0] >= session.get("start", 0) \
                and self._clock() < datetime.fromtimestamp(session.get("end", 0), timezone.utc):
            bars = bars[:-1]
        last = None
        if bars and bars[-1][1] is None:
            day_start = bars[-1][0]
            intraday = [b for b in self._bars(self._chart(symbol, "range=2d&interval=5m"), symbol)
                        if b[1] is not None and b[0] >= day_start]
            if intraday:
                stamp, value = intraday[-1]
                last = Quote(float(value), currency, _moment(stamp), "yahoo-5m", _market_date(day_start, offset))
        settled = [Quote(float(value), currency, _moment(stamp), "yahoo", _market_date(stamp, offset))
                   for stamp, value in bars if value is not None]
        return settled + ([last] if last is not None else [])

    def close(self, asset: dict) -> Quote:
        """Last settled daily close: the last bar of a five-day range, by the rules of _settled_bars."""
        symbol = asset["price_source"]["symbol"]
        settled = self._settled_bars(self._chart(symbol, "range=5d&interval=1d"), symbol)
        if not settled:
            raise PriceError(f"no settled close for {symbol}")
        return settled[-1]

    def history(self, asset: dict, start: date | None = None) -> History:
        """Settled daily closes and corporate actions from `start` (else the last month) to now, as traded.

        The price source adjusts closes and dividends for later splits, so each is multiplied back by the splits
        dated after it in the same response. A request therefore always ends now.
        """
        symbol, asset_id = asset["price_source"]["symbol"], asset["id"]
        if start is None:
            query = f"range=1mo&{YAHOO_EVENTS}"
        else:
            begin = datetime.combine(start, time(0, 0), timezone.utc)
            query = f"period1={int(begin.timestamp())}&period2={int(self._clock().timestamp())}&{YAHOO_EVENTS}"
        daily = self._chart(symbol, query)
        meta = daily.get("meta") or {}
        currency = str(meta.get("currency") or "")
        offset = int(meta.get("gmtoffset") or 0)
        events = daily.get("events") or {}
        actions, rejected, splits = [], [], []
        try:
            for item in (events.get("splits") or {}).values():
                day = _market_date(item["date"], offset)
                splits.append((day, float(item["numerator"]) / float(item["denominator"])))
                numerator, denominator = _whole(item["numerator"]), _whole(item["denominator"])
                split = {"date": day, "asset": asset_id, "kind": "split", "numerator": numerator,
                         "denominator": denominator, "source": "yahoo"}
                if numerator is None or denominator is None:
                    rejected.append({**split, "numerator": item["numerator"], "denominator": item["denominator"],
                                     "reason": "the split ratio is not a ratio of whole numbers"})
                else:
                    actions.append(split)
            for item in (events.get("dividends") or {}).values():
                day = _market_date(item["date"], offset)
                actions.append({"date": day, "asset": asset_id, "kind": "dividend",
                                "amount": _as_traded(float(item["amount"]), day, splits), "currency": currency,
                                "source": "yahoo"})
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            raise PriceError(f"unexpected corporate actions for {symbol}: {exc!r}") from exc
        bars = [Quote(_as_traded(bar.value, bar.trading_date, splits), bar.currency, bar.as_of, bar.source,
                      bar.market_date) for bar in self._settled_bars(daily, symbol)]
        actions.sort(key=lambda action: (action["date"], action["kind"]))
        return History(bars, actions, self._session(meta), currency, rejected)

    @staticmethod
    def _session(meta: dict) -> Session | None:
        if meta.get("instrumentType") == "CRYPTOCURRENCY":
            return Session("utc-day")
        zone = meta.get("exchangeTimezoneName")
        end = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
        if not zone or end is None:
            return None
        local = datetime.fromtimestamp(int(end), timezone.utc).astimezone(ZoneInfo(zone))
        return Session("exchange", zone, local.strftime("%H:%M"))


class NaverProvider:
    """Daily bars from Naver Finance, the source for Korea-listed shares (spec 16.4)."""

    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 15.0,
                 clock: Callable[[], datetime] = utc_now):
        self._open = opener
        self._timeout = timeout
        self._clock = clock

    def _daily(self, symbol: str, count: int = 5) -> list[Quote]:
        url = NAVER_URL.format(symbol=urllib.parse.quote(symbol, safe=""), count=count)
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

    def _settled(self, symbol: str, count: int) -> list[Quote]:
        now = self._clock()
        return [bar for bar in self._daily(symbol, count) if parse_iso(bar.as_of) <= now]

    def close(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        settled = self._settled(symbol, 5)
        if not settled:
            raise PriceError(f"no settled close for {symbol}")
        return settled[-1]

    def history(self, asset: dict, start: date | None = None) -> History:
        """Settled daily closes from `start` (else the last 30 bars); Naver gives no corporate actions."""
        count = NAVER_HISTORY_BARS
        if start is not None:
            today = self._clock().date()
            weekdays = sum(1 for n in range((today - start).days + 1) if (start + timedelta(days=n)).weekday() < 5)
            count = max(NAVER_HISTORY_BARS, weekdays + 10)
        bars = self._settled(asset["price_source"]["symbol"], count)
        if start is not None:
            bars = [bar for bar in bars if bar.trading_date >= start.isoformat()]
        return History(bars, [], Session("fixed", fixed_utc=NAVER_CLOSE_UTC[:5]), "KRW")


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

    def history(self, asset: dict, start: date | None = None) -> History:
        return self._provider(asset).history(asset, start)


class FixedPrices:
    """Quotes the same value for every asset, stamped at `now`. Used by dry runs."""

    def __init__(self, value: float, now: datetime):
        self.value, self.now = value, now

    def quote(self, asset: dict) -> Quote:
        return Quote(self.value, asset["currency"], iso(self.now), "fixed")

    def close(self, asset: dict) -> Quote:
        return self.quote(asset)

    def history(self, asset: dict, start: date | None = None) -> History:
        return History([self.quote(asset)], [], None, asset["currency"])


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
