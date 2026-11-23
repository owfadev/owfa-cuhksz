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
cuhksz-cli sis grades --term 'Term 2'
cuhksz-cli home status
cuhksz-cli home migrate --dry-run
```

Full command tables and reverse-engineering notes live in [docs/bb.md](docs/bb.md) and [docs/sis.md](docs/sis.md); agent-facing usage, login discipline and the migration section in [SKILL.md](SKILL.md). Offline regression tests: `python -m unittest discover tests` (synthetic cookies only, no network; the substrate tests need `OWFA_HOME_HELPER` pointing at a framework checkout and use temp directories).

Both `status` commands are **offline tri-state probes** (zero network, zero login): bb reports `session_file` / `session_valid` (local cookie liveness) / `auto_relogin` (`available` | `blocked (no stored credentials)` | `blocked (no default account)`); sis reports the same state/capability split as `session` / `relogin` plus unknown `reachable`. A stale session with re-login capability available is not an error — only `blocked` states need manual `login`. Full contracts: [docs/bb.md](docs/bb.md#status-contract-tri-state-offline), [docs/sis.md](docs/sis.md#status-contract-031).

## Changelog

- **0.4.0** (2026-11-23): new read-only `cuhksz-cli sis search` — Class Search lists a term's courses with their sections, meeting times, rooms and instructors (two-step AJAX query on `SA_LEARNER_SERVICES.CLASS_SEARCH.GBL`; open sections only by default; advisory only — no cart, no enrollment, no state change). Non-breaking: no existing command, flag or output shape changes; plus the new `sis-course` member plugin and its skill live in the package repo.

## Layout

- `cuhkszcli/` — dispatcher (entry layer, no logic of its own) + `home.py` (substrate resolution / `home` commands' data layer)
- `bbcli/` — Blackboard backend (config / transport / auth / api / cli)
- `siscli/` — SIS backend (config / transport / auth / api / parser / cli)
- `tests/` — offline regressions
- `docs/` — per-backend full reference (the old connector READMEs, kept current)
