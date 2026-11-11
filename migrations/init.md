---
verb: init
verify: init.py
---
First-run setup for the cuhksz school domain (relay to the user in their language):

0. **User Notice before login or data retrieval** — present https://github.com/owfadev/pkg-cuhksz/blob/master/USER_NOTICE.md ([简体中文](https://github.com/owfadev/pkg-cuhksz/blob/master/USER_NOTICE.zh-CN.md)). Briefly explain the read-only university-system boundary, local file changes, saved credentials/passwords, and possible cloud AI processing. Reading the notice or installing the package is not authorization for arbitrary queries or sharing; follow the user's actual task and access rights. Never ask for university passwords in the AI conversation; the user enters them in a local terminal.

1. **Connector logins** — bb-cli and sis-cli (ADFS SSO; credentials stay on this machine, ~/.bb-cli / ~/.sis-cli, never in any repository). Guide the user through both; each connector's skill ships its own login disclosure.
2. **Identity page** — wiki/cuhksz/identity.md per the identity constitution: pull the sis-cli transcript, write the sis block mapping (student_id / college / school / major / admitted / status) + generated/trust fields.
3. **Territory & data zones** — wiki/cuhksz/ follows the identity page; cuhksz/{bb,registry}/ workspaces appear per-course on first mapping (lazy — do not pre-create).
4. **First term digest** (optional) — offer, never force.
5. **Usage boundaries (relay briefly)** — own credentials, read-only university queries at human pace; personal-study use only, no bulk crawls, no credential sharing, and no unauthorized redistribution of courseware. Follow the User Notice linked above; COMPLIANCE.md provides the underlying references, not evidence of university or ITSO approval.

Completion = the identity page carries the sis block; connector sessions are warning-level (the user may log in later, at first pull).
