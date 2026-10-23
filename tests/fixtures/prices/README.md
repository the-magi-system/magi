# Recorded price responses

These are real responses from the two public price endpoints the engine uses, recorded once so that `tests/test_price_history.py` runs without network access (plan 8, Task 6). They are third-party prices: they are not covered by the repository's licences and remain subject to their sources' terms (protocol section 14).

| File | Request | What it covers |
|---|---|---|
| `yahoo-nvda-2024-split.json` | `https://query1.finance.yahoo.com/v8/finance/chart/NVDA?period1=1709251200&period2=1792744716&interval=1d&events=div%2Csplits` | Daily bars from 2024-03-01 to 2026-10-22, with the 10-for-1 split of 2024-06-10 and every dividend since March 2024 |
| `yahoo-tem-1mo.json` | `https://query1.finance.yahoo.com/v8/finance/chart/TEM?range=1mo&interval=1d&events=div%2Csplits` | A month without corporate actions, 2026-09-23 to 2026-10-22 |
| `yahoo-btc-usd-1mo.json` | `https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?range=1mo&interval=1d&events=div%2Csplits` | A crypto asset, one bar per UTC day, 2026-09-23 to 2026-10-23 |
| `naver-005930.xml` | `https://fchart.stock.naver.com/sise.nhn?symbol=005930&timeframe=day&count=30&requestType=0` | A Naver response of 30 daily bars, 2026-09-08 to 2026-10-23 |

All four were recorded by the maintainer at 2026-10-23T08:38:36Z (`period2` above), with the engine's `USER_AGENT` (`Mozilla/5.0 (compatible; magi-engine)`), which carries no contact details. At that moment the sessions of NVDA and TEM for 2026-10-22 and of 005930 for 2026-10-23 had closed, and the UTC day of 2026-10-23 was still trading for BTC-USD, so the last BTC-USD bar is unsettled.

Facts these files show:

- Yahoo stamps each daily bar and each corporate action at the start of the session in UTC (13:30Z for TEM in October); `meta.gmtoffset` gives the exchange's own date.
- `meta` carries `instrumentType` (`EQUITY` for NVDA and TEM, `CRYPTOCURRENCY` for BTC-USD), `exchangeTimezoneName` (`America/New_York`, `UTC`) and `currentTradingPeriod` for the current session only; a daily response has no `tradingPeriods`.
- A response for a range without corporate actions has no `events` key.
- Closes and dividend amounts are adjusted for later splits: NVDA's close of 2024-06-07 is given as 120.888 (as traded, about 1,208.88) and the dividend of 2024-03-05 as 0.004 (0.04 was paid).
- A split is given as floats, `numerator: 10.0`, `denominator: 1.0`, with `splitRatio: "10:1"`.
