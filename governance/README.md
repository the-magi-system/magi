# Governance

`rulesets/main.json` is the branch ruleset for `main`. Rulesets on private repositories need GitHub Team or Enterprise, so it is imported only after the organisation upgrades (design section 3.6).

Once imported, only the maintainers team and the GitHub Actions app (which runs the intake engine) can push to `main`; everyone else goes through pull requests that pass the `test` check. Research members already have read-only access, so the ruleset mainly protects `main` from accidental direct pushes by maintainers.

Import it with:

```
python tools/import_ruleset.py --repo the-magi-system/magi
```

The script looks up the numeric ids of the maintainers team and the GitHub Actions app, then creates the ruleset. Check the result under Settings → Rules → Rulesets.
