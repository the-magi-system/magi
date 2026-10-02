# Price sources by market

Operating knowledge supplied by data provider `arthur` and approved for The Magi System on 2026-10-02 (design section 16.4). It records what has been observed to work. Verify a source before relying on it for a market that is not listed here.

## Default: the Yahoo Finance chart API

- Endpoint: `https://query1.finance.yahoo.com/v8/finance/chart/<symbol>?range=5d&interval=1d`. Send a User-Agent header; requests without one are rate-limited (HTTP 429). Never put personal information in request headers.
- `meta.regularMarketPrice` read during or just after a session is provisional. Two checks made the next day found the settled close 0.7% away from the captured value, once higher and once lower. For a daily close, read the last bar of `indicators.quote[0].close`, and confirm with `meta.regularMarketTime` that the session has ended.
- Before the open, `meta.regularMarketPrice` is still the previous session's close. `meta.chartPreviousClose` and `meta.regularMarketTime` show which session a number belongs to. Date a price by the market's own timestamp, never by the local clock: a machine at UTC+8 changes date while New York is still trading.
- Yahoo records some spin-offs as splits (one spin-off appeared as a 15:10 split), which silently divides all earlier prices. Check `?events=split|div` before building any historical price series.
- Some sites refuse automated requests; stockanalysis.com answered HTTP 403.

## Symbols and units

| Market | Yahoo suffix | Notes |
|---|---|---|
| United States, including OTC | none | |
| Tokyo | `.T` | |
| Taiwan, TWSE-listed | `.TW` | |
| Taiwan, TPEx-listed | `.TWO` | not `.T` or `.TW` |
| London | `.L` | quoted in pence (GBp), not pounds |
| Australia | `.AX` | |
| Stockholm | `.ST` | |
| Warsaw | `.WA` | |
| Toronto | `.TO` | Canadian dollars |
| Hong Kong | `.HK` | |
| Germany, XETRA | `.DE` | see below |
| Korea | `.KS`, `.KQ` | do not use for closes; see below |

## Korea: Naver Finance

Yahoo's `.KS` and `.KQ` closes disagreed with the Korea Exchange on all 8 trading days checked in September 2026. Use Naver Finance daily bars instead:

`https://fchart.stock.naver.com/sise.nhn?symbol=<6-digit code>&timeframe=day&count=5&requestType=0`

Each bar is an element `<item data="YYYYMMDD|open|high|low|close|volume" />`; the last one is the latest session. The Korea Exchange closes at 15:30 KST, which is 06:30 UTC.

## Germany: XETRA

The XETRA session runs from 07:00 to 15:30 UTC. The morning after, Yahoo's daily bar for the previous day can still have a null close. Take the 15:30 UTC closing-auction bar from `range=2d&interval=5m`, and confirm that it equals `meta.regularMarketPrice` and that `meta.regularMarketTime` is after 15:30 UTC.

## Holidays

During East Asian holidays, such as Japan's September holidays and Korea's Chuseok, the latest close can be several days old. Check the timestamp against the exchange calendar before attaching a date to a price. When one run covers several markets, record each market's own last trading date.

## Low-priced shares

Rounding to two decimals distorts shares priced below two currency units by 0.3–1.4% (0.355 becomes 0.36). Store the value as quoted.

## Currencies

When a company reports in one currency and trades in another, for example reporting in USD and trading in GBp or CAD, every per-share comparison needs an explicit exchange-rate step taken on the same date as the price. The Bank of Canada Valet API (series `FXUSDCAD`) has served USD/CAD.
