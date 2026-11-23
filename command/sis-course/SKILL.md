---
name: sis-course
owner: sis-course
consumes: [sis, sis-course, trust, log, index, hot]
description: "Read-only course-catalog advisory on SIS Class Search: resolve the term → query by subject/catalog → present courses with sections, meeting times, rooms and instructors as 建议参考 — never pick courses for the user, never promise an optimal plan, never cart/enroll. Triggers on: sis-course, 选课清单, 开课查询, 下学期开什么课, class search, course catalog, 课号, 班号, 时间冲突, 查课程, 有哪些课."
---

# sis-course: course-catalog advisory

Answer "what courses run next term / what time does this course meet / will it clash with X" from SIS Class Search (`cuhksz-cli sis search`) and present the result as **建议参考** — the catalog facts come from SIS, the choice always stays with the user. This command is query-and-answer: it writes nothing by default, never adds to a shopping cart, and never promises an optimal timetable. Session discipline and the connector's read-only red line live in the cuhksz-cli skill (`connectors/cuhksz-cli/SKILL.md`); in-depth course selection belongs to the user and the academic regulations, not to this command.

「本命令只提供课程信息的查询与参考建议；AI 不能保证给出最优选课方案，也不代替用户做决定；连接器是**只读**的——不选课、不加购物车、不交作业、不执行任何 state-changing 交易；最终以 SIS 与教务规定为准。」

## Scope

