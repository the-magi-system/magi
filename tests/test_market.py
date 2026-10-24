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


def _bar(day, value):
    return Quote(value, "USD", f"{day}T20:00:00Z", "yahoo", day)


def _history(days_values, actions=(), rejected=()):
    from engine.prices import History
    return History([_bar(day, value) for day, value in days_values], list(actions), None, "USD", list(rejected))


def _line(repo, day, value, asset="nvda"):
    path = repo / "market" / "prices" / day[:4] / f"{day[5:7]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"date": day, "asset": asset, "close": value, "currency": "USD", "source": "yahoo",
            "as_of": f"{day}T20:00:00Z", "recorded_at": f"{day}T23:00:00Z"}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")
    return path


def _nvda(repo):
    return sorted((line["date"], line["close"]) for line in read_closes(repo) if line["asset"] == "nvda")


DIVIDEND = {"date": "2026-09-10", "asset": "nvda", "kind": "dividend", "amount": 0.01, "currency": "USD",
            "source": "yahoo"}
SPLIT = {"date": "2026-09-15", "asset": "nvda", "kind": "split", "numerator": 2, "denominator": 1, "source": "yahoo"}


def test_every_missing_close_of_the_month_is_recorded(repo):
    from engine.market import record_market
    _line(repo, "2026-09-29", 180.0)
    history = _history([("2026-09-28", 179.0), ("2026-09-29", 180.0), ("2026-09-30", 181.0), ("2026-10-01", 182.0)])
    update = record_market(repo, FakePrices(histories={"NVDA": history}), NOW)
    assert sorted(line["date"] for line in update.closes if line["asset"] == "nvda") == \
        ["2026-09-28", "2026-09-30", "2026-10-01"]
    september = (repo / "market/prices/2026/09.jsonl").read_text(encoding="utf-8")
    october = (repo / "market/prices/2026/10.jsonl").read_text(encoding="utf-8")
    assert "2026-09-28" in september and "2026-09-30" in september and '"2026-10-01", "asset": "nvda"' in october
    assert _nvda(repo) == [("2026-09-28", 179.0), ("2026-09-29", 180.0), ("2026-09-30", 181.0), ("2026-10-01", 182.0)]


def test_corporate_actions_are_recorded_once(repo):
    from engine.market import read_actions, record_market
    prices = FakePrices(histories={"NVDA": _history([("2026-10-01", 182.0)], [DIVIDEND, SPLIT])})
    update = record_market(repo, prices, NOW)
    assert len(update.actions) == 2
    lines = (repo / "market/actions/2026/09.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{**DIVIDEND, "recorded_at": "2026-10-02T03:00:00Z"},
                                                    {**SPLIT, "recorded_at": "2026-10-02T03:00:00Z"}]
    assert record_market(repo, prices, NOW).actions == [] and len(read_actions(repo)) == 2


def test_an_overlapping_close_is_kept_and_only_a_difference_over_half_a_percent_is_reported(repo):
    from engine.market import record_market
    path = _line(repo, "2026-10-01", 100.0)
    before = path.read_text(encoding="utf-8")
    update = record_market(repo, FakePrices(histories={"NVDA": _history([("2026-10-01", 100.4)])}), NOW)
    assert update.findings == [] and path.read_text(encoding="utf-8").startswith(before)
    assert [c for c in update.closes if c["asset"] == "nvda"] == []
    after = path.read_text(encoding="utf-8")
    update = record_market(repo, FakePrices(histories={"NVDA": _history([("2026-10-01", 100.6)])}), NOW)
    assert [(f.path, f.owner) for f in update.findings] == [("market/prices/2026/10.jsonl", "melchior.magi")]
    assert path.read_text(encoding="utf-8") == after and _nvda(repo) == [("2026-10-01", 100.0)]


def test_conflicting_action_data_is_reported_and_not_appended(repo):
    from engine.market import read_actions, record_market
    path = repo / "market/actions/2026/09.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({**SPLIT, "recorded_at": "2026-09-16T23:00:00Z"}) + "\n", encoding="utf-8")
    prices = FakePrices(histories={"NVDA": _history([("2026-10-01", 182.0)], [{**SPLIT, "numerator": 3}])})
    update = record_market(repo, prices, NOW)
    assert update.actions == [] and len(read_actions(repo)) == 1
    assert [(f.path, f.owner) for f in update.findings] == [("market/actions/2026/09.jsonl", "melchior.magi")]
    odd = {"date": "2026-09-20", "asset": "msft", "kind": "split", "numerator": 1.5, "denominator": 1.0,
           "source": "yahoo", "reason": "the split ratio is not a ratio of whole numbers"}
    prices = FakePrices(histories={"NVDA": _history([("2026-10-01", 182.0)], [{**SPLIT, "numerator": 3}]),
                                   "MSFT": _history([("2026-10-01", 400.0)], rejected=[odd])})
    update = record_market(repo, prices, NOW)
    assert len(update.findings) == 2 and all(f.owner == "melchior.magi" for f in update.findings)
    assert update.findings[1].path == "market/actions/2026/09.jsonl"


def test_missed_days_are_filled_by_the_next_run(repo):
    from engine.market import record_market
    first = [("2026-09-28", 1.0), ("2026-09-29", 2.0), ("2026-09-30", 3.0), ("2026-10-01", 4.0)]
    record_market(repo, FakePrices(histories={"NVDA": _history(first)}), NOW)
    later = first + [("2026-10-02", 5.0), ("2026-10-05", 6.0), ("2026-10-06", 7.0)]
    update = record_market(repo, FakePrices(histories={"NVDA": _history(later)}), NOW)
    assert [line["date"] for line in update.closes if line["asset"] == "nvda"] == \
        ["2026-10-02", "2026-10-05", "2026-10-06"]


def test_cli_prices_reports_findings_in_an_audit_issue(monkeypatch, repo):
    _line(repo, "2026-10-01", 100.0)
    reports = []

    class StubGit:
        def __init__(self, root):
            pass

        def commit(self, subject, trailers):
            return "sha"

        def push(self):
            pass

    monkeypatch.setattr(cli, "Git", StubGit)
    monkeypatch.setattr(cli, "GitHubClient", type("Client", (), {"from_env": staticmethod(lambda: "gh")}))
    monkeypatch.setattr(cli, "report", lambda gh, title, findings: reports.append((gh, title, findings)) or 7)
    monkeypatch.setattr(cli, "PriceRouter",
                        lambda: FakePrices(histories={"NVDA": _history([("2026-10-01", 101.0)])}))
    monkeypatch.setattr(cli, "utc_now", lambda: NOW)
    assert cli.main(["prices", "--repo", str(repo)]) == 0
    assert [(gh, title, len(findings)) for gh, title, findings in reports] == [("gh", "Price data found problems", 1)]
