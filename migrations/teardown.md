---
verb: teardown
---
Semantic deletion (x->0) for the cuhksz school domain — relay to the user, confirm before each step; data deletion always belongs to the human:

1. **Deprecate, never delete**: mark wiki/cuhksz/ territory pages `status: deprecated` (identity.md, term digests, course territories); the cuhksz/ data zone stays as-is unless the user explicitly orders removal
2. **Semantic registrations**: clean the anchors — profile.md `## Domain Cognition` lines (bb-track), language.md consumer precedents (bb-teach / bb-quiz), calendar source keys, cron pages depending on bb members
3. **Processes**: stop any cuhksz-cli (bb/sis) background jobs (none typical — read-only pullers)
4. **Credentials**: connector state lives in the OWFA substrate `$OWFA_HOME/connectors/cuhksz-cli/homes/` (legacy `~/.bb-cli` / `~/.sis-cli` on a machine never migrated; `cuhksz-cli home status` locates it) — remind, never delete

Default gate: the kernel residual scan (anchors clean = clear).
