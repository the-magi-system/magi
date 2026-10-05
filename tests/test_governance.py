import importlib.util
import json

from tests.util import REPO_ROOT


def _module():
    spec = importlib.util.spec_from_file_location("import_ruleset", REPO_ROOT / "tools" / "import_ruleset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ruleset_protects_history_without_bypass():
    ruleset = json.loads((REPO_ROOT / "governance" / "rulesets" / "main.json").read_text(encoding="utf-8"))
    assert {rule["type"] for rule in ruleset["rules"]} == {"deletion", "non_fast_forward"}
    assert ruleset["bypass_actors"] == [] and ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    assert _module().resolve(ruleset, lambda key: 0) == ruleset


def test_resolve_turns_lookups_into_ids():
    ruleset = {"bypass_actors": [{"actor_type": "Team", "actor_lookup": "team:maintainers", "actor_id": None,
                                  "bypass_mode": "always"}]}
    resolved = _module().resolve(ruleset, {"team:maintainers": 11}.__getitem__)
    assert resolved["bypass_actors"] == [{"actor_type": "Team", "actor_id": 11, "bypass_mode": "always"}]
    assert "actor_lookup" in ruleset["bypass_actors"][0]
