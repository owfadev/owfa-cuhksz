"""Dispatcher: routes `cuhksz-cli bb ...` / `cuhksz-cli sis ...` to the
backend command surfaces. No logic of its own — argument parsing, auth and
output all stay inside bbcli.cli / siscli.cli.
"""

from __future__ import annotations

import sys

from . import __version__

USAGE = """\
cuhksz-cli — unified read-only connector for the CUHK-SZ school systems

usage: cuhksz-cli <backend> <command> [options]

backends:
  bb    Blackboard (bb.cuhk.edu.cn) — courses/assignments/grades/announcements/
        course files/submissions; credentials in ~/.bb-cli/ (unchanged)
  sis   SIS (sis.cuhk.edu.cn, PeopleSoft) — schedule/grades/history/enrollment
        dates/exams/transcript; credentials in ~/.sis-cli/ (unchanged)

examples:
  cuhksz-cli bb courses --format text
  cuhksz-cli bb status
  cuhksz-cli sis schedule --days
  cuhksz-cli sis grades --term 'Term 2'

legacy entry points `bb-cli ...` / `sis-cli ...` remain available as thin
wrappers (identical behavior); see SKILL.md for the migration mapping.
"""


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
    print(f"cuhksz-cli: unknown backend {args[0]!r} (expected 'bb' or 'sis')",
          file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