Write: only on an explicit request to keep a comparison — a notes page under `wiki/cuhksz/sis/` with the `course_catalog` mapping (term/strm/subject/catalog/fetched_at/stale_after) + a log line; otherwise nothing
Read: cuhksz-cli sis (`search` for the catalog, `status` for the session), `wiki/cuhksz/sis/inbox.md` (term context, when present), `wiki/calendar.md` + the relevant month projection (the user's existing commitments, for time-conflict checks), `wiki/cuhksz/identity.md` (term/major context, when present)

## Steps

1. **Resolve the term**: `cuhksz-cli sis status` first (offline evidence; if `relogin` is blocked, follow the login discipline in the cuhksz-cli skill). Then let `search` resolve the term: `--term` accepts the strm code (`2620`) or a full label (`'2026-27 Term 2'`); a bare substring like `'Term 2'` matches many years and is **refused with candidate terms** (pass the strm or the full label). When the user names no term, the command resolves the newest term whose start year is not after the current year and echoes it — **state the resolved term in the answer**. If the term cannot be matched, show the available terms and ask, do not guess
2. **Query by subject and/or catalog**: SIS needs at least two criteria (the term plus a subject and/or catalog), so always query with `--subject <code>` and/or `--catalog <number>`; `--contains` turns the catalog match into contains. Add `--all-seats` only when the user asks about closed sections (the default is open sections only). Add `--all-sections` when the section list matters — SIS renders only the first 3 per course by default, and expansion costs one read-only request per course
3. **Present courses + sections + times**: per course, a header line with the section count and completeness marker (`AIE 1904 - AI Exploration IV — 8 sections (all)` / `— 3 sections (first 3 shown; --all-sections to expand)`), then each section (`L01-LEC(2278)` / `S01-SUP(2549)` …) with its meeting time(s) joined by ` / `, room and instructor. When a course mixes section types the text output groups them (`LEC:` then `TUT:` …), because a GE course's tutorial is what occupies the timetable. Sections with no fixed meeting (SUP) are marked as such. Keep the resolved term and the filters visible above the list
4. **Frame the output as 建议参考**: relate the list to the user's stated constraints (interests, time conflicts against the calendar, term load) and explain the trade-offs — but explicitly say the choice is the user's. **Never call a plan optimal, never choose for the user, never add anything to a cart**; the final authority is SIS and the academic regulations
5. **Keep the limits honest**: SIS renders only the first 3 sections per course by default; `--all-sections` expands every course with a "View All Sections" link (capped, one request per course, and a failed expansion degrades to the 3 rendered sections with a structured note) — use it when the tutorial/section choice matters, and never present a short list as exhaustive. A query over ~50 classes returns a structured notice — narrow with `--catalog` / `--contains`. Never imply a section is guaranteed to have a seat
6. **Optional save** (explicit request only): write one comparison page under `wiki/cuhksz/sis/` with the `course_catalog` mapping + `fetched_at`/`stale_after` and a backlink to the query; then the post-write pipeline + a log line
7. Report: resolved term / filters / course and section counts / the advisory framing

## Prohibitions

- **Never** enroll, add to cart, drop/swap, submit, or perform any state-changing transaction; the only network flow is the read-only Class Search query
- Never present the output as an optimal or final choice, never make the decision for the user, never promise seat availability or an enrollment outcome
- Never hide the 3-section default, the `--all-sections` cap/expansion failure, or the 50-class notice when they affect the answer; never invent a section/time that the query did not return
- Never paste raw SIS HTML (contains personal data) or credentials into the answer or any repository; student data stays in the conversation on the local machine
- Do not write a comparison page unless the user explicitly asks; catalog data is regenerable, so a default archive only drifts

## Language

Output language takes the default key of the language declaration page `wiki/language.md` (a missing page or missing key falls back to the session language); course codes, section codes, room names and instructor names keep their original form.

## Parameters

- Term (strm code or a full label; an ambiguous substring is refused with candidates; omittable = the newest term whose start year is not in the future, echoed in the answer)
- Subject and/or catalog number (at least one is required by SIS; both can be combined)
- `--contains` (catalog contains match), `--all-seats` (include closed sections), `--all-sections` (expand the per-course section list), `--format text|json`

## Injected Section (plugin usage blocks)

> This region is a wiki_plugin_kernel projection: consumes pulls merged with usage_routes source-side routing; disclosure order = owner first, routed blocks in the middle, pulled blocks last (rebuilt by inject / all); handwritten content does not belong here — to change the write-side contract, edit PLUGIN.yaml.

<!-- cmd-inject:start -->
<!-- usage:sis-course -->
- Resolve the term first: `cuhksz-cli sis search --subject <code>` echoes the resolved term; `--term` accepts the strm code or a full label (`'2026-27 Term 2'`); a bare substring like `'Term 2'` is refused as ambiguous with candidate terms; omitted = the newest term whose start year is not in the future. State the resolved term in the answer
- Query with at least two criteria (term + subject and/or catalog): `cuhksz-cli sis search --subject AIE --catalog 1904`. A subject alone may exceed the server's 50-class ceiling (structured notice); SIS renders only the first 3 sections per course by default, so add `--all-sections` when the section/tutorial list matters (capped, one request per course; a failed expansion degrades with a note) — narrow with --catalog/--contains and never present a short list as exhaustive
- Present as 建议参考: courses → sections (grouped `LEC:` / `TUT:` when a course mixes types; L01-LEC / S01-SUP …) → meeting times / room / instructor. Compare against the user's stated constraints (term, time conflicts, interests) but leave the choice with the user — never call a schedule optimal, never auto-add to a cart, never promise an enrollment outcome
- Only on an explicit request to keep the comparison, save a notes page (term/filters + fetched_at + stale_after + backlink); otherwise write no page — the data is fully regenerable from SIS
<!-- /usage:sis-course -->

<!-- usage:sis -->
- Enter the domain by first reading wiki/cuhksz/sis/inbox.md (created when absent: fresh-pull cuhksz-cli sis grades/appt/schedule, distill and rewrite the digest + a log line); staleness follows the same flow (the agent is the synchronizer)
- Query via the cuhksz-cli skill (sis backend): grades (--term term substring) / history / schedule (--days weekday scoping) / registration windows / exam arrangements; sessions are minute-scale and short-lived, commands auto-relogin, no manual login needed (credentials in the OWFA substrate, `$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/sis/`, located via `cuhksz-cli home status`; environment variables or `SIS_CLI_HOME` as explicit overrides)
- Term-grade sedimentation: after the term ends, full pull of grades --term → the digest page's snapshot section + an append to the bb-track evidence stream (after user confirmation, machine evidence)
- Enrollment identity changes (major transfer/graduation) → update the sis block mapping of the domain-root identity.md
<!-- /usage:sis -->

<!-- usage:trust -->
- When writing a page, write `generated` along the way (block style: `by: agent/<current-model>` / `at: <today>`)
- When a review action happens, append a `verified` event (single line `by: <actor>, at: <date>`), never fabricated to inflate the level
- Reviews are initiated by the user (triggered by human instruction); agents never append verified events on their own
<!-- /usage:trust -->

<!-- usage:log -->
- Writing lines (mechanical, automatic): `python .owfa/plugins/domains/personal/pipeline.py log <type> "<one sentence>" [--domain <domain>]` (type value set in the log block of the AGENTS injection region; domain tag = domain-plugin name such as bb/lark/vault, mandatory for in-domain transactions, omitted for framework and native transactions); rolling window and archiving are performed by the script
<!-- /usage:log -->
<!-- cmd-inject:end -->
