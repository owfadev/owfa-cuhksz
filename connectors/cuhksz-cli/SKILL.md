---
name: cuhksz-cli
owner: framework
description: "Read-only access to the CUHK-SZ school systems via the unified connectors/cuhksz-cli CLI: `cuhksz-cli bb <...>` reads bb.cuhk.edu.cn (Blackboard — courses/assignments/grades/announcements/course files/my submissions) and `cuhksz-cli sis <...>` reads sis.cuhk.edu.cn (PeopleSoft — schedule/grades/history/enrollment dates/exams/transcript). Legacy `bb-cli` / `sis-cli` entry points keep working as thin wrappers. Query-and-answer only; writes nothing to wiki. Triggers on: cuhksz-cli, bb-cli, sis-cli, bb, blackboard, bb.cuhk.edu.cn, sis, sis.cuhk.edu.cn, fetch from bb, check bb courses, check bb assignments, check bb grades, check bb announcements, check sis schedule, check my timetable, check enrollment dates, student information system, timetable query, 学生信息系统, 课表查询."
---

# cuhksz-cli: Unified CUHK-SZ Read-Only Connector

One entry, two backends. `cuhksz-cli bb <command> ...` pulls from bb.cuhk.edu.cn (Blackboard Learn) and `cuhksz-cli sis <command> ...` from sis.cuhk.edu.cn (PeopleSoft CS) via `connectors/cuhksz-cli/` (a purely read-only CLI data plane) and relays the results to the user. Queries answer directly: nothing is written to wiki and no data area is modified. Credential stores are NOT aggregated: bb credentials/sessions stay in `~/.bb-cli/`, sis in `~/.sis-cli/` — exactly as before, so existing logins keep working.

## Migration (backward compatibility)

The pre-0.2.1 entry points remain installed and behave identically — they are thin wrappers over the same backends:

| Legacy command | Unified command |
|---|---|
| `bb-cli <cmd> [args]` | `cuhksz-cli bb <cmd> [args]` |
| `sis-cli <cmd> [args]` | `cuhksz-cli sis <cmd> [args]` |

Mapping rule: insert the `bb` / `sis` backend word after `cuhksz-cli`; every command name, flag and output shape is unchanged. Old skill docs referencing `bb-cli` / `sis-cli` keep working; prefer the unified form in new writing.

## Scope

- bb backend — read: courses / assignments / grades / announcements / course files / my submissions / members; write: none (read-only by design; submitting assignments or posting announcements is deliberately not provided — would require explicit user instruction and separate design)
- sis backend — read: weekly schedule with day-of-week / per-term grades / course history / enrollment dates / exam schedule / student center / transcript; write: none. **Enrollment actions (add/drop/swap classes) and any state-changing transaction are deliberately NOT provided**; the user risks academic penalties for misuse, so never attempt them via raw or any other route. The only POST the CLI ever makes is the term-selection "Continue" query on PeopleSoft search pages — a pure query action

## Prerequisites (install / auth)

1. Install (if missing): `cd connectors/cuhksz-cli && python3 -m pip install --user --break-system-packages -e .` (deps: curl_cffi + beautifulsoup4 only; or the `.venv`/uv route per README). One install provides all three entry points (`cuhksz-cli`, `bb-cli`, `sis-cli`). Upgrading from the old layout: reinstall from the new path; stored credentials in `~/.bb-cli/` and `~/.sis-cli/` carry over untouched — no re-login needed
2. Init (strongly recommended): run `cuhksz-cli bb login` and/or `cuhksz-cli sis login` manually once to leave stored credentials (`--username <student-id>`; password via the `BB_CLI_PASSWORD` / `SIS_CLI_PASSWORD` env var or interactive prompt; `--no-store` keeps it off disk; sessions live in `~/.bb-cli/session.json` / `~/.sis-cli/session.json`). The first login automatically becomes the **default account** per backend; confirm with `<backend> default`, switch with `<backend> default <name>`. Automatic re-login (401-triggered) only ever uses the **default account**; other stored accounts are never auto-logged-in
3. Self-check: `cuhksz-cli bb status --format text` → `authenticated=yes` means ready; `cuhksz-cli sis status` lists local session/credential evidence and registered components (no network check — sessions are minute-scale, commands auto-relogin)

## Steps

1. `cuhksz-cli bb status` / `cuhksz-cli sis status` to confirm the session
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

## Schedule query routing (sis)

For timetable or next-class questions in a wiki instance, first read `wiki/calendar.md` and the relevant `wiki/calendar/YYYY-MM.md` month projection (including the next month if the requested date crosses a month boundary). Answer locally when the projection identifies the matching SIS source, covers the requested dates, and has an unexpired `stale_after`. If the projection is absent, stale, lacks freshness/source evidence, or does not cover the requested dates, use SIS as the source under the user's authorization; an explicit request to refresh overrides the local-cache preference. Outside a wiki instance, this connector remains usable directly.

## Known limits

- bb: 404 under student sessions for `gradebook/attempts` (flat), `discussion/forums`, `users/me/memberships`, `tasks`, `gradebook/grades`; Classic (JSP) courses only, Ultra unverified; write operations deliberately not provided
- sis: `exam` returns empty until the school publishes the term's exam schedule; `assignments` (per-assignment gradebook) usually shows "no information" — use `grades`; Tuition/Finances and enrollment-cart read views not registered — explore via `raw` first, then wrap; PIA upgrades or sign-in page changes break the chain — re-run with `SIS_CLI_DEBUG=<dir>` to capture evidence
- bb raw pass-through accepts GET only; sis raw POST is restricted to registered components

## Prohibitions

- Never perform write operations (submitting/posting on bb; enroll/drop/swap/edit classes or any state-changing transaction on sis); if ever needed, requires explicit user instruction and separate design — the user faces academic penalties for enrollment misuse
- Student ids / passwords never enter the repo; never echo the password; credentials live only in `~/.bb-cli/` and `~/.sis-cli/`
- Do not paste raw sis component HTML (contains personal data) into the wiki or commit it; relay personal data in conversation only

## Language

Follow the upper-layer requirements and the conversation context. Keep course names, course codes, component names, file names, and paths verbatim.
