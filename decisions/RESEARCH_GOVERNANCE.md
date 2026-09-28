# Research Governance

## Holdout consumption

Once a strategy has consumed a precommitted holdout, that holdout cannot be reused as pristine validation for a tuned descendant.

`us_equity_holdout_v1` was consumed by the three v0.2.0 strategies in Phase 3D-3. Phase 3D-4 used the frozen cohort and strategies only as a secondary rolling evidence layer after the Phase 3D-3 results had been viewed.

If a future v0.3.0 design is influenced by evidence from this holdout, `us_equity_holdout_v1` must not be described as unseen validation for that descendant. A new untouched validation dataset or cohort is required.

## Subsequent hypotheses

Future work must identify itself as exactly one of:

- parameter tuning of an existing hypothesis; or
- a genuinely new hypothesis.

Before either path starts, the researcher must:

1. pre-register the rationale;
2. pre-register falsification criteria;
3. freeze the specification;
4. create a new strategy version; and
5. designate a new untouched validation resource.

These requirements do not themselves authorize any strategy state transition or execution activity. An explicit human Research Director decision is required first.
