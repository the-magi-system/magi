from engine.ledger import closed_event, event_path, load_book, opened_event, pick_id
from engine.prices import Quote
from engine.timeutil import iso
from engine.yamlio import write_yaml
from tests.fakes import NOW

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
SIGNAL = {"date": "2026-10-01", "value": 199.0, "currency": "USD", "as_of": "2026-10-01T13:30:00Z", "source": "yahoo"}


def test_book_from_fixture(repo):
    book = load_book(repo)
    pick = book.open[("arthur.val", "nvda-ai-capex-2026")]
    assert (pick.pick_id, pick.direction, pick.opened_at) == ("pk-000001", "long", "2026-10-01T02:30:00Z")
    assert not hasattr(pick, "entry_price")
    assert book.next_number == 2 and book.paths == {OPENED}


def test_closed_pick_is_not_open(repo):
    write_yaml(repo / "ledger/events/2026/10/20261002T030000Z-pk-000001-pick_closed.yaml",
               {"schema": "magi/ledger-event@1", "event": "pick_closed", "pick_id": "pk-000001",
                "actor": "arthur.val", "idea": "nvda-ai-capex-2026", "direction": "long", "at": "2026-10-02T03:00:00Z"})
    book = load_book(repo)
    assert book.open == {} and book.next_number == 2
    last = book.last_event[("arthur.val", "nvda-ai-capex-2026")]
    assert (last.at, last.pick_id, last.event) == ("2026-10-02T03:00:00Z", "pk-000001", "pick_closed")


def test_event_path_avoids_collisions():
    first = event_path(NOW, "pk-000002", "pick_opened", set())
    assert first == "ledger/events/2026/10/20261002T030000Z-pk-000002-pick_opened.yaml"
    assert event_path(NOW, "pk-000002", "pick_opened", {first}) == first.replace(".yaml", "-2.yaml")
    assert pick_id(123) == "pk-000123"


def test_closed_event_fields(repo):
    pick = load_book(repo).open[("arthur.val", "nvda-ai-capex-2026")]
    event = closed_event(pick=pick, now=NOW, quote=Quote(200.0, "USD", iso(NOW), "fake"),
                         signal_close=SIGNAL, reason="position_change", issue=7, view_version=2,
                         proposal_sha256="a" * 64)
    assert event["proposal_sha256"] == "a" * 64
    assert event["event"] == "pick_closed" and event["signal_close"] == SIGNAL and event["view_version"] == 2
    assert not {"entry_price", "realized_return", "duration_days"} & set(event)


def test_opened_event_fields():
    event = opened_event(pick_id="pk-000009", actor="john.research", idea="nvda-ai-capex-2026", direction="short",
                         now=NOW, quote=Quote(150.0, "USD", iso(NOW), "fake"), signal_close=SIGNAL, view_version=1,
                         original={"p50": 140, "expected_price": 141.0, "horizon_months": 12}, issue=8,
                         proposal_sha256="b" * 64)
    assert event["proposal_sha256"] == "b" * 64
    assert event["event"] == "pick_opened" and event["price"]["value"] == 150.0 and event["at"] == iso(NOW)
    assert event["signal_close"]["value"] == 199.0
