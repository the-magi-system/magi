import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from engine.errors import E_PRICE, E_PRICE_STALE
from engine.prices import FixedPrices, NaverProvider, PriceError, PriceRouter, Quote, YahooProvider, fetch
from engine.schemas import validate_payload
from engine.timeutil import iso, parse_iso, stamp
from tests.fakes import NOW, FakePrices
from tests.util import REPO_ROOT

NVDA = {"id": "nvda", "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "NVDA"}}


def chart(price=180.2, ts=1790000000, currency="USD") -> bytes:
    meta = {"regularMarketPrice": price, "regularMarketTime": ts, "currency": currency}
    return json.dumps({"chart": {"result": [{"meta": meta}], "error": None}}).encode()


class Opener:
    def __init__(self, payload: bytes = b"", error: Exception | None = None):
        self.payload, self.error, self.requests = payload, error, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.payload)


def test_time_helpers():
    moment = datetime(2026, 10, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert iso(moment) == "2026-10-02T03:04:05Z"
    assert stamp(moment) == "20261002T030405Z"
    assert parse_iso(iso(moment)) == moment


def test_yahoo_parses_chart_response():
    opener = Opener(chart())
    quote = YahooProvider(opener=opener).quote(NVDA)
    assert quote == Quote(180.2, "USD", iso(datetime.fromtimestamp(1790000000, timezone.utc)), "yahoo")
    request = opener.requests[0]
    assert request.full_url.startswith("https://query1.finance.yahoo.com/v8/finance/chart/NVDA?")
    assert "magi" in request.get_header("User-agent")


def test_yahoo_encodes_special_symbols():
    opener = Opener(chart())
    for symbol, encoded in [("GC=F", "GC%3DF"), ("^GSPC", "%5EGSPC"), ("0700.HK", "0700.HK")]:
        YahooProvider(opener=opener).quote({**NVDA, "price_source": {"provider": "yahoo", "symbol": symbol}})
        assert f"/chart/{encoded}?" in opener.requests[-1].full_url


def test_yahoo_network_failure():
    with pytest.raises(PriceError, match="NVDA"):
        YahooProvider(opener=Opener(error=OSError("timed out"))).quote(NVDA)


def test_yahoo_unexpected_response():
    with pytest.raises(PriceError, match="unexpected"):
        YahooProvider(opener=Opener(json.dumps({"chart": {"result": None}}).encode())).quote(NVDA)


def test_fetch_fresh_quote():
    quote, error = fetch(FakePrices({"NVDA": 181.0}), NVDA, NOW)
    assert error is None and quote.value == 181.0


def test_fetch_stale_quote():
    quote, error = fetch(FakePrices(as_of=iso(NOW - timedelta(days=8))), NVDA, NOW)
    assert quote is None and error.code == E_PRICE_STALE


def test_fetch_outage():
    quote, error = fetch(FakePrices(fail={"NVDA"}), NVDA, NOW)
    assert quote is None and error.code == E_PRICE and error.retryable


def test_fetch_rejects_a_quote_of_zero_or_below():
    for value in (0.0, -1.0):
        quote, error = fetch(FakePrices({"NVDA": value}), NVDA, NOW)
        assert quote is None and error.code == E_PRICE and error.retryable


def test_fixed_prices():
    assert FixedPrices(50.0, NOW).quote(NVDA) == Quote(50.0, "USD", iso(NOW), "fixed")


SAMSUNG = {"id": "005930-ks", "currency": "KRW", "price_source": {"provider": "naver", "symbol": "005930"}}
XETRA = {"id": "aixa-de", "currency": "EUR", "price_source": {"provider": "yahoo", "symbol": "AIXA.DE"}}


class SequenceOpener:
    def __init__(self, payloads):
        self.payloads, self.requests = list(payloads), []

    def __call__(self, request, timeout):
        self.requests.append(request)
        return io.BytesIO(self.payloads.pop(0))


def bars(stamps, closes, currency="USD", **meta):
    result = {"meta": {"currency": currency, **meta}, "timestamp": stamps, "indicators": {"quote": [{"close": closes}]}}
    return json.dumps({"chart": {"result": [result], "error": None}}).encode()


def naver(*items):
    rows = "".join(f'<item data="{item}" />' for item in items)
    return ('<?xml version="1.0" encoding="EUC-KR" ?><protocol><chartdata symbol="005930">'
            f"{rows}</chartdata></protocol>").encode("euc-kr")


def test_yahoo_close_takes_last_settled_daily_bar():
    opener = SequenceOpener([bars([1790000000, 1790086400], [10.0, 12.5])])
    quote = YahooProvider(opener=opener).close(NVDA)
    assert quote == Quote(12.5, "USD", iso(datetime.fromtimestamp(1790086400, timezone.utc)), "yahoo")
    assert "range=5d&interval=1d" in opener.requests[0].full_url


def test_yahoo_close_falls_back_to_five_minute_bars():
    day = 1790060400
    opener = SequenceOpener([bars([day - 86400, day], [30.0, None], "EUR"),
                             bars([day - 600, day + 30600, day + 30900], [29.0, 31.1, 31.2], "EUR")])
    quote = YahooProvider(opener=opener).close(XETRA)
    assert (quote.value, quote.source, quote.currency) == (31.2, "yahoo-5m", "EUR")
    assert "range=2d&interval=5m" in opener.requests[1].full_url


def test_yahoo_close_without_any_close_fails():
    with pytest.raises(PriceError, match="no settled close"):
        YahooProvider(opener=SequenceOpener([bars([1790000000], [None]), bars([], [])])).close(NVDA)


def test_yahoo_close_skips_a_session_still_trading():
    day = 1790060400  # 2026-09-22T07:00:00Z, the XETRA open
    payload = bars([day - 86400, day], [30.0, 30.5], "EUR",
                   currentTradingPeriod={"regular": {"start": day, "end": day + 30600}})
    clock = lambda: datetime.fromtimestamp(day + 3600, timezone.utc)  # noqa: E731
    quote = YahooProvider(opener=SequenceOpener([payload]), clock=clock).close(XETRA)
    assert (quote.value, quote.market_date) == (30.0, "2026-09-21")


def test_yahoo_close_keeps_a_finished_session():
    day = 1790060400  # 2026-09-22T07:00:00Z
    ended = bars([day - 86400, day], [30.0, 30.5], "EUR",
                 currentTradingPeriod={"regular": {"start": day, "end": day + 30600}})
    evening = lambda: datetime.fromtimestamp(day + 40000, timezone.utc)  # noqa: E731  after the 15:30 close
    assert YahooProvider(opener=SequenceOpener([ended]), clock=evening).close(XETRA).value == 30.5
    upcoming = bars([day - 86400, day], [30.0, 30.5], "EUR",
                    currentTradingPeriod={"regular": {"start": day + 86400, "end": day + 86400 + 30600}})
    next_morning = lambda: datetime.fromtimestamp(day + 80000, timezone.utc)  # noqa: E731  before the next open
    assert YahooProvider(opener=SequenceOpener([upcoming]), clock=next_morning).close(XETRA).value == 30.5


def test_yahoo_close_dates_by_exchange_day():
    opens = 1790031600  # 2026-09-21T23:00:00Z, which is 10:00 on 22 September in Sydney (UTC+11)
    payload = bars([opens], [41.2], "AUD", gmtoffset=39600)
    quote = YahooProvider(opener=SequenceOpener([payload])).close({**NVDA, "currency": "AUD"})
    assert (quote.as_of, quote.market_date) == ("2026-09-21T23:00:00Z", "2026-09-22")


def test_naver_parses_last_daily_bar():
    payload = naver("20260930|60000|61000|59000|60500|1000", "20261001|60500|62000|60000|61800|1200")
    opener = SequenceOpener([payload, payload])
    provider = NaverProvider(opener=opener, clock=lambda: NOW)
    assert provider.quote(SAMSUNG) == Quote(61800.0, "KRW", "2026-10-01T06:30:00Z", "naver")
    close = provider.close(SAMSUNG)
    assert close == Quote(61800.0, "KRW", "2026-10-01T06:30:00Z", "naver") and close.market_date == "2026-10-01"
    assert "symbol=005930" in opener.requests[0].full_url


def test_naver_session_still_trading():
    payload = naver("20261001|60500|62000|60000|61800|1200", "20261002|61800|62500|61000|62100|300")
    provider = NaverProvider(opener=SequenceOpener([payload, payload]), clock=lambda: NOW)  # 12:00 in Seoul
    assert provider.quote(SAMSUNG) == Quote(62100.0, "KRW", iso(NOW), "naver")
    assert provider.close(SAMSUNG).as_of == "2026-10-01T06:30:00Z"


def test_naver_without_bars_fails():
    with pytest.raises(PriceError, match="no daily bars"):
        NaverProvider(opener=SequenceOpener([b"<protocol></protocol>"])).close(SAMSUNG)


def test_router_sends_each_asset_to_its_provider():
    router = PriceRouter({"yahoo": FakePrices({"NVDA": 1.0}), "naver": FakePrices({"005930": 2.0})})
    assert router.quote(NVDA).value == 1.0 and router.close(SAMSUNG).value == 2.0
    with pytest.raises(PriceError, match="no price provider"):
        router.quote({**NVDA, "price_source": {"provider": "bloomberg", "symbol": "NVDA"}})


def test_register_asset_accepts_naver():
    payload = {"id": "005930-ks", "name": "Samsung Electronics", "type": "equity", "sector": "information-technology",
               "currency": "KRW", "price_source": {"provider": "naver", "symbol": "005930"}}
    assert validate_payload(REPO_ROOT, "register_asset", payload) == []
