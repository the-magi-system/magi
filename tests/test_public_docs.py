"""Files a public repository needs: licences, disclaimer, contribution guide and join form (design section 17)."""
from engine.yamlio import load_yaml
from tests.util import REPO_ROOT


def _text(*parts: str) -> str:
    return REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_licences_and_disclaimer():
    assert _text("LICENSE").lstrip().startswith("Apache License")
    assert "Attribution 4.0 International" in _text("LICENSES", "CC-BY-4.0.txt")
    readme = _text("README.md")
    for needle in ["Apache-2.0", "CC BY 4.0", "`LICENSES/CC-BY-4.0.txt`", "Third-party data is not covered",
                   "investment advice", "不构成投资建议", "`CONTRIBUTING.md`"]:
        assert needle in readme, needle


def test_contributing_explains_joining_and_licensing():
    text = _text("CONTRIBUTING.md")
    for needle in ["**Join as a researcher**", "E_IDENTITY", "`magi:join`", "Apache-2.0", "CC BY 4.0",
                   "investment advice", "public_repo", "Material non-public information"]:
        assert needle in text, needle


def test_join_form_and_blank_issues():
    form = load_yaml(REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "join.yml")
    assert form["name"] == "Join as a researcher" and form["labels"] == ["magi:join"]
    assert [item.get("id") for item in form["body"]] == [None, "handle", "display_name", "research", "agents", "terms"]
    terms = form["body"][-1]["attributes"]["options"]
    assert len(terms) == 4 and all(option["required"] for option in terms)
    assert "material non-public information" in terms[3]["label"]
    config = load_yaml(REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml")
    assert config["blank_issues_enabled"] is True
