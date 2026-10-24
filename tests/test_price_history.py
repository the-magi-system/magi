"""Daily bars over a range, with dividends and splits, from recorded responses (protocol section 10, Market data)."""
import json
from datetime import date, datetime, timezone

from engine.prices import NaverProvider, YahooProvider
from tests.test_prices import NVDA, SAMSUNG, SequenceOpener, bars
from tests.util import REPO_ROOT

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "prices"
CLOCK = datetime(2026, 10, 23, 9, 0, 0, tzinfo=timezone.utc)
TEM = {"id": "tem", "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "TEM"}}
BTC = {"id": "btc-usd", "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "BTC-USD"}}


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def yahoo(*payloads):
    opener = SequenceOpener(payloads)
    return YahooProvider(opener=opener, clock=lambda: CLOCK), opener


def by_date(history):
    return {bar.market_date: bar for bar in history.bars}


def test_history_asks_for_a_month_with_dividends_and_splits():
    provider, opener = yahoo(fixture("yahoo-tem-1mo.json"), fixture("yahoo-tem-1mo.json"))
    provider.history(TEM)
    assert "range=1mo&interval=1d&events=div%2Csplits" in opener.requests[0].full_url
    provider.history(TEM, date(2024, 3, 1))
    assert f"period1=1709251200&period2={int(CLOCK.timestamp())}" in opener.requests[1].full_url


def test_closes_before_a_split_are_converted_back_to_as_traded():
    raw = json.loads(fixture("yahoo-nvda-2024-split.json"))["chart"]["result"][0]
    given = {datetime.fromtimestamp(ts - 14400, timezone.utc).strftime("%Y-%m-%d"): close
             for ts, close in zip(raw["timestamp"], raw["indicators"]["quote"][0]["close"])}
    provider, _ = yahoo(fixture("yahoo-nvda-2024-split.json"))
    closes = by_date(provider.history(NVDA, date(2024, 3, 1)))
    assert abs(closes["2024-06-07"].value - 1208.88) < 0.01
    assert closes["2024-06-10"].value == given["2024-06-10"] and closes["2026-10-22"].value == given["2026-10-22"]


def test_dividends_are_converted_back_to_as_traded():
    provider, _ = yahoo(fixture("yahoo-nvda-2024-split.json"))
    (march,) = [a for a in provider.history(NVDA, date(2024, 3, 1)).actions
                if a["kind"] == "dividend" and a["date"].startswith("2024-03")]
    assert abs(march["amount"] - 0.04) < 1e-6


def test_splits_are_recorded_with_numerator_and_denominator():
    from engine.prices import History
    provider, _ = yahoo(fixture("yahoo-nvda-2024-split.json"))
    history = provider.history(NVDA, date(2024, 3, 1))
    assert isinstance(history, History)
    split = {"date": "2024-06-10", "asset": "nvda", "kind": "split", "numerator": 10, "denominator": 1,
             "source": "yahoo"}
    (found,) = [a for a in history.actions if a["kind"] == "split"]
    assert found == split and type(found["numerator"]) is int and type(found["denominator"]) is int
    assert any(a["kind"] == "dividend" and a["date"] == "2024-03-05" for a in history.actions)
    response = json.loads(fixture("yahoo-nvda-2024-split.json"))
    for item in response["chart"]["result"][0]["events"]["splits"].values():
        item["numerator"] = 1.5
    provider, _ = yahoo(json.dumps(response).encode())
    history = provider.history(NVDA, date(2024, 3, 1))
    assert not [a for a in history.actions if a["kind"] == "split"]
    assert [r["date"] for r in history.rejected] == ["2024-06-10"]


def test_a_month_without_actions_returns_the_closes_as_given():
    raw = json.loads(fixture("yahoo-tem-1mo.json"))["chart"]["result"][0]
    provider, _ = yahoo(fixture("yahoo-tem-1mo.json"))
    history = provider.history(TEM)
    assert history.actions == []
    assert [bar.value for bar in history.bars] == [c for c in raw["indicators"]["quote"][0]["close"] if c is not None]
    closes = by_date(history)
    assert [closes[d].value for d in ("2026-10-20", "2026-10-21", "2026-10-22")] == \
        [66.75, 67.76000213623047, 63.810001373291016]


def test_the_last_bar_follows_the_close_rules():
    day = 1790060400  # 2026-09-22T07:00:00Z, the XETRA open
    xetra = {**NVDA, "currency": "EUR", "price_source": {"provider": "yahoo", "symbol": "AIXA.DE"}}
    trading = bars([day - 86400, day], [30.0, 30.5], "EUR",
                   currentTradingPeriod={"regular": {"start": day, "end": day + 30600}})
    provider = YahooProvider(opener=SequenceOpener([trading]),
                             clock=lambda: datetime.fromtimestamp(day + 3600, timezone.utc))
    assert [bar.value for bar in provider.history(xetra).bars] == [30.0]
    unclosed = bars([day - 86400, day], [30.0, None], "EUR")
    intraday = bars([day - 600, day + 30600, day + 30900], [29.0, 31.1, 31.2], "EUR")
    provider = YahooProvider(opener=SequenceOpener([unclosed, intraday]),
                             clock=lambda: datetime.fromtimestamp(day + 40000, timezone.utc))
    last = provider.history(xetra).bars[-1]
    assert (last.value, last.source, last.market_date) == (31.2, "yahoo-5m", "2026-09-22")


def test_close_is_the_last_bar_of_the_history():
    provider, opener = yahoo(fixture("yahoo-tem-1mo.json"), fixture("yahoo-tem-1mo.json"))
    close = provider.close(TEM)
    last = provider.history(TEM).bars[-1]
    assert close == last and close.market_date == last.market_date == "2026-10-22"
    assert "range=5d&interval=1d" in opener.requests[0].full_url


def test_session_close_comes_from_the_exchange_time_zone():
    provider, _ = yahoo(fixture("yahoo-tem-1mo.json"))
    session = provider.history(TEM).session
    assert (session.kind, session.timezone, session.close_local) == ("exchange", "America/New_York", "16:00")
    assert session.close_at("2026-10-20") == datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
    assert session.close_at("2026-11-06") == datetime(2026, 11, 6, 21, 0, tzinfo=timezone.utc)


def test_crypto_closes_at_midnight_utc():
    provider, _ = yahoo(fixture("yahoo-btc-usd-1mo.json"))
    history = provider.history(BTC)
    assert history.session.kind == "utc-day"
    assert history.session.close_at("2026-10-20") == datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)
    assert history.bars[-1].market_date == "2026-10-22"


def test_naver_history_has_no_actions_and_closes_at_0630z():
    opener = SequenceOpener([fixture("naver-005930.xml")])
    history = NaverProvider(opener=opener, clock=lambda: CLOCK).history(SAMSUNG)
    assert history.actions == [] and history.currency == "KRW"
    assert history.session.close_at("2026-10-23") == datetime(2026, 10, 23, 6, 30, tzinfo=timezone.utc)
    assert "count=30" in opener.requests[0].full_url
    assert history.bars[-1].market_date == "2026-10-23"
