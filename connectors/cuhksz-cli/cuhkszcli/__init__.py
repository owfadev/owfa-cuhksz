"""cuhksz-cli — unified read-only CLI connector for the CUHK-SZ school systems.

One entry, two backends (unchanged modules, moved in-repo under this
connector): `bbcli` reads bb.cuhk.edu.cn (Blackboard Learn), `siscli` reads
sis.cuhk.edu.cn (PeopleSoft Campus Solutions). `cuhksz-cli bb <...>` and
`cuhksz-cli sis <...>` dispatch to them; the legacy `bb-cli` / `sis-cli`
console scripts keep working unchanged as thin wrappers over the same
backends.

Credential stores are NOT aggregated: bb sessions/config stay in ~/.bb-cli/
(BB_CLI_HOME), sis in ~/.sis-cli/ (SIS_CLI_HOME) — exactly as before.

Discipline: read-only — never issues any write request (the single
deliberate exception, inherited from siscli, is the term-selection
"Continue" POST on PeopleSoft search pages); credentials and sessions live
only in the user directory, never in any repository.
"""

__version__ = "0.2.1"
