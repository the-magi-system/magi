import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from engine.errors import E_PRICE, E_PRICE_STALE
from engine.prices import FixedPrices, PriceError, Quote, YahooProvider, fetch
from engine.timeutil import iso, parse_iso, stamp
from tests.fakes import NOW, FakePrices

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


def test_fixed_prices():
    assert FixedPrices(50.0, NOW).quote(NVDA) == Quote(50.0, "USD", iso(NOW), "fixed")
