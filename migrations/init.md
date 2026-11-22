---
verb: init
verify: init.py
---
First-run setup for the cuhksz school domain (relay to the user in their language):

1. **Connector logins** — cuhksz-cli: `cuhksz-cli bb login` and `cuhksz-cli sis login` (ADFS SSO; credentials stay on this machine in the OWFA substrate — `$OWFA_HOME/connectors/cuhksz-cli/homes/<id>/bb` and `.../sis`, never in any repository). Machines upgraded from the pre-0.3 layout: run `cuhksz-cli home status`, then `cuhksz-cli home migrate --dry-run`, then `cuhksz-cli home migrate` to move the legacy `~/.bb-cli` / `~/.sis-cli` (the legacy `bb-cli` / `sis-cli` entry points were removed in connector 0.3.0 — use `cuhksz-cli bb|sis`). Guide the user through both logins; the connector skill ships its own login disclosure.
2. **Identity page** — wiki/cuhksz/identity.md per the identity constitution: pull the cuhksz-cli sis transcript, write the sis block mapping (student_id / college / school / major / admitted / status) + generated/trust fields.
3. **Territory & data zones** — wiki/cuhksz/ follows the identity page; cuhksz/{bb,registry}/ workspaces appear per-course on first mapping (lazy — do not pre-create).
4. **First term digest** (optional) — offer, never force.
5. **Compliance note (relay briefly)** — the package runs on the user's own credentials, read-only and at human pace, inside CUHK-SZ ITSO rules; boundary: personal-study use only, no bulk crawls, no credential sharing, no republishing of courseware (details in the package's COMPLIANCE.md).

Completion = the identity page carries the sis block; connector sessions are warning-level (the user may log in later, at first pull).
