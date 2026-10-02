import importlib.util
import json

from tests.util import REPO_ROOT


def _module():
    spec = importlib.util.spec_from_file_location("import_ruleset", REPO_ROOT / "tools" / "import_ruleset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ruleset_resolves_bypass_actors():
    ruleset = json.loads((REPO_ROOT / "governance" / "rulesets" / "main.json").read_text(encoding="utf-8"))
    ids = {"team:maintainers": 11, "app:github-actions": 15368}
    resolved = _module().resolve(ruleset, ids.__getitem__)
    assert [(a["actor_type"], a["actor_id"]) for a in resolved["bypass_actors"]] == [("Team", 11), ("Integration", 15368)]
    assert all("actor_lookup" not in actor for actor in resolved["bypass_actors"])
    assert "actor_lookup" in ruleset["bypass_actors"][0]
    assert {rule["type"] for rule in resolved["rules"]} == {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
