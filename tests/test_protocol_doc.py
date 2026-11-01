from engine.errors import RETRYABLE
from engine.schemas import known_actions
from tests.util import REPO_ROOT


def test_protocol_mentions_every_action_and_error_code_and_has_a_changelog():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    names = sorted(known_actions(REPO_ROOT) | set(RETRYABLE))
    assert [name for name in names if f"`{name}`" not in text] == []
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v1" in changelog


def test_protocol_describes_thread_issues_and_open_access():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "`magi:thread`" in text and "Idea Debate" not in text
    assert "**Any agent may take part.**" in text
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v1.1" in changelog


def test_agent_guide_is_complete_and_client_neutral():
    text = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    missing = [name for name in sorted(known_actions(REPO_ROOT)) if f"`{name}`" not in text]
    assert missing == []
    for needle in ["curl", "https://api.github.com/repos/the-magi-system/magi/issues", "request@1", "magi:thread", "/retry"]:
        assert needle in text, needle


def test_protocol_describes_profiles():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "**Profiles.**" in text and "`registry/profiles/<actor id>.yaml`" in text and "`risk_preference`" in text
    assert "`publish_profile`" in (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_protocol_describes_non_public_information():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["`access: non-public`", "`non_public_pillars`", "**Never submit** material non-public information",
                   "**Public means permanent.**", "`process_md`"]:
        assert needle in text, needle
    assert "access: non-public" in (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")


def test_changelog_records_v1_4():
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = changelog.split("## v1.3")[0]
    assert "## v1.4" in latest and "`publish_profile`" in latest and "`access: non-public`" in latest


def test_changelog_records_v1_5():
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = changelog.split("## v1.4")[0]
    assert "## v1.5" in latest and "Caspar.Magi" in latest and "`publish_judgement`" in latest
    assert "`input_commit`" in latest and "same GitHub account" in latest


def test_changelog_records_v1_6():
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = changelog.split("## v1.5")[0]
    for needle in ["## v1.6", "`target_date`", "two prices", "intrinsic value", "never treated as zero"]:
        assert needle in latest, needle


def test_protocol_describes_the_prediction_contract():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["**What a distribution predicts.**", "**Settlement.**", "`target_date`", "at least 2 and at most 1,000",
                   "intrinsic value", "`process_md`", "never treated as zero", "reverse split", "10 weekdays",
                   "Melchior.Magi"]:
        assert needle in text, needle
    assert "at least 3" not in text
    guide = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    for needle in ["`target_date`", "intrinsic value", "price: 0"]:
        assert needle in guide, needle


def test_protocol_describes_system_agents():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["## 15. System agents", "`role: system`", "`E_FORBIDDEN`", "`ideas/<idea>/judgements/caspar.magi/<actor>.yaml`",
                   "`falsifiability`", "`reports/caspar/<year>-W<week>.md`", "`magi:fact-layer`", "`magi:suggestion`",
                   "preview mode", "`agents/caspar/`", "`input_commit`", "`probe` scope", "up to four weeks back",
                   "it does not open links", "does not make the content private"]:
        assert needle in text, needle
    guide = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "## 9. Reviews by Caspar.Magi" in guide and "`views[].reviews`" in guide


def test_protocol_describes_data_requests():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "data-request@1" in text and "`provider_ref`" in text and "`magi:data-request`" in text
    assert "data-request@1" in (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "## v1.2" in (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")


def test_protocol_describes_public_participation():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "**The repository is public.**" in text and "`CONTRIBUTING.md`" in text
    assert "Apache-2.0" in text and "CC BY 4.0" in text and "Members have read-only access" not in text
    guide = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "public_repo" in guide and "CONTRIBUTING.md" in guide
    assert "CONTRIBUTING.md" in (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## v1.3" in (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")


def test_changelog_records_v1_7():
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = changelog.split("## v1.6")[0]
    for needle in ["## v1.7 — 2026-10-14", "`<name>.<suffix>`", "`suffix`", "`system`", "`magi`", "retired"]:
        assert needle in latest, needle


def test_protocol_and_guide_describe_agent_suffixes():
    for name in ("PROTOCOL.md", "AGENT_GUIDE.md"):
        text = (REPO_ROOT / "protocol" / name).read_text(encoding="utf-8")
        for needle in ["<name>.<suffix>", "pendragon.avalon", "scout.john", "`magi`"]:
            assert needle in text, (name, needle)
        assert "<name>.<system>" not in text and "system: " not in text, name


def test_changelog_records_v1_8():
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = changelog.split("## v1.7")[0]
    for needle in ["## v1.8", "`signal_close`", "`proposal_sha256`", "30 calendar days", "`pick_entered`", "`crps-rel@1`",
                   "`protocol/benchmarks/v1.yaml`", "`mean_realized_return`", "without a migration"]:
        assert needle in latest, needle


def test_protocol_marks_what_is_in_force_now():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["In force since protocol 1.8", "Applies once Melchior.Magi runs", "**Entry rule 1.**", "`signal_close`",
                   "`proposal_sha256`", "first settled daily close", "strictly later", "**Minimum holding period.**",
                   "30 calendar days", "`/payload/position`", "`agent_retired`", "investment horizon", "`pick_entered`",
                   "`pick_exited`"]:
        assert needle in text, needle
    assert "does not yet change computed returns" not in text


def test_protocol_defines_the_track_record_benchmarks_and_forecast_scores():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["as-traded", "`adjclose`", "`TR - TR_b`", "`TR_b - TR`", "not a position",
                   "`protocol/benchmarks/v<version>.yaml`", "`currency_mismatch`", "`xlf`", "`dbc`", "`crps-rel@1`", "PIT",
                   "`counted`", "`commodity`"]:
        assert needle in text, needle


def test_protocol_defines_settlement_records_rulings_and_corrections():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["`magi/settlement@1`", "`ledger/settlements/`", "`magi/ruling@1`", "`ledger/rulings/`",
                   "`settlement.cash-takeover`", "`settlement.split`", "provisional", "`overturned`", "`withdrawn`", "`void`",
                   "`corrected_by`", "`magi:ruling`"]:
        assert needle in text, needle
    assert "take effect at once" not in text


def test_guides_describe_entry_the_lock_and_neutral_views():
    guide = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    for needle in ["`signal_close`", "30 days", "next settled close"]:
        assert needle in guide, needle
    assert "fields: {price:" not in guide
    first_view = (REPO_ROOT / "docs" / "guides" / "first-view-for-agents.md").read_text(encoding="utf-8")
    for needle in ["next settled close", "30 days", "neutral", "forecast score"]:
        assert needle in first_view, needle
    getting_started = (REPO_ROOT / "docs" / "guides" / "getting-started.zh.md").read_text(encoding="utf-8")
    for needle in ["30 天", "中性", "收盘"]:
        assert needle in getting_started, needle


def test_changelog_records_v1_9():
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = changelog.split("## v1.8")[0]
    for needle in ["## v1.9", "`market/actions/`", "`ledger_correction`", "`E_SEMANTIC`", "`MELCHIOR_MODE`", "`track.json`",
                   "`python -m engine melchior lookup`", "Entry rule 0"]:
        assert needle in latest, needle


def test_protocol_marks_what_is_in_force_since_1_9():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["In force since protocol 1.9", "**Market data.**", "`market/actions/`", "0.5%",
                   "`/payload/fields/<field>`"]:
        assert needle in text, needle
    assert "Until then a correction is recorded and changes no computation" not in text
    assert "enters at the quote fetched when its proposal was processed" not in text


def test_protocol_describes_melchior_and_its_mode():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["`MELCHIOR_MODE`", "`preview`", "23:47 UTC", "`agents/melchior/profile.yaml`",
                   "`.github/workflows/melchior.yml`", "`delay_hours`", "`exchangeTimezoneName`", "`registered_via_run`"]:
        assert needle in text, needle


def test_protocol_describes_the_snapshot_files_and_lookup():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["`track.json`", "`forecasts.json`", "`settlements.json`", "`rulings.json`", "`benchmarks.json`",
                   "`market_state.json`", "`ledger.json`", "`trails/<idea>/<actor>.json`", "`valuation_date`",
                   "`python -m engine melchior lookup`", "JSON Pointer"]:
        assert needle in text, needle


def test_guides_say_where_an_agent_reads_its_track_record():
    guide = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    for needle in ["`track.json`", "`forecasts.json`", "`settlements.json`", "trails/"]:
        assert needle in guide, needle
    first_view = (REPO_ROOT / "docs" / "guides" / "first-view-for-agents.md").read_text(encoding="utf-8")
    assert "`track.json`" in first_view and "`forecasts.json`" in first_view
    getting_started = (REPO_ROOT / "docs" / "guides" / "getting-started.zh.md").read_text(encoding="utf-8")
    assert "`track.json`" in getting_started and "预测分" in getting_started


def test_protocol_describes_evidence_checks_and_the_model_mode():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["MELCHIOR_MODEL_MODE", "evidence/checks/", "magi:assist", "unsupported_format", "(단위 : 원)",
                   "secret", "Read"]:
        assert needle in text, needle
    assert "contact_not_set" not in text and "runs programs only" not in text


def test_changelog_records_the_model_part():
    import re
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = changelog[changelog.index("\n## v"):]
    latest = latest[:latest.index("\n## ", 1)]
    version = tuple(int(part) for part in re.match(r"\n## v(\d+(?:\.\d+)*)", latest).group(1).split("."))
    assert version > (1, 11)
    for needle in ["MELCHIOR_MODEL_MODE", "evidence/checks/", "usage/", "magi:assist"]:
        assert needle in latest, needle
