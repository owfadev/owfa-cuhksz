---
name: cuhksz-cli
owner: framework
description: "Read-only access to the CUHK-SZ school systems via the unified connectors/cuhksz-cli CLI: `cuhksz-cli bb <...>` reads bb.cuhk.edu.cn (Blackboard — courses/assignments/grades/announcements/course files/my submissions) and `cuhksz-cli sis <...>` reads sis.cuhk.edu.cn (PeopleSoft — schedule/grades/history/enrollment dates/exams/transcript/class search). Single entry point; machine state lives in the OWFA substrate (`cuhksz-cli home status`). Query-and-answer only; writes nothing to wiki. Triggers on: cuhksz-cli, cuhksz, bb-cli, sis-cli, bb, blackboard, bb.cuhk.edu.cn, sis, sis.cuhk.edu.cn, fetch from bb, check bb courses, check bb assignments, check bb grades, check bb announcements, check sis schedule, check my timetable, check enrollment dates, student information system, timetable query, class search, course catalog, 学生信息系统, 课表查询, 选课, 开课."
---

# cuhksz-cli: Unified CUHK-SZ Read-Only Connector

One entry, two backends. `cuhksz-cli bb <command> ...` pulls from bb.cuhk.edu.cn (Blackboard Learn) and `cuhksz-cli sis <command> ...` from sis.cuhk.edu.cn (PeopleSoft CS) via `connectors/cuhksz-cli/` (a purely read-only CLI data plane) and relays the results to the user. Queries answer directly: nothing is written to wiki and no data area is modified.

The backend state directories are **not** aggregated into one directory, but they do share the connector's single machine home: bb's credentials/session live in the `bb` component, sis's in the `sis` component of

```
$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/bb/
$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/sis/
```

(`$OWFA_HOME` defaults to `~/.owfa`; `<id>` is the workspace binding — `default` on a one-workspace machine). All paths come from the machine-substrate helper `.owfa/scripts/owfa_home.py`; never assemble `~/.owfa/...` by hand. Run `cuhksz-cli home status` to print the effective paths, the substrate health view and any legacy directories still present.

## Migration (0.3.0 — legacy entry points removed)

Since connector 0.3.0 the package ships **one** console script; the legacy wrappers kept since 0.2.1 are gone:

| Was (removed in 0.3.0) | Now |
|---|---|
| `bb-cli <cmd> [args]` | `cuhksz-cli bb <cmd> [args]` |
| `sis-cli <cmd> [args]` | `cuhksz-cli sis <cmd> [args]` |

