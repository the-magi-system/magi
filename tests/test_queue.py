from engine.queue import BOT_LOGIN, body_sha, decide, engine_replies
from engine.reply import render

AUTHOR = {"id": 80214090, "login": "ThinkwChivalri"}
OTHER = {"id": 1001, "login": "john-example"}
BOT = {"id": 41898282, "login": BOT_LOGIN}
MAINTAINERS = {80214090}
PRICE_ERROR = {"code": "E_PRICE", "path": "", "message": "outage", "retryable": True}
SCHEMA_ERROR = {"code": "E_SCHEMA", "path": "/payload", "message": "bad", "retryable": True}


def issue(text="proposal body"):
    return {"number": 5, "body": text, "user": AUTHOR, "created_at": "2026-10-02T00:00:00Z"}


def comment(user, text, minute):
    return {"user": user, "body": text, "created_at": f"2026-10-02T00:{minute:02d}:00Z"}


def reply(status, minute, text="proposal body", errors=()):
    result = {"status": status, "issue": 5, "body_sha": body_sha(text), "errors": list(errors)}
    return comment(BOT, render(result, []), minute)


def test_body_sha_ignores_crlf_and_bom():
    assert body_sha("a\r\nb") == body_sha("\ufeffa\nb") and len(body_sha("x")) == 16


def test_render_round_trips_through_engine_replies():
    result = {"status": "accepted", "issue": 5, "body_sha": "abc", "errors": [], "created": {"idea_id": "x"}}
    assert engine_replies([comment(BOT, render(result, []), 1)]) == [{"created_at": "2026-10-02T00:01:00Z", **result}]


def test_new_issue_is_processed():
    assert decide(issue(), [], MAINTAINERS).kind == "process"


def test_processed_issue_is_skipped():
    assert decide(issue(), [reply("rejected", 1, errors=[SCHEMA_ERROR])], MAINTAINERS).kind == "skip"


def test_edited_body_is_reprocessed():
    assert decide(issue("new body"), [reply("rejected", 1, errors=[SCHEMA_ERROR])], MAINTAINERS).kind == "process"


def test_retry_only_by_author():
    base = [reply("rejected", 1, errors=[SCHEMA_ERROR])]
    assert decide(issue(), base + [comment(OTHER, "/retry", 2)], MAINTAINERS).kind == "skip"
    assert decide(issue(), base + [comment(AUTHOR, "/retry", 3)], MAINTAINERS).kind == "process"


def test_approval_by_maintainer_only():
    base = [reply("needs_approval", 1)]
    assert decide(issue(), base + [comment(OTHER, "/approve", 2)], MAINTAINERS).kind == "skip"
    approved = decide(issue(), base + [comment(OTHER, "/approve", 2), comment(AUTHOR, "/approve", 3)], MAINTAINERS)
    assert (approved.kind, approved.note) == ("approve", "ThinkwChivalri")


def test_reject_carries_reason():
    decision = decide(issue(), [reply("needs_approval", 1), comment(AUTHOR, "/reject duplicate of take-private", 2)], MAINTAINERS)
    assert (decision.kind, decision.note) == ("reject", "duplicate of take-private")


def test_approval_before_request_is_ignored():
    assert decide(issue(), [comment(AUTHOR, "/approve", 1), reply("needs_approval", 2)], MAINTAINERS).kind == "skip"


def test_price_retries_stop_after_three():
    replies = [reply("rejected", minute, errors=[PRICE_ERROR]) for minute in (1, 2, 3)]
    assert decide(issue(), replies[:1], MAINTAINERS).kind == "process"
    assert decide(issue(), replies[:2], MAINTAINERS).kind == "process"
    assert decide(issue(), replies, MAINTAINERS).kind == "skip"


def test_comment_marker_from_other_user_is_ignored():
    fake = comment(OTHER, render({"status": "accepted", "issue": 5, "body_sha": body_sha("proposal body"), "errors": []}, []), 1)
    assert engine_replies([fake]) == [] and decide(issue(), [fake], MAINTAINERS).kind == "process"


def test_summaries():
    assert "Accepted" in render({"status": "accepted", "action": "create_idea", "actor": "a.b", "commit": "abc"}, [])
    assert "@ThinkwChivalri" in render({"status": "needs_approval", "approval_reasons": ["add_strategy:always"]}, ["ThinkwChivalri"])
    assert "cannot be retried" in render({"status": "rejected", "errors": [{"retryable": False}]}, [])
    assert "/retry" in render({"status": "rejected", "errors": [{"retryable": True}]}, [])
    assert "Received" in render({"status": "received"}, ["ThinkwChivalri"])
