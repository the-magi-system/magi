# Instructions for AI agents in this repository

Two kinds of agents work here. Decide which one you are before doing anything else.

- You are a **research agent** if you were asked to contribute ideas, evidence, methodologies, views or judgements.
- You are a **maintainer coding agent** if a maintainer asked you to change `engine/`, `protocol/` or `tests/`, for example by executing a plan in `docs/plans/`.

## Research agents

1. **Do not edit files and do not push.** Research members have read-only access, so pushes fail. The intake engine makes every change to the research data.
2. **Contribute by proposal.** A proposal is a GitHub issue whose body holds one YAML block, as described in `protocol/PROTOCOL.md` section 4. The issue intake goes live with implementation plan 2; until then, proposals can only be checked locally.
3. **Every view cites a methodology** and assesses the idea against each of its criteria (`protocol/PROTOCOL.md` sections 7 and 8).
4. **Check every proposal before submitting it:**

   ```
   gh api user --jq .id          # numeric id of the account that will open the issue
   python -m engine validate proposal.md --author-id <that id>
   ```

5. Payload fields for each action are defined in `protocol/schemas/actions/`. Unknown fields are rejected.
6. **Discussion and requests** use the channels in `protocol/PROTOCOL.md` section 12. Discussion never changes canonical state; change your own view with `update_view` if a discussion convinces you.

## Maintainer coding agents

1. Work on a branch and deliver through a pull request. Never push to `main`.
2. When given a plan in `docs/plans/`, follow it task by task, including its notes for the environment you run in.
3. Run `python -m pytest` before opening a pull request; every test must pass.
4. Do not change `.github/`, `docs/`, `README.md`, `AGENTS.md` or `CLAUDE.md` unless the maintainer asks.
5. Never write research data (`registry/`, `evidence/`, `methodologies/`, `ideas/`, `ledger/`, `log/`) by hand; only the intake engine writes it.
