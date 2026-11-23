# cuhksz-cli — CUHK-SZ Unified Read-Only CLI Connector

One distribution, one install, one entry point:

- `cuhksz-cli bb <command> ...` — Blackboard (`bb.cuhk.edu.cn`, Learn Classic): courses / assignments / grades / announcements / course files / my submissions. Backend module: `bbcli/`
- `cuhksz-cli sis <command> ...` — SIS (`sis.cuhk.edu.cn`, PeopleSoft CS): weekly schedule / per-term grades / course history / enrollment dates / exam schedule / transcript. Backend module: `siscli/`
- `cuhksz-cli home status|migrate` — machine-substrate state: effective paths and the explicit legacy-home migration

The legacy `bb-cli` / `sis-cli` console scripts (thin wrappers since 0.2.1) were **removed in 0.3.0**; every command name, flag and output shape is unchanged under `cuhksz-cli bb ...` / `cuhksz-cli sis ...` (see the migration table in SKILL.md).

**A purely read-only data plane — no agent logic, no MCP, no monitoring** — serving as a fact interface for upper layers (wiki domain plugins / humans / scripts). Backend state is not aggregated into one directory, but both components live under the connector's single machine home:

```text
$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/bb/    # BB_CLI_HOME overrides
$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/sis/   # SIS_CLI_HOME overrides
```

`$OWFA_HOME` defaults to `~/.owfa`; all paths resolve through `.owfa/scripts/owfa_home.py` (the OWFA connector-home ABI). Upgrading from the old layout: reinstall, then run `cuhksz-cli home migrate --dry-run` followed by `cuhksz-cli home migrate` — credentials and sessions move with the directories, so no re-login is needed. A machine with no OWFA helper at all keeps using `~/.bb-cli` / `~/.sis-cli` and prints a one-line migration notice.

Since package version 0.2.1 this single connector replaces the former standalone bb and sis connector packages (same code, moved here — `git log --follow` reaches the full history); 0.3.0 completes the move onto the machine substrate.

## Installation

Use the instance's declared Python environment when one exists. Otherwise, from `connectors/cuhksz-cli`, choose one isolated environment; activation and global PATH changes are unnecessary.

Windows (PowerShell or Git Bash):

```text
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m cuhkszcli --help
```

macOS / Linux:

```text
python3 -m venv .venv
./.venv/bin/python3 -m pip install -e .
./.venv/bin/python3 -m cuhkszcli --help
```

On hosts using uv, `uv venv .venv` and `uv pip install --python .venv -e .` are an alternative. Deps: `curl_cffi` + `beautifulsoup4` only (`requirements.txt`). If the console script is not on PATH, run `python -m cuhkszcli --help` with the same interpreter that installed the package.

## Usage

```text
cuhksz-cli bb courses --format text
cuhksz-cli bb fetch <course> -o out/
cuhksz-cli sis schedule --days
cuhksz-cli sis grades --term '2026-27 Term 2'
cuhksz-cli home status
cuhksz-cli home migrate --dry-run
```

Full command tables and reverse-engineering notes live in [docs/bb.md](docs/bb.md) and [docs/sis.md](docs/sis.md); agent-facing usage, login discipline and the migration section in [SKILL.md](SKILL.md). Offline regression tests: `python -m unittest discover tests` (synthetic cookies only, no network; the substrate tests need `OWFA_HOME_HELPER` pointing at a framework checkout and use temp directories).

Both `status` commands are **offline tri-state probes** (zero network, zero login): bb reports `session_file` / `session_valid` (local cookie liveness) / `auto_relogin` (`available` | `blocked (no stored credentials)` | `blocked (no default account)`); sis reports the same state/capability split as `session` / `relogin` plus unknown `reachable`. A stale session with re-login capability available is not an error — only `blocked` states need manual `login`. Full contracts: [docs/bb.md](docs/bb.md#status-contract-tri-state-offline), [docs/sis.md](docs/sis.md#status-contract-031).

## Changelog

- **0.4.3** (2026-11-23): default-term fix — `sis grades`/`appt`/`exam` without `--term` now pick the newest term **by label ordering** (start year, then Term 1 < Term 2 < Summer), not page position. Live: `appt`/`exam` radios are oldest-first and used to resolve 2025-26 Term 1, while `grades` (newest-first) resolved 2026-27 Term 2; all three now resolve 2026-27 Term 2. `parser.default_term` accepts both term-row shapes so Class Search and the term-query pages share one ordering rule; explicit `--term` is unchanged (exact strm, else first label-substring match in page order). `_capped_course_ids` keys failures by (title, occurrence) so same-title courses are not conflated. Docs: Summer Session limits (Max 6.00, no Min row — live 2025-26 Summer) and the Summer strm digit 5 (2550/2650). Version anchors bumped to 0.4.3. **No command or flag changes**; the only JSON addition is the `occurrence` field on `expansion_failed` notes.
- **0.4.2** (2026-11-23): fix `sis appt` mislabeling the enrollment unit limits. The live page puts both labels in one row and both values in the next (`Max Total Units | Min Total Units`, then `18.00 | 9.00`), so the old per-line label→number regex paired `Min` with `18.00` and dropped `Max`; `parse_appt` now reads the `Enrollment Limits` table's label cells then value cells in document order and zips them (with a text fallback and an empty `limits` on a malformed page). Text output prints Max first and adds a one-line cap hint; **JSON `limits` keeps its existing dict shape** (`{"Max Total Units": "18.00", "Min Total Units": "9.00"}`). `--term` now also accepts the strm code on the shared grades/appt/exam term path (derived from the label, since those pages expose labels only), matching `sis search`. `bbcli` / `siscli` `__version__` anchors now match the distribution (0.4.2). Removed `migrations/0.4-to-0.4.1.md` — the kernel's `_stage_migrations` only matches two-part `A.B-to-C.D` names, so the three-part patch-level file never ran; its user-facing note lives in this changelog. **No command, flag or JSON-key changes** — the `appt` text line order and the cap hint changed by design.
- **0.4.1** (2026-11-23): `sis search --all-sections` — SIS renders only the first 3 sections per course, so the new flag expands every course's "View All Sections" list via the page's own read-only `$ICFieldNNN$hviewall$<course-index>` AJAX action (sequential, capped at 30 courses, per-request timeout; a failed expansion degrades to the rendered sections with a structured note). JSON gains per-course `sections_complete` / `sections_expanded` plus top-level `all_sections` / `notes`; text output marks expanded courses `N sections (all)` and groups mixed `LEC:` / `TUT:` / `SUP:` sections. **Additive** — the default is still the fast first-3 view.
- **0.4.0** (2026-11-23): new read-only `cuhksz-cli sis search` — Class Search lists a term's courses with their sections, meeting times, rooms and instructors (two-step AJAX query on `SA_LEARNER_SERVICES.CLASS_SEARCH.GBL`; open sections only by default; advisory only — no cart, no enrollment, no state change). Non-breaking: a new command, flag and output shape only — no existing command, flag or JSON key changed; plus the new `sis-course` member plugin and its skill live in the package repo.

## Layout

- `cuhkszcli/` — dispatcher (entry layer, no logic of its own) + `home.py` (substrate resolution / `home` commands' data layer)
- `bbcli/` — Blackboard backend (config / transport / auth / api / cli)
- `siscli/` — SIS backend (config / transport / auth / api / parser / cli)
- `tests/` — offline regressions
- `docs/` — per-backend full reference (the old connector READMEs, kept current)
