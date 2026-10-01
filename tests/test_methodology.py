from engine.errors import E_SEMANTIC
from engine.methodology import check_publish, check_view_methodology, scope_gaps
from tests.util import methodology_payload, view_payload


def paths(errors):
    return {e.path for e in errors}


def test_publish_new(state):
    assert check_publish(state, "john.research", methodology_payload(id="deep-value-screen", name="Deep Value Screen")) == []


def test_publish_near_duplicate_rejected(state):
    errors = check_publish(state, "john.research", methodology_payload(id="event-catalysts", name="Event Catalysts"))
    assert errors[0].code == E_SEMANTIC and errors[0].path == "/payload/id"
    assert "event-catalyst" in errors[0].message


def test_owner_can_publish_a_new_version(state):
    assert check_publish(state, "arthur.val", methodology_payload(summary="Revised summary of the method")) == []


def test_cannot_update_someone_elses(state):
    errors = check_publish(state, "john.research", methodology_payload())
    assert paths(errors) == {"/payload/id"} and "belongs to" in errors[0].message


def test_publish_internal_consistency(state):
    payload = methodology_payload(
        id="quality-screen", name="Quality Screen",
        criteria=[{"id": "c1", "text": "first"}, {"id": "c1", "text": "second"}],
        scope={**methodology_payload()["scope"], "horizon_months": {"min": 24, "max": 6}},
    )
    errors = check_publish(state, "john.research", payload)
    assert paths(errors) == {"/payload/criteria", "/payload/scope/horizon_months"}


def test_view_fit_ok(state):
    assert check_view_methodology(state, view_payload()) == []


def test_view_fit_must_cover_criteria_exactly_once(state):
    fit = [
        {"criterion": "c1-dated-event", "assessment": "met", "note": "first"},
        {"criterion": "c1-dated-event", "assessment": "met", "note": "again"},
        {"criterion": "c9-unknown", "assessment": "unmet", "note": "not a criterion"},
    ]
    messages = [e.message for e in check_view_methodology(state, view_payload(methodology_fit=fit))]
    assert len(messages) == 3
    assert "not addressed: c2-asymmetric" in messages[0]
    assert "c9-unknown" in messages[1]
    assert "more than once: c1-dated-event" in messages[2]


def test_view_unknown_methodology(state):
    assert paths(check_view_methodology(state, view_payload(methodology="no-such-method"))) == {"/payload/methodology"}


def test_scope_gaps(state):
    method = state.methodologies["event-catalyst"]
    assert scope_gaps(method, state.assets["nvda"], 18) == []
    assert scope_gaps(method, state.assets["nvda"], 30) == ["horizon"]
    assert scope_gaps(method, state.assets["xom"], 18) == ["sector"]


def test_scope_exception_required_only_when_outside_scope(state):
    outside = check_view_methodology(state, view_payload(idea="xom-lng-2027"))
    assert paths(outside) == {"/payload/scope_exception"} and "sector" in outside[0].message
    explained = view_payload(idea="xom-lng-2027", scope_exception="LNG contract award is a dated event like the tech cases")
    assert check_view_methodology(state, explained) == []
    needless = check_view_methodology(state, view_payload(scope_exception="not needed"))
    assert paths(needless) == {"/payload/scope_exception"} and "remove" in needless[0].message
