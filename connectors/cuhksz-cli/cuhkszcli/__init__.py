"""cuhksz-cli — unified read-only CLI connector for the CUHK-SZ school systems.

One entry, two backends (unchanged modules, moved in-repo under this
connector): `bbcli` reads bb.cuhk.edu.cn (Blackboard Learn), `siscli` reads
sis.cuhk.edu.cn (PeopleSoft Campus Solutions). `cuhksz-cli bb <...>` and
`cuhksz-cli sis <...>` dispatch to them; `cuhksz-cli home status|migrate` is
the machine-substrate surface. The legacy `bb-cli` / `sis-cli` console
scripts were removed in 0.3.0.

Credential stores are NOT aggregated into one directory: bb sessions/config
live in the `bb` component and sis in the `sis` component of the connector's
single substrate home, `$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/`
(`BB_CLI_HOME` / `SIS_CLI_HOME` remain explicit compatibility overrides).
See the migration section of SKILL.md.

Discipline: read-only — never issues any write request (the deliberate
exceptions, inherited from siscli, are query-only POSTs on PeopleSoft
search pages: the term-selection "Continue", the two-step Class Search
AJAX flow, and the per-course "View All Sections" (`hviewall`) expansion);
credentials and sessions live only in the machine substrate, never in any
repository.
"""

__version__ = "0.4.3"
