"""Dispatcher: routes `cuhksz-cli bb ...` / `cuhksz-cli sis ...` to the
backend command surfaces and `cuhksz-cli home ...` to the substrate commands.
No logic of its own beyond dispatch — argument parsing, auth and output all
stay inside bbcli.cli / siscli.cli / home.py.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, home

USAGE = """\
cuhksz-cli — unified read-only connector for the CUHK-SZ school systems

usage: cuhksz-cli <backend> <command> [options]

backends:
  bb    Blackboard (bb.cuhk.edu.cn) — courses/assignments/grades/announcements/
        course files/submissions
  sis   SIS (sis.cuhk.edu.cn, PeopleSoft) — schedule/grades/history/enrollment
        dates/exams/transcript
  home  machine-state substrate — status / migrate (legacy home migration)

State lives under $OWFA_HOME/connectors/cuhksz-cli/homes/<id>/{bb,sis}
(`cuhksz-cli home status` prints the effective paths).

examples:
  cuhksz-cli bb courses --format text
  cuhksz-cli bb status
  cuhksz-cli sis schedule --days
  cuhksz-cli sis grades --term 'Term 2'
  cuhksz-cli home status
  cuhksz-cli home migrate --dry-run
"""


def _home_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cuhksz-cli home",
                                description="OWFA machine-substrate state for cuhksz-cli")
    sub = p.add_subparsers(dest="home_cmd", required=True)

    s = sub.add_parser("status", help="where bb/sis state lives (read-only; writes nothing)")
    s.add_argument("--root", default="", help="workspace root to resolve the binding for (default: cwd/OWFA_ROOT)")
    s.add_argument("--format", choices=["json", "text"], default="json")
    s.set_defaults(fn=_home_status)

    s = sub.add_parser("migrate", help="move ~/.bb-cli and ~/.sis-cli into the substrate (never a side effect)")
    s.add_argument("--dry-run", action="store_true", help="inspect and report only: moves nothing, registers nothing")
    s.add_argument("--root", default="", help="workspace root to bind (default: cwd/OWFA_ROOT)")
    s.add_argument("--format", choices=["json", "text"], default="json")
    s.set_defaults(fn=_home_migrate)
    return p


def _home_status(args) -> int:
    data = home.status(root=args.root)
    if args.format == "text":
        print(f"connector: {data['connector']}")
        print(f"helper:    {data['helper'] or '(none — legacy fallback)'}")
        if data["helper_problem"]:
            print(f"           {data['helper_problem']}")
        for component, row in data["components"].items():
            print(f"{component}: {row['state_dir']} ({row['source']})")
            if row["override_value"]:
                print(f"   explicit override {row['override_env']}={row['override_value']}")
            if row["legacy_present"]:
                print(f"   legacy {row['legacy_home']} is still present"
                      + (" (already migrated: symlink)" if row["legacy_is_symlink"] else
                         "" if not row["legacy_has_state"] else " and holds state — migrate it"))
        substrate = data.get("substrate")
        if substrate and "home" in substrate:
            print(f"home:      {substrate['home']}")
            print(f"components on disk: {', '.join(substrate['components']) or '(none)'}")
            for key in ("exclusivity_violations", "stale_bindings"):
                if substrate[key]:
                    print(f"{key}: {json.dumps(substrate[key], ensure_ascii=False)}")
        return 0
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _home_migrate(args) -> int:
    try:
        data = home.migrate(dry_run=args.dry_run, root=args.root)
    except home.MigrationError as exc:
        # Structured error on stdout (a stable contract even for text mode), human line on stderr.
        print(json.dumps(exc.detail, ensure_ascii=False, indent=2))
        print(f"cuhksz-cli home migrate: {exc}", file=sys.stderr)
        return 1
    if args.format == "text":
        if args.dry_run:
            print("dry run — nothing was moved and no binding was registered")
        elif data.get("already_migrated"):
            print("already migrated — nothing was moved")
        else:
            print(f"migrated: {', '.join(data.get('migrated') or []) or '(none)'}")
        for row in data["components"]:
            print(f"{row['component']}: {row['action']}")
            print(f"   legacy: {row['legacy']}")
            print(f"   target: {row['target']}")
            if row.get("binding_id"):
                print(f"   binding: {row['binding_id']} (home {row['home']})")
        return 0
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else (argv or []))
    if not args or args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if args[0] == "--version":
        print(__version__)
        return 0
    if args[0] == "bb":
        from bbcli.cli import main as bb_main
        return bb_main(args[1:]) or 0
    if args[0] == "sis":
        from siscli.cli import main as sis_main
        return sis_main(args[1:])
    if args[0] == "home":
        parsed = _home_parser().parse_args(args[1:])
        return parsed.fn(parsed)
    print(f"cuhksz-cli: unknown backend {args[0]!r} (expected 'bb', 'sis' or 'home')",
          file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
