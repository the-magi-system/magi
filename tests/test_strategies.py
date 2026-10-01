from engine.errors import E_SEMANTIC
from engine.strategies import (
    check_add_strategy, check_declaration, check_view_strategy, is_catch_all, normalize, too_close,
)

DEEP_VALUE = {"name": "Deep Value", "definition": "Assets priced well below liquidation value"}


def test_normalize():
    assert normalize("M&A-Arbitrage") == "maarbitrage"
    assert normalize("Spin_Off") == "spinoff"
    assert normalize("mergers and acquisitions") == "mergersacquisitions"


def test_too_close():
    assert too_close("spin-off", "spinoff")
    assert too_close("take-private", "takeprivate")
    assert too_close("special-sit", "special-situations")
    assert too_close("compounder", "compunder")
    assert not too_close("value", "quality")


def test_synonyms_are_not_caught():
    # Documented limit (spec 5.6): spelling variants only; maintainers resolve synonyms.
    assert not too_close("merger-arb", "m-and-a-arb")


def test_catch_all():
    assert is_catch_all("other")
    assert is_catch_all("Misc Ideas")
    assert is_catch_all("catch-all")
    assert not is_catch_all("special-sit")


def test_first_declaration_accepted(state):
    assert check_declaration(state.strategies, "john.research", {"strategies": {"deep-value": DEEP_VALUE}}) == []


def test_second_declaration_rejected(state):
    errors = check_declaration(state.strategies, "arthur.val", {"strategies": {"deep-value": DEEP_VALUE}})
    assert errors[0].code == E_SEMANTIC and errors[0].path == "/action" and "one-time" in errors[0].message


def test_declaration_near_duplicate_rejected(state):
    payload = {"strategies": {"special-situations": {"name": "Special Situations Plus", "definition": "Event-driven ideas of any kind"}}}
    errors = check_declaration(state.strategies, "john.research", payload)
    assert errors[0].path == "/payload/strategies/special-situations"
    assert "special-sit" in errors[0].message


def test_declaration_catch_all_rejected(state):
    payload = {"strategies": {"other": {"name": "Other", "definition": "Anything that fits nowhere else"}}}
    assert "catch-all" in check_declaration(state.strategies, "john.research", payload)[0].message


def test_declaration_entries_checked_against_each_other(state):
    payload = {"strategies": {"deep-value": DEEP_VALUE, "deepvalue": {"name": "Deepvalue", "definition": "Same thing spelled differently"}}}
    errors = check_declaration(state.strategies, "john.research", payload)
    assert [e.path for e in errors] == ["/payload/strategies/deepvalue"]


def test_declaration_sub_strategies_checked_within_parent(state):
    subs = {"spin-off": {"name": "Spin-off", "definition": "New listed company carved out"},
            "spinoff": {"name": "Spinoff", "definition": "Same thing spelled differently"}}
    payload = {"strategies": {"event-driven": {"name": "Event Driven", "definition": "Corporate events drive the return", "subs": subs}}}
    errors = check_declaration(state.strategies, "john.research", payload)
    assert [e.path for e in errors] == ["/payload/strategies/event-driven/subs/spinoff"]


def test_add_requires_prior_declaration(state):
    errors = check_add_strategy(state.strategies, "john.research", {"strategy": {"id": "deep-value", **DEEP_VALUE}})
    assert "declare_strategies" in errors[0].message


def test_add_sub_to_existing_parent(state):
    ok = {"parent": "special-sit", "sub": {"id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}}
    clash = {"parent": "special-sit", "sub": {"id": "mergerarb", "name": "Merger Arb", "definition": "Deal spread capture"}}
    missing = {"parent": "no-such", "sub": ok["sub"]}
    assert check_add_strategy(state.strategies, "arthur.val", ok) == []
    assert check_add_strategy(state.strategies, "arthur.val", clash)[0].path == "/payload/sub"
    assert check_add_strategy(state.strategies, "arthur.val", missing)[0].path == "/payload/parent"


def test_add_top_level(state):
    assert check_add_strategy(state.strategies, "arthur.val", {"strategy": {"id": "deep-value", **DEEP_VALUE}}) == []
    clash = {"strategy": {"id": "quality", "name": "Quality", "definition": "High quality businesses only"}}
    assert "quality-compounder" in check_add_strategy(state.strategies, "arthur.val", clash)[0].message


def test_view_strategy_rules(state):
    cat = state.strategies
    assert check_view_strategy(cat, "special-sit", "take-private") == []
    assert check_view_strategy(cat, "quality-compounder", None) == []
    missing_sub = check_view_strategy(cat, "special-sit", None)
    assert missing_sub[0].path == "/payload/sub_strategy" and "merger-arb" in missing_sub[0].message
    assert "no sub-strategies" in check_view_strategy(cat, "quality-compounder", "x")[0].message
    assert "is not a sub-strategy" in check_view_strategy(cat, "special-sit", "spin-off")[0].message
    deprecated = check_view_strategy(cat, "legacy-event", None)
    assert "deprecated" in deprecated[0].message and "special-sit" in deprecated[0].message
    assert check_view_strategy(cat, "unknown", None)[0].path == "/payload/strategy"
