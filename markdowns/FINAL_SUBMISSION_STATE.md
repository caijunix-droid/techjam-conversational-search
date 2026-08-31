# FINAL SUBMISSION STATE

Written 2026-08-31. Canonical record of the frozen scoring baseline for
this submission. Records only verified facts — each figure below was
re-confirmed directly (test run, evaluator run, or `git`/`shasum`
inspection) during the repository hardening pass that produced this file,
not copied forward from memory.

```text
Final scoring commit:
ce7114904b8cb97f6223e7419ef3923cce178a90

Final public metrics (200 public sessions):
HR@10          0.880000
MRR            0.567583
MTTC           5.495000
Efficiency     0.550500
TechnicalScore 0.720375

Hits:
176 / 200

Tests:
54 / 54 PASS

Simulation vs production:
0 / 200 mismatches
(verified in markdowns/fix05_implementation_handover.md §7)

Known runtime:
approximately 84.7-86.8 seconds / 200 sessions
(measured on the development machine; not a universal figure)

Scoring status:
FROZEN
```

```text
Final score sprint:
NO SAFE EXPERIMENT FOUND

Reason:
remaining headroom lacked an evidence-backed, generalizable mechanism
strong enough to justify risking the locked 88% implementation.
Full evidence trail: markdowns/final_score_sprint_report.md
```

## What this file deliberately does not claim

- Not claimed: 88% private-set performance, real-world accuracy, or
  production-scale deployment readiness. The 88.0% figure is the public
  200-session HR@10 only.
- Not claimed: a confirmed root cause for the runtime increase under the
  final ranking tier. `markdowns/fix05_implementation_handover.md` §9
  documents a plausible hypothesis (an index gap on a lookup column) that
  was explicitly **not** verified with a profiler.

## Reproducibility, verified fresh during this hardening pass

```text
git status --short  (pre-hardening):  HEAD == origin/main == ce71149,
                                        only known untracked markdown docs

python3 -m unittest discover -s tests -p 'test*.py':  54 / 54 PASS

Fresh local clone of the committed repo state, catalog placed per the
README's own documented instructions, re-run from that clean clone:
  - unit tests:        54 / 54 PASS
  - agent import/init:  OK
  - demo import:        OK
  - full evaluator:     HR@10 0.880000, MRR 0.567583, MTTC 5.495000,
                         Efficiency 0.550500, TechnicalScore 0.720375,
                         reported_token_usage: 0 -- exact match to the
                         figures above, reproduced independently of the
                         working tree used for development.
```

## Full engineering history

Every experiment, simulation, and implementation report behind this final
state lives under `markdowns/`, in chronological order (`fix01_*` through
`fix05_*`, plus the final score sprint and this hardening pass). This file
is a summary pointer, not a replacement for that record.
