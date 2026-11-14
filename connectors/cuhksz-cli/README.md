# cuhksz-cli — CUHK-SZ Unified Read-Only CLI Connector

One distribution, one install, three entry points:

- `cuhksz-cli bb <command> ...` — Blackboard (`bb.cuhk.edu.cn`, Learn Classic): courses / assignments / grades / announcements / course files / my submissions. Backend module: `bbcli/`
- `cuhksz-cli sis <command> ...` — SIS (`sis.cuhk.edu.cn`, PeopleSoft CS): weekly schedule / per-term grades / course history / enrollment dates / exam schedule / transcript. Backend module: `siscli/`
- `bb-cli ...` / `sis-cli ...` — legacy thin wrappers, byte-for-byte the same backends (kept so existing scripts, skills and habits keep working; see the migration table in SKILL.md)

**A purely read-only data plane — no agent logic, no MCP, no monitoring** — serving as a fact interface for upper layers (wiki domain plugins / humans / scripts). Credentials and sessions are NOT aggregated: bb state stays in `~/.bb-cli/` (`BB_CLI_HOME`), sis state in `~/.sis-cli/` (`SIS_CLI_HOME`) — upgrading from the old two-connector layout requires no re-login.

Since package version 0.2.1 this single connector replaces the former `connectors/bb-cli/` and `connectors/sis-cli/` directories (same code, moved here — `git log --follow` reaches the full history).

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

On hosts using uv, `uv venv .venv` and `uv pip install --python .venv -e .` are an alternative. Deps: `curl_cffi` + `beautifulsoup4` only (`requirements.txt`). If a console script is not on PATH, run `python -m cuhkszcli --help` (or `python -m bbcli` / `python -m siscli`) with the same interpreter that installed the package.

## Usage

```text
cuhksz-cli bb courses --format text
cuhksz-cli bb fetch <course> -o out/
cuhksz-cli sis schedule --days
cuhksz-cli sis grades --term 'Term 2'
```

Full command tables and reverse-engineering notes live in [docs/bb.md](docs/bb.md) and [docs/sis.md](docs/sis.md); agent-facing usage and login discipline in [SKILL.md](SKILL.md). Offline regression tests: `python -m unittest discover tests` (synthetic cookies only, no network).

## Layout

- `cuhkszcli/` — dispatcher (entry layer, no logic of its own)
- `bbcli/` — Blackboard backend (config / transport / auth / api / cli)
- `siscli/` — SIS backend (config / transport / auth / api / parser / cli)
- `tests/` — offline regressions
- `docs/` — per-backend full reference (the old connector READMEs, kept current)
