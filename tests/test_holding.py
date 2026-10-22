"""Minimum holding period and re-entry interval (protocol section 10, design decision D44)."""
from datetime import timedelta

from engine.apply import apply_proposal, write_changes
from engine.errors import E_SEMANTIC
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.semantic import check_semantics
from engine.timeutil import iso, parse_iso
from engine.validate import validate
from engine.yamlio import write_yaml
from tests.fakes import FakePrices
from tests.util import ARTHUR_ID, JOHN_ID, T0, body, view_payload

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
OPENED_AT = parse_iso("2026-10-01T02:30:00Z")
UNTIL = "2026-10-31T02:30:00Z"
DAY = timedelta(days=1)


def check(repo, payload, now, actor="arthur.val", author=ARTHUR_ID):
    return validate(RepoState.load(repo), body("update_view", actor, payload), author, now=now)


def write(repo, payload, now, actor="arthur.val", action="update_view"):
    state = RepoState.load(repo)
    changes = apply_proposal(state, Proposal(action, actor, payload), issue=80, owner=actor.split(".")[0], now=now,
                             prices=FakePrices(as_of=iso(now)))
    write_changes(repo, changes)


def locked(result, until):
    return [(e.code, e.path) for e in result.errors] == [(E_SEMANTIC, "/payload/position")] \
        and until in result.errors[0].message


def test_closing_within_30_days_is_rejected_and_the_reply_names_the_first_moment(repo):
    assert locked(check(repo, view_payload(position="neutral"), OPENED_AT + 29 * DAY), UNTIL)
    assert locked(check(repo, view_payload(position="short"), OPENED_AT + 30 * DAY - timedelta(seconds=1)), UNTIL)


def test_closing_after_exactly_30_days_is_accepted(repo):
    assert check(repo, view_payload(position="neutral"), OPENED_AT + 30 * DAY).status == "ok"


def test_a_flip_after_30_days_starts_a_new_lock(repo):
    flipped = OPENED_AT + 31 * DAY
    write(repo, view_payload(position="short"), flipped)
    assert locked(check(repo, view_payload(position="neutral"), flipped + 29 * DAY), iso(flipped + 30 * DAY))
    assert check(repo, view_payload(position="neutral"), flipped + 30 * DAY).status == "ok"


def test_reentry_within_30_days_of_closing_is_rejected(repo):
    closed = OPENED_AT + 40 * DAY
    write(repo, view_payload(position="neutral"), closed)
    assert locked(check(repo, view_payload(), closed + 15 * DAY), iso(closed + 30 * DAY))
    assert check(repo, view_payload(), closed + 30 * DAY).status == "ok"


def test_every_idea_on_the_same_asset_shares_the_lock(repo):
    for idea_id, asset_id in [("nvda-second-look", "nvda"), ("msft-cloud-2027", "msft")]:
        write_yaml(repo / "ideas" / idea_id / "idea.yaml", {
            "schema": "magi/idea@1", "id": idea_id, "asset": asset_id, "title": idea_id, "summary": "Test idea",
            "status": "active", "created_by": "arthur.val", "created_at": T0,
        })
    now = OPENED_AT + 10 * DAY
    assert locked(check(repo, view_payload(idea="nvda-second-look"), now), UNTIL)
    assert check(repo, view_payload(idea="nvda-second-look", position="neutral"), now).status == "ok"
    assert check(repo, view_payload(idea="msft-cloud-2027"), now).status == "ok"


def test_changes_that_keep_the_direction_are_accepted_during_the_lock(repo):
    now = OPENED_AT + DAY
    assert check(repo, view_payload(confidence=0.5, rationale="Lower confidence"), now).status == "ok"
    assert check(repo, view_payload(position="neutral"), now, actor="john.research", author=JOHN_ID).status == "ok"


def test_retirement_is_not_held_by_the_lock(repo):
    proposal = Proposal("retire_agent", "arthur", {"agent": "arthur.val", "reason": "Replaced"})
    assert check_semantics(RepoState.load(repo), proposal, OPENED_AT + DAY) == ([], [])


def test_a_correction_does_not_lift_the_lock_before_plan_8(repo):
    write(repo, {"corrects": OPENED, "reason": "Opened by mistake", "fields": {"void": True}}, OPENED_AT + 2 * DAY,
          actor="arthur", action="ledger_correction")
    assert locked(check(repo, view_payload(position="neutral"), OPENED_AT + 5 * DAY), UNTIL)
