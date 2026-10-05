"""Import governance/rulesets/main.json into the public repository (design section 17.6).

    python tools/import_ruleset.py --repo the-magi-system/magi

The token comes from GH_TOKEN, or from `gh auth token` when GH_TOKEN is unset.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.github import GitHubClient  # noqa: E402


def resolve(ruleset: dict, lookup: Callable[[str], int]) -> dict:
    resolved = copy.deepcopy(ruleset)
    for actor in resolved["bypass_actors"]:
        actor["actor_id"] = lookup(actor.pop("actor_lookup"))
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import the main-branch ruleset")
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                                                          check=True).stdout.strip()
    gh = GitHubClient(args.repo, token)
    org = args.repo.split("/")[0]

    def lookup(key: str) -> int:
        kind, slug = key.split(":", 1)
        path = f"/orgs/{org}/teams/{slug}" if kind == "team" else f"/apps/{slug}"
        return int(gh.request("GET", path)["id"])

    ruleset = json.loads((ROOT / "governance" / "rulesets" / "main.json").read_text(encoding="utf-8"))
    created = gh.request("POST", f"/repos/{args.repo}/rulesets", resolve(ruleset, lookup))
    print(json.dumps({"id": created["id"], "name": created["name"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
