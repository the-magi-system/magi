"""Declared style against actual views (design 19.8)."""
from engine.apply import apply_proposal, write_changes
from engine.behaviour import actor_behaviour, all_behaviour
from engine.proposal import Proposal
from engine.repo import RepoState
from tests.fakes import NOW, FakePrices
from tests.util import non_public_evidence_payload, view_payload


def _apply(repo, action, actor, payload):
    state = RepoState.load(repo)
    owner = state.agents[actor]["owner"]
    write_changes(repo, apply_proposal(state, Proposal(action, actor, payload), issue=70, owner=owner, now=NOW,
                                       prices=FakePrices({"NVDA": 180.2, "XOM": 110.0})))


def test_declared_style_is_set_against_the_current_views(repo):
    _apply(repo, "update_view", "john.research", view_payload())
    _apply(repo, "update_view", "john.research", view_payload(idea="xom-lng-2027", position="short", horizon_months=6))
    stats = actor_behaviour(RepoState.load(repo), "john.research")
    assert stats["declared"]["sectors"] == ["information-technology", "communication-services"]
    assert (stats["views"], stats["horizon_months"]) == (2, {"min": 6, "median": 12.0, "max": 18})
    assert stats["positions"] == {"long": 1, "short": 1, "neutral": 0}
    assert stats["sectors"] == {"energy": 1, "information-technology": 1} and stats["views_outside_declared_sectors"] == 1
    assert stats["asset_types"] == {"equity": 2} and stats["views_outside_declared_asset_types"] == 0
    assert stats["methodologies"] == {"event-catalyst": 2} and stats["non_public_pillar_share"] == 0.0


def test_non_public_share_counts_flagged_pillars(repo):
    _apply(repo, "add_evidence", "john.research", non_public_evidence_payload())
    state = RepoState.load(repo)
    secret = next(e for e in state.evidence if e.endswith("channel-check"))
    pillars = [{"id": "launch", "claim": "The launch lands on time", "weight": 2, "evidence": [secret]},
               {"id": "ai-demand", "claim": "AI compute demand remains supply constrained", "weight": 3}]
    _apply(repo, "update_view", "john.research", view_payload(pillars=pillars))
    assert actor_behaviour(RepoState.load(repo), "john.research")["non_public_pillar_share"] == 0.5


def test_actors_with_a_profile_but_no_views_are_listed(repo):
    rows = {row["actor"]: row for row in all_behaviour(RepoState.load(repo))}
    assert set(rows) == {"arthur.val", "john.research"}
    assert (rows["arthur.val"]["views"], rows["arthur.val"]["horizon_months"]) == (0, None)
    assert rows["arthur.val"]["non_public_pillar_share"] is None
