# Governance

`rulesets/main.json` is the branch ruleset for `main`. The repository is public, and GitHub Free allows rulesets on public repositories (design section 17.6).

The ruleset has two rules: nobody can delete `main`, and nobody can force-push to it, so its history cannot be rewritten. It has no bypass actors. The intake engine is not affected, because its pushes are ordinary fast-forward pushes.

The ruleset does not require pull requests or passing checks for every change. That rule would also block the engine, which pushes directly with the workflow's `GITHUB_TOKEN`. Enabling it first needs the engine to push as a GitHub App (design section 14).

Import it once with:

```
python tools/import_ruleset.py --repo the-magi-system/magi
```

Check the result under Settings → Rules → Rulesets, or with `gh api repos/the-magi-system/magi/rules/branches/main`.

## In an emergency

- To repair `main` with a force push, an organisation owner temporarily disables the ruleset under Settings → Rules. GitHub records the change in the organisation's audit log. Enable the ruleset again straight afterwards.
- When issues or comments are flooded, a maintainer sets temporary interaction limits (Settings → Moderation options → Interaction limits), so that only prior contributors can open issues and comment. The engine already rejects proposals from unregistered accounts.
