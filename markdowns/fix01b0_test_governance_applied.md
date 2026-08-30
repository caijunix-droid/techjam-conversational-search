# FIX-01B0 — Test Governance Applied (Option 1: Archive)

Status: **test-classification move only, executed as authorized.** No production-code
edit. Nothing staged. No commit. FIX-01B1 not started.

---

## Historical test original path

```
tests/test_intent_override_fix01.py
```

## Historical test archived path

```
markdowns/historical_tests/test_intent_override_fix01.py
```

Moved via plain filesystem move (the file was untracked in git — created earlier this
session and never committed — so no `git mv` history to preserve; a `mkdir -p` + `mv`
achieves the same byte-for-byte relocation).

## Pre/post historical-test SHA256

```
Before move: 016c76ed8917a1efc89181d572a1eaac2b93294dfecac744ba2a1106645d775e
After move:  016c76ed8917a1efc89181d572a1eaac2b93294dfecac744ba2a1106645d775e
```

**Identical.** FIX-01A historical test preserved byte-for-byte. Removed from active
discovery only — no content was altered.

---

## Active unittest discovery results (post-archival)

```bash
python3 -m unittest tests.test_evaluator
python3 -m unittest tests.test_fix01b0_state_retrieval_decoupling
python3 -m unittest discover -s tests -p 'test*.py' -v
```

```
tests.test_evaluator:                          3/3 PASS
tests.test_fix01b0_state_retrieval_decoupling: 10/10 PASS

Full discovery: Ran 13 tests in 0.012s — OK
13 tests, 13 PASS, 0 FAIL, 0 ERROR, 0 SKIP
```

Matches the directive's expected post-archival count (13/13) exactly — not forced,
actually observed.

---

## `starter/agent.py` SHA256

```
0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
```

Identical to the value recorded before this test-governance pass began and to the
FIX-01B0 candidate reviewed in `fix01b0_state_retrieval_decoupling_handover.md` and
`fix01b0_precommit_test_hygiene.md`.

## git status

```
 M starter/agent.py
?? markdowns/fix01_cleanup_inspection.md
?? markdowns/fix01_intent_override_handover.md
?? markdowns/fix01_prepatch_verification.md
?? markdowns/fix01_restored_baseline.md
?? markdowns/fix01a_revert_and_architectural_finding.md
?? markdowns/fix01b0_precommit_test_hygiene.md
?? markdowns/fix01b0_state_retrieval_decoupling_handover.md
?? markdowns/historical_tests/
?? markdowns/patches/
?? markdowns/probes/probe_fix01b0_override_and_equivalence.py
?? tests/test_fix01b0_state_retrieval_decoupling.py
```

`tests/test_intent_override_fix01.py` no longer appears (moved, not deleted — its
contents now live at `markdowns/historical_tests/test_intent_override_fix01.py`).

## Confirmation no production edit

`git diff --stat -- starter/agent.py` shows the same `52 insertions(+), 6 deletions(-)`
as the already-reviewed FIX-01B0 patch — no new hunks were introduced by this pass. This
test-governance operation touched only test-file location, nothing under `starter/`.

## Confirmation nothing staged

```bash
git diff --cached --stat
# (empty)
```

## Confirmation no commit

No `git commit` was run at any point in this pass.

## Confirmation FIX-01B1 not started

No changes to retrieval logic, `active_slots` logic, BM25, query construction, question
policy, or benchmark behavior were made or attempted. `starter/agent.py`'s hash is
unchanged from the FIX-01B0 candidate, so no re-run of the 200-session benchmark was
performed (per directive §6 — not required when the candidate is byte-identical).

---

## Authorization boundary (unchanged from directive)

```
TEST-GOVERNANCE MOVE: APPLIED
PRODUCTION CODE EDIT: NOT AUTHORIZED, NOT DONE
FIX-01B0 COMMIT: NOT YET AUTHORIZED
FIX-01B1: NOT AUTHORIZED, NOT STARTED
```

STOP. Awaiting review for final commit decision on FIX-01B0.
