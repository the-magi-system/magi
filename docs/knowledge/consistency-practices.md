# Consistency practices

Operating knowledge supplied by data provider `arthur` and approved for The Magi System on 2026-10-02 (design section 16.5). Each practice comes from a failure observed in an earlier research system. The last column says where Magi applies it.

| Practice | Failure it prevents | Where Magi applies it |
|---|---|---|
| One implementation per rule, called by every consumer | Two copies of one rule drift apart, and on the day they diverge neither reports an error | `engine/derive.py` is the only place derived figures are computed, and `engine/ledger.py` the only place ledger events are put in order: at intake, in the consistency check and in the snapshot |
| A dry run and the real run read from the same source | A dry run read an in-memory object that had a field, while the real run read a CSV that lacked it. For a week the real run reported every item as updated while one of its steps changed nothing | The intake writes exactly the change set it validated, and `dry-run` calls the same `apply_proposal` |
| Verify through an independent path, not through the tool's own report | A check compared the written files with the same CSV they were written from, so it could not find an error in that CSV | The consistency check recomputes derived fields from the raw inputs instead of trusting stored values |
| Treat an empty scan as a failure, not as "no problems" | A directory walk on a network share swallowed its errors and returned zero files without complaint; an audit pointed at a path that did not exist reported zero problems | The consistency check lists directories with explicit error capture and reports a data directory that yields no files |
| Tests own their fixtures, and a missing fixture fails | Tests that read real pages were skipped after the pages were renamed, and the suite still printed no failures | `tests/util.py` builds every fixture; no test reads live data |
| Checks report; owners fix | A script that overwrites a hand-maintained file erases the judgement written into it | The audit and consistency commands only open issues, and every finding names its owner |
| Every finding has an owner, an action and a closing condition | Findings without an owner only accumulated: one count of unresolved items kept rising | Findings carry `owner`; audit issues stay open until a maintainer closes them |
| Cite the single source instead of transcribing it | A transcribed figure goes stale while the source moves on | The snapshot is compiled from the repository and never edited; provider evidence carries `provider_ref` so the provider can supersede it |
| A negative claim ("X is missing", "nothing changed") needs a full search and a known counter-example | A filter written the wrong way returned every row and looked like "everything is missing" | The tests of every check include cases that must produce findings, not only clean cases |
| Version everything that consumers depend on | Instructions written against an older contract kept producing obsolete fields | Stored files carry a schema version (`magi/view@1`), and protocol changes go into `protocol/CHANGELOG.md` |
