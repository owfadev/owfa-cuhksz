"""bbcli — CUHK-SZ Blackboard backend of cuhksz-cli (bb subcommand).

Layering: config (paths and settings) / transport (curl_cffi session and TLS
fingerprint) / auth (ADFS OAuth2 login) / api (Learn REST wrappers) / cli
(command surface).
Discipline: read-only — never issues any write request; credentials and
sessions live only in the user directory (~/.bb-cli/, unchanged), never in
any repository.
Since cuhksz-cli 0.2.1 this module ships in the `cuhkszcli` distribution;
the standalone `bb-cli` entry point remains as a thin wrapper.
"""

__version__ = "0.2.1"
