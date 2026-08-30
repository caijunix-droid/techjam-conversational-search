# FIX-01B0 — Pre-Commit Test-Hygiene Verification

Status: **investigation only. No production-code edit. No test-governance change applied.
No commit.** Per the directive, this pass exists solely to establish clean test-suite
governance facts before a commit decision is asked of the user.

---

## FIX-01B0 candidate SHA

```
0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
```

Confirmed matching the expected value both before this investigation started and again
after it finished (§6 below). `git diff -- starter/agent.py` shows only the already-
reviewed FIX-01B0 patch itself — no new edits.

---

## Core evaluator tests

```bash
python3 -m unittest tests.test_evaluator
```
```
Ran 3 tests in 0.002s — OK
```
3/3 PASS, as expected.

---

## FIX-01B0 focused tests

```bash
python3 -m unittest tests.test_fix01b0_state_retrieval_decoupling
```
```
Ran 10 tests in 0.012s — OK
```
10/10 PASS, as expected.

---

## Full unittest discovery result

```bash
python3 -m unittest discover -s tests -p 'test*.py' -v
```

```
Total tests run: 20
Passes:          19
Failures:        1
Errors:          0
Skips:           0
```

Exit code 1 (non-zero) due to the one failure below. Nothing hidden.

---

## Every failing/erroring test

Exactly one:

```
FAIL: test_different_attribute_override_removes_old_and_sets_new
      (tests.test_intent_override_fix01.IntentOverrideFix01Test
       .test_different_attribute_override_removes_old_and_sets_new)

AssertionError: 'feature' unexpectedly found in
  {'feature': 'Buckle closure', 'material': 'leather'}
  : superseded feature constraint must be removed
```

**Classification: FIX-01A historical experiment test**, not a production regression and
not a violation of a current production invariant. Verified directly, not assumed:

- The test's own helper, `_slots()` (`tests/test_intent_override_fix01.py:35–36`), reads
  `self.agent._sessions[session_id].slots` only. This file has no reference anywhere to
  `active_slots` — it predates FIX-01B0's two-store architecture entirely (it was written
  for FIX-01A, where `slots` itself *was* the corrected active-intent store).
- The very same test's first assertion (line 43,
  `self.assertEqual(self._slots(session_id), {"feature": "Buckle closure"})`, checking
  state right after turn 1, before any override) **passes** — because at that point
  `slots` legitimately equals `{"feature": "Buckle closure"}` under both FIX-01A's and
  FIX-01B0's designs. Only the post-override assertion at line 49 fails, and it fails
  specifically because it expects `slots` (not `active_slots`) to reflect the override
  correction — a FIX-01A-specific expectation.
- The corresponding production invariant under the current (FIX-01B0) architecture —
  "the superseded value is removed from *active* intent" — is separately and
  successfully verified by `tests/test_fix01b0_state_retrieval_decoupling.py::
  test_a_different_bucket_active_state_correct`, which passed in both the focused run
  and the full discovery run above.

No other test file, and no other test within `test_intent_override_fix01.py`, exercises
a production invariant that FIX-01B0 violates. The remaining 6 tests in that file pass
because they either check same-bucket behavior (where `slots` and `active_slots` coincide
under both architectures, since a same-key dict overwrite behaves identically either way)
or don't touch the cross-bucket deletion assertion at all.

| Test file | Status | Classification |
|---|---|---|
| `tests/test_evaluator.py` | 3/3 pass | Production regression suite |
| `tests/test_fix01b0_state_retrieval_decoupling.py` | 10/10 pass | Current production candidate's own test suite |
| `tests/test_intent_override_fix01.py` | 6/7 pass, 1 fail | FIX-01A historical experiment test suite — the 1 failure is a superseded-architecture assertion, not a regression |

---

## Recommended test-governance treatment (proposal only — NOT applied)

Per the directive, this section is a proposal for review, not an action taken. Three
options, smallest-change first:

1. **Move the file out of `tests/` discovery path** — e.g. relocate
   `test_intent_override_fix01.py` to `markdowns/patches/` or a new
   `markdowns/historical_tests/` directory, alongside the other preserved FIX-01A
   evidence (`fix01_intent_override_handover.md`, `fix01a_intent_override.patch`). This
   keeps the file byte-for-byte as historical evidence but removes it from
   `python -m unittest discover`'s default `tests/` scope, so full-suite runs are green
   without deleting or rewriting anything.

2. **Add an explicit skip/annotation in place**, e.g. wrap the one failing test (or the
   whole `IntentOverrideFix01Test` class) with `@unittest.skip("FIX-01A historical "
   "architecture (single-store slots) superseded by FIX-01B0's active_slots/slots split "
   "— see markdowns/fix01a_revert_and_architectural_finding.md")`. This keeps the file in
   `tests/` (so `git blame`/history stays where developers expect it) and makes the
   reason machine-visible in the test report itself, but does modify the file's content.

3. **Leave it exactly as-is and document the expected single failure** in whatever CI/
   local-dev instructions the team uses (e.g. a note in `README.md` or a Devpost
   write-up), accepting that `python -m unittest discover` will always show 1 known
   failure until/unless option 1 or 2 is applied.

No option has been applied. `tests/test_intent_override_fix01.py` remains byte-identical
to how FIX-01A left it.

---

## Confirmation `starter/agent.py` unchanged

```
SHA256 before this investigation: 0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
SHA256 after this investigation:  0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
```
Identical. `git diff -- starter/agent.py` shows only the already-reviewed FIX-01B0 patch,
no new hunks introduced during this pass.

## Confirmation no commit

```
git status --short
```
shows `M starter/agent.py` (uncommitted) plus untracked markdown/test/probe files.
`git diff --cached --stat` is empty — nothing staged, nothing committed.

---

STOP. No test-governance option has been applied. No commit made. No FIX-01B1 work
started. Awaiting review and explicit authorization on which (if any) test-governance
treatment to apply.
