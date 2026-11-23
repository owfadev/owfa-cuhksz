# sis-course: Course-Catalog Advisory

## Design Summary

- **Why it exists**: choosing next term's courses currently means hunting through SIS Class Search by hand. The read-only `cuhksz-cli sis search` command now exposes the catalog (courses + sections + meeting times), but a raw listing is not advice — this member turns a query into a **参考建议** while keeping the decision with the user. It is the consumption side of the same sis facts the sis plugin governs
- **Position in the family**: a member inside the cuhksz domain, sibling of sis (institutional facts) and the bb family (course operations); it reads SIS only and writes no SIS state. It has no territory of its own — the catalog is fully regenerable, so results stay in the conversation unless the user asks to keep a comparison
- **Key rulings**:
  - **advisory, never decisive** (2026-11-23): the output is framed as 建议参考; the agent compares against the user's stated constraints but never calls a plan optimal, never picks for the user, and never executes an enrollment action
  - **read-only red line extended to advice**: no cart, no add/drop, no submission, no state-changing transaction — the only network flow is the two-step Class Search query (plus the optional per-course "View All Sections" expansion, itself a read-only query action)
  - **no default projection**: a query writes nothing; a comparison page is created only on an explicit request and is regenerable, so there is no archive worth maintaining
- **Rejected alternatives**: a catalog mirror under `cuhksz/sis/` — SIS re-serves it anytime, a mirror only drifts; a "best schedule" solver — it would imply an optimality promise the plugin explicitly refuses, and would silently encode the agent's priorities over the user's

## Structure

- No materialization zone and no territory of its own: reads go through the sis backend (`cuhksz-cli sis search`), output is conversation-only by default
- Command skill `command/sis-course/SKILL.md` (resolution → query → presentation → advisory framing); command-bearing plugin, `commands: [sis-course]`
- On explicit request only: a comparison page under `wiki/cuhksz/sis/` notes with `course_catalog` mapping (term/strm/subject/catalog/fetched_at/stale_after) and a backlink to the query that produced it

## Invariants

- **Advisory only** — 「本命令只提供课程信息的查询与参考建议；AI 不能保证给出最优选课方案，也不代替用户做决定；连接器是**只读**的——不选课、不加购物车、不交作业、不执行任何 state-changing 交易；最终以 SIS 与教务规定为准。」
- Read-only red line: no enrollment, cart, drop/swap or any state-changing action; the only POSTs are the two-step Class Search query and the per-course "View All Sections" expansion (both pure query actions on the same component)
- Never promise optimality; compare against the user's stated constraints and leave the choice with the user
- Limitations stay visible: the resolved term is echoed; SIS renders only the first 3 sections per course by default and `--all-sections` expands them (capped, one read-only request per course, and a failed expansion degrades to the rendered sections with a structured note); queries over 50 classes return a structured notice — narrow with `--catalog` / `--contains`
- Regenerable: no default projection; a saved comparison carries `fetched_at` + `stale_after`; credibility is machine-confirmed, never human-reviewed
- Privacy: student data and credentials stay on the local machine / in the conversation; course selections never enter the framework repository

## Changelog

- 0.2 (2026-11-23): consume the connector's new `--all-sections` expansion (per-course "View All Sections" query) so section/tutorial choices are presented completely when they matter; LEC/TUT/SUP grouping in the text output; term-resolution usage corrected (a full label or strm code, ambiguous substrings refused with candidates; omitted = the newest term not in the future)
- 0.1 (2026-11-23) established: read-only course-catalog advisory via `cuhksz-cli sis search` (Class Search two-step AJAX), with the advisory-only / no-optimality / read-only rules and the 3-section & 50-class limits made explicit
