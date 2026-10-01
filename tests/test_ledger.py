from engine.ledger import closed_event, event_path, load_book, opened_event, pick_id, realized_return
from engine.prices import Quote
from engine.timeutil import iso
from engine.yamlio import write_yaml
from tests.fakes import NOW

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"


def test_book_from_fixture(repo):
    book = load_book(repo)
    pick = book.open[("arthur.val", "nvda-ai-capex-2026")]
    assert (pick.pick_id, pick.direction, pick.entry_price, pick.opened_at) == ("pk-000001", "long", 180.2, "2026-10-01T02:30:00Z")
    assert book.next_number == 2 and book.paths == {OPENED}


def test_closed_pick_is_not_open(repo):
    write_yaml(repo / "ledger/events/2026/10/20261002T030000Z-pk-000001-pick_closed.yaml",
               {"schema": "magi/ledger-event@1", "event": "pick_closed", "pick_id": "pk-000001",
                "actor": "arthur.val", "idea": "nvda-ai-capex-2026", "direction": "long"})
    book = load_book(repo)
    assert book.open == {} and book.next_number == 2


def test_event_path_avoids_collisions():
    first = event_path(NOW, "pk-000002", "pick_opened", set())
    assert first == "ledger/events/2026/10/20261002T030000Z-pk-000002-pick_opened.yaml"
    assert event_path(NOW, "pk-000002", "pick_opened", {first}) == first.replace(".yaml", "-2.yaml")
    assert pick_id(123) == "pk-000123"


def test_realized_return():
    assert realized_return("long", 100.0, 120.0) == 0.2
    assert realized_return("short", 100.0, 120.0) == -0.2


def test_closed_event_fields(repo):
    pick = load_book(repo).open[("arthur.val", "nvda-ai-capex-2026")]
    event = closed_event(pick=pick, now=NOW, quote=Quote(200.0, "USD", iso(NOW), "fake"),
                         reason="position_change", issue=7, view_version=2)
    assert event["event"] == "pick_closed" and event["realized_return"] == round(200.0 / 180.2 - 1, 6)
    assert event["entry_price"] == 180.2 and event["duration_days"] == 1 and event["view_version"] == 2


def test_opened_event_fields():
    event = opened_event(pick_id="pk-000009", actor="john.research", idea="nvda-ai-capex-2026", direction="short",
                         now=NOW, quote=Quote(150.0, "USD", iso(NOW), "fake"), view_version=1,
                         original={"p50": 140, "expected_price": 141.0, "horizon_months": 12}, issue=8)
    assert event["event"] == "pick_opened" and event["price"]["value"] == 150.0 and event["at"] == iso(NOW)
