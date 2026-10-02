import json

import engine.cli as cli
from engine.market import latest_closes, read_closes, record_closes
from engine.prices import Quote
from tests.fakes import NOW, FakePrices


class SydneyPrices(FakePrices):
    """Closes stamped at the session open, 23:00 UTC on the previous calendar day."""

    def close(self, asset: dict) -> Quote:
        quote = self.quote(asset)
        return Quote(quote.value, quote.currency, "2026-09-30T23:00:00Z", quote.source, "2026-10-01")


def test_close_is_dated_by_the_exchange_day(repo):
    added, _ = record_closes(repo, SydneyPrices(), NOW)
    assert {line["date"] for line in added} == {"2026-10-01"}
    assert (repo / "market" / "prices" / "2026" / "10.jsonl").exists()
    assert not (repo / "market" / "prices" / "2026" / "09.jsonl").exists()


def test_record_closes_appends_lines(repo):
    added, failures = record_closes(repo, FakePrices({"NVDA": 181.0}), NOW)
    assert failures == [] and sorted(line["asset"] for line in added) == ["msft", "nvda", "xom"]
    lines = (repo / "market" / "prices" / "2026" / "10.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[1])
    assert first == {"date": "2026-10-02", "asset": "nvda", "close": 181.0, "currency": "USD", "source": "fake",
                     "as_of": "2026-10-02T03:00:00Z", "recorded_at": "2026-10-02T03:00:00Z"}


def test_same_day_is_not_recorded_twice(repo):
    record_closes(repo, FakePrices(), NOW)
    added, _ = record_closes(repo, FakePrices(), NOW)
    assert added == [] and len(read_closes(repo)) == 3


def test_failures_are_reported_not_fatal(repo):
    added, failures = record_closes(repo, FakePrices(fail={"MSFT"}), NOW)
    assert len(added) == 2 and failures[0]["asset"] == "msft" and "MSFT" in failures[0]["message"]


def test_latest_closes_picks_the_newest_date(repo):
    record_closes(repo, FakePrices({"NVDA": 100.0}, as_of="2026-09-30T20:00:00Z"), NOW)
    record_closes(repo, FakePrices({"NVDA": 110.0}), NOW)
    latest = latest_closes(repo)["nvda"]
    assert (latest["date"], latest["close"]) == ("2026-10-02", 110.0)


def test_cli_prices_commits_only_new_lines(monkeypatch, repo):
    calls = []

    class StubGit:
        def __init__(self, root):
            pass

        def commit(self, subject, trailers):
            calls.append(subject)
            return "sha"

        def push(self):
            calls.append("push")

    monkeypatch.setattr(cli, "Git", StubGit)
    monkeypatch.setattr(cli, "PriceRouter", lambda: FakePrices())
    monkeypatch.setattr(cli, "utc_now", lambda: NOW)
    assert cli.main(["prices", "--repo", str(repo)]) == 0
    assert calls == ["chore: record daily closes for 3 asset(s)", "push"]
    assert cli.main(["prices", "--repo", str(repo)]) == 0
    assert calls == ["chore: record daily closes for 3 asset(s)", "push"]