Every command name, flag and output shape is unchanged — insert the `bb` / `sis` backend word after `cuhksz-cli`. Scripts, aliases or muscle memory still calling `bb-cli` / `sis-cli` must switch; reinstall the connector and remove the old scripts (`python -m pip uninstall` + reinstall, or the instance's uv route).

Machine state migrates with an explicit command (never a side effect of a normal run). Inspect first, then move; each legacy directory is moved into a component and left as a symlink so old absolute paths keep resolving:

```text
cuhksz-cli home status
cuhksz-cli home migrate --dry-run
cuhksz-cli home migrate
```

`home migrate` moves `~/.bb-cli` → `<home>/bb` and `~/.sis-cli` → `<home>/sis`. It must run inside the workspace whose binding should own the state (or pass `--root <workspace>`); run it once, then re-login is not needed — stored credentials and sessions carry over. `--dry-run` moves nothing and registers no binding. Before moving anything the command pre-flights every component: if `BB_CLI_HOME` or `SIS_CLI_HOME` is set the whole migration is refused (an explicit override is honoured exactly — unset it first), as is a target component that already holds files; the refusal is a structured JSON error and nothing moves or binds. If the connector runs with no OWFA helper at all (installed outside any workspace), or if the substrate component does not hold state yet while the legacy directory still does, it keeps using the legacy directory and prints a one-line notice naming this command — an unmigrated home is never silently stranded behind a new empty one.

The `BB_CLI_HOME` / `SIS_CLI_HOME` environment variables remain honoured as explicit compatibility overrides ("use exactly this directory") and are not the default path. The `BB_CLI_*` / `SIS_CLI_*` credential, proxy and debug variables are unchanged.

## Scope

- bb backend — read: courses / assignments / grades / announcements / course files / my submissions / members; write: none (read-only by design; submitting assignments or posting announcements is deliberately not provided — would require explicit user instruction and separate design)
- sis backend — read: weekly schedule with day-of-week / per-term grades / course history / enrollment dates / exam schedule / student center / transcript / **class search (course catalog + section times)**; write: none. **Enrollment actions (add/drop/swap classes) and any state-changing transaction are deliberately NOT provided**; the user risks academic penalties for misuse, so never attempt them via raw or any other route. The only POSTs the CLI ever makes are query actions on PeopleSoft search pages: the term-selection "Continue", and the two-step Class Search AJAX flow — both pure queries

## Prerequisites (install / auth)

1. Install (if missing): `cd connectors/cuhksz-cli && python3 -m pip install --user --break-system-packages -e .` (deps: curl_cffi + beautifulsoup4 only; or the `.venv`/uv route per README). One install provides the single entry point `cuhksz-cli`. Upgrading from ≤0.2.2: reinstall so the `bb-cli` / `sis-cli` console scripts disappear, run `cuhksz-cli home migrate` (see Migration above), then no re-login is needed
2. Init (strongly recommended): run `cuhksz-cli bb login` and/or `cuhksz-cli sis login` manually once to leave stored credentials (`--username <student-id>`; password via the `BB_CLI_PASSWORD` / `SIS_CLI_PASSWORD` env var or interactive prompt; `--no-store` keeps it off disk; the session cookie jar is `<home>/bb/session.json` / `<home>/sis/session.json` — locate `<home>` with `cuhksz-cli home status`). The first login automatically becomes the **default account** per backend; confirm with `<backend> default`, switch with `<backend> default <name>`. Automatic re-login (401-triggered) only ever uses the **default account**; other stored accounts are never auto-logged-in
3. Self-check: `cuhksz-cli bb status` / `cuhksz-cli sis status` are **offline tri-state probes** (zero network, zero login): bb reports `session_file` / `session_valid` (local cookie liveness, server validity not checked) / `auto_relogin` (`"available"` = stored credentials renew any real command silently; `"blocked (no stored credentials)"` = manual `login` needed; `"blocked (no default account)"` = credentials on disk but several accounts and none picked — fix with `default <name>`); sis reports the same state/capability split as `session` / `relogin` (plus `reachable: null` — network health is never claimed offline). A stale session with `auto_relogin: available` is NOT an error and NOT a manual-login condition; only `blocked` states call for `login` (or `default <name>` when the reason is no default account). `status 全绿≠可用` on sis either — a failed first pull splits into network (campus VPN) vs. credentials (`relogin`) paths

## Steps

1. `cuhksz-cli home status` (first run on a machine upgraded from the old layout) and `cuhksz-cli bb status` / `cuhksz-cli sis status` to confirm state and the session
2. Pick a backend and command per the need (cheat sheets below); `--format text` prints human-readable lines, JSON keeps raw/structured values
3. Relay the results to the user (language: see Language below)

## bb command cheat sheet

| Need | Command |
|---|---|
| My courses | `cuhksz-cli bb courses [--term <term-name-substring>] --format text` |
| Terms | `cuhksz-cli bb terms --format text` (locate the current term name first, then filter with it, e.g. `--term 2610UG`) |
| Assignments + status | `cuhksz-cli bb assignments <course> --format json` (due / possible / status / score) |
| Gradebook | `cuhksz-cli bb grades [<course>] [--due-only]` |
| Upcoming deadlines (one course / all) | `cuhksz-cli bb dues [--course C] [--from D] [--to D] --format text` |
| Announcements | `cuhksz-cli bb announcements [--course <substring>] [--limit N]` |
| Course files / download | `cuhksz-cli bb files <course>` / `cuhksz-cli bb fetch <course> [-o DIR] [--dest DIR] [--exclude-mime video/,audio/] [--exclude-ext ext,…] [--no-media-filter] [--max-size MB] [--refresh]` |
| My submissions | `cuhksz-cli bb submission <course> [--download] [--dest DIR]` |
| Identity | `cuhksz-cli bb whoami` |
| Accounts / default account | `cuhksz-cli bb accounts` / `cuhksz-cli bb default [<name>]` (per-backend account stores, passwords never shown; switching clears the session so the next command auto-logs-in as it) |

The course argument accepts a course id (`_18027_1`), a course code, or a name substring (`AIE3905`); on ambiguity the CLI lists the candidates. Status values: `Graded` = graded (with score), `NeedsGrading` = submitted and awaiting grade, empty/`None` = not submitted or no data. Timestamps: `--format text` display and `--from`/`--to`/`--since` filtering use the local timezone; JSON output keeps the raw API value (UTC ISO `…Z`). `fetch` skips common media extensions by default (`mts/mpg/mpeg/avi/mkv/wav/mp4/mov/mp3/m4a/webm`); `--no-media-filter` restores "download everything"; `--refresh` re-pulls existing files and lands changed content as a hash-suffixed new file (old kept). Full table: [docs/bb.md](docs/bb.md).

## sis command cheat sheet

| Need | Command |
|---|---|
| Weekly schedule + day-of-week timetable | `cuhksz-cli sis schedule --days --format text` |
| Course catalog / sections & times for a term | `cuhksz-cli sis search [--term 'Term 2'] --subject AIE [--catalog 1904] [--contains] [--all-seats]` (read-only; open sections by default) |
| My grades for a term | `cuhksz-cli sis grades [--term 'Term 2']` (default = newest term) |
| Full course history | `cuhksz-cli sis history` |
| Enrollment dates / registration window | `cuhksz-cli sis appt [--term 'Summer']` |
| Exam schedule | `cuhksz-cli sis exam` (empty when not yet published) |
| Download unofficial transcript PDF | `cuhksz-cli sis transcript [--lang eng] [-o out.pdf]` |
| Structured student identity | `cuhksz-cli sis identity` |
| Degree progress report (currently needs Request Audit) | `cuhksz-cli sis dpr` |
| Student center / per-assignment grades | `cuhksz-cli sis center` / `cuhksz-cli sis assignments` (text summaries) |
| Any page as HTML, GET or ICAction POST navigation | `cuhksz-cli sis raw <url> [--post --action BTN --set k=v] --file out.html` |
| Accounts / default account | `cuhksz-cli sis accounts` / `cuhksz-cli sis default [<name>]` |

Component URLs take the form `/psc/csprd/EMPLOYEE/HRMS/c/<COMPONENT>?PORTALPARAM_PTCNAV=<NAV>` — both parts are registered in `siscli/config.py`; use `raw` for anything not yet wrapped. Sessions expire in ~5 minutes — the CLI re-logs in automatically per command (default account only). Full table: [docs/sis.md](docs/sis.md).

`sis search` is advisory only. 「本命令只提供课程信息的查询与参考建议；AI 不能保证给出最优选课方案，也不代替用户做决定；连接器是**只读**的——不选课、不加购物车、不交作业、不执行任何 state-changing 交易；最终以 SIS 与教务规定为准。」

## `home` command surface (machine substrate)

| Need | Command |
|---|---|
| Where does bb/sis state live? | `cuhksz-cli home status [--format text] [--root WS]` (read-only: prints the effective component paths with their source — env override / substrate / legacy — plus the substrate health view) |
| Inspect a pending legacy migration | `cuhksz-cli home migrate --dry-run [--root WS]` (reports `would-migrate` / `nothing-to-migrate` / `already-migrated`; moves and binds nothing) |
| Move `~/.bb-cli` + `~/.sis-cli` into the substrate | `cuhksz-cli home migrate [--root WS]` (move, never copy; leaves a symlink at each legacy path; register the workspace binding) |

Migration is explicit only: no other command ever moves or creates a second home. If `home migrate` reports `no OWFA home helper`, run it from a workspace that carries `.owfa/scripts/owfa_home.py` (or set `OWFA_HOME_HELPER`).

## Schedule query routing (sis)

For timetable or next-class questions in a wiki instance, first read `wiki/calendar.md` and the relevant `wiki/calendar/YYYY-MM.md` month projection (including the next month if the requested date crosses a month boundary). Answer locally when the projection identifies the matching SIS source, covers the requested dates, and has an unexpired `stale_after`. If the projection is absent, stale, lacks freshness/source evidence, or does not cover the requested dates, use SIS as the source under the user's authorization; an explicit request to refresh overrides the local-cache preference. Outside a wiki instance, this connector remains usable directly.

## Known limits

- bb: 404 under student sessions for `gradebook/attempts` (flat), `discussion/forums`, `users/me/memberships`, `tasks`, `gradebook/grades`; Classic (JSP) courses only, Ultra unverified; write operations deliberately not provided
- sis: `exam` returns empty until the school publishes the term's exam schedule; `assignments` (per-assignment gradebook) usually shows "no information" — use `grades`; Tuition/Finances and enrollment-cart read views not registered — explore via `raw` first, then wrap; `search` renders only the first 3 sections per course (PeopleSoft pagination) and refuses queries over 50 classes with a notice; PIA upgrades or sign-in page changes break the chain — re-run with `SIS_CLI_DEBUG=<dir>` to capture evidence
- bb raw pass-through accepts GET only; sis raw POST is restricted to registered components

## Prohibitions

- Never perform write operations (submitting/posting on bb; enroll/drop/swap/edit classes or any state-changing transaction on sis); if ever needed, requires explicit user instruction and separate design — the user faces academic penalties for enrollment misuse
- Student ids / passwords never enter the repo; never echo the password; credentials live only in the machine substrate — `$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/bb/` and `.../sis/` (locate them with `cuhksz-cli home status`), or in the explicit `BB_CLI_HOME` / `SIS_CLI_HOME` override directory; never in the repository
- Do not paste raw sis component HTML (contains personal data) into the wiki or commit it; relay personal data in conversation only

## Language

Follow the upper-layer requirements and the conversation context. Keep course names, course codes, component names, file names, and paths verbatim.
