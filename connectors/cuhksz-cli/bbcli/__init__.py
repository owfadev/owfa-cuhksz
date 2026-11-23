"""bbcli — CUHK-SZ Blackboard backend of cuhksz-cli (bb subcommand).

Layering: config (paths and settings) / transport (curl_cffi session and TLS
fingerprint) / auth (ADFS OAuth2 login) / api (Learn REST wrappers) / cli
(command surface).
Discipline: read-only — never issues any write request; credentials and
sessions live only in the machine substrate
($OWFA_HOME/connectors/cuhksz-cli/homes/<id>/bb/), never in any repository.
Since cuhksz-cli 0.2.1 this module ships in the `cuhkszcli` distribution;
the legacy `bb-cli` entry point was removed in 0.3.0.
"""

__version__ = "0.4.2"
