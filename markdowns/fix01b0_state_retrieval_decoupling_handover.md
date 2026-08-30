# FIX-01B0 — Active Intent / Retrieval Evidence Decoupling Handover

Status: **implemented, tested, benchmarked. NOT committed.** Working tree left modified
for review. No FIX-01B1, no weight tuning, no reranking, no commit.

---

## 0. Repository state

| | Value |
|---|---|
| Branch | `main` |
| Commit (pre-patch) | `037b52d` |
| git status (pre-patch) | clean except pre-existing untracked `markdowns/*.md` files from earlier FIX-01/FIX-01A work |
| Baseline `starter/agent.py` SHA256 | `5b1d38d99fd49d8ba61e5f2ea278e8acfd665f8dfc50aa69f130e20415313544` (confirmed matching accepted baseline before any edit) |
| Post-patch `starter/agent.py` SHA256 | `0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354` |
| Commit created | **No.** `git status --short` shows `M starter/agent.py` plus new untracked test/probe files; nothing staged or committed. |

Confirmed before editing: `git diff -- starter/agent.py` was empty and the hash matched
the accepted baseline exactly — no material difference from the directive's assumed
starting state, so no STOP was triggered at step 1.

---

## 1. Baseline reproduction (pre-patch)

```bash
python3 -m unittest tests.test_evaluator   # 3/3 pass
python3 -m evaluator.local_evaluator        # matches reference exactly
```

```
HR@10 = 0.730000
MRR = 0.465458
MTTC = 6.345000
Efficiency = 0.4655
TechnicalScore = 0.597737
```

All four scenario metrics also matched the directive's quoted reference exactly. No STOP
triggered.

---

## 2. Hypothesis

`SessionState.slots` was doing two jobs: it represented **active customer intent** (read
by `_next_ask_attribute` to decide what's still unknown) and it supplied the **literal
retrieval terms** (read by `_build_query`). FIX-01A proved that correctly removing a
superseded value from this one shared structure also removes it as retrieval evidence,
costing MRR/MTTC even though the semantic fix itself was correct (see
`fix01a_revert_and_architectural_finding.md`, §E).

FIX-01B0's hypothesis: separating the two roles into two stores lets active intent be
corrected (superseded value removed from *active* state) while retrieval evidence keeps
accumulating exactly as the accepted baseline would, preserving the benchmark score.

---

## 3. Implementation

**File changed**: `starter/agent.py` only. Full diff reviewed before any test was run.

**Active-state representation**: `SessionState` gains `active_slots: dict[str, str]`
(mirrors `slots` at every write site) plus `override_source_attr`/`override_source_value`
provenance (same mechanism as FIX-01A, but scoped only to `active_slots`).

**Retrieval-evidence representation**: `slots` itself. Its population code is **byte-for-
byte unchanged** from the accepted baseline at every call site, including the override
branch, which still just does `state.slots[classify(new_value)] = new_value` with no
deletion — exactly the original (defective, for active-state purposes) baseline behavior,
kept deliberately so `_build_query()` (also untouched) produces identical output to
baseline by construction.

**Why retrieval should stay baseline-equivalent**: `_build_query` was not modified at all
— it still reads only `state.slots`. Since every `slots`-writing line is untouched, its
output is guaranteed identical to baseline for any given message sequence; this is a
structural guarantee, not a behavior that could drift, and it was independently measured
anyway (§6) rather than only asserted.

**Dialog logic uses active state**: `_next_ask_attribute`'s "already filled" check was
changed from `if attr in state.slots` to `if attr in state.active_slots`, so a superseded
attribute becomes askable again once removed from active intent, without being blocked by
`slots` still remembering it.

---

## 4. Targeted tests (A–F)

New file: `tests/test_fix01b0_state_retrieval_decoupling.py`, 10 tests. Does **not**
modify `tests/test_intent_override_fix01.py` (FIX-01A's own suite, preserved per
directive §14 — see note in §11 on that suite's one now-expected failure).

Retrieval-equivalence assertions in this suite compare against the actual accepted-
baseline `Agent` class, loaded directly from its git blob (`git show 037b52d:...`,
hash-checked against `5b1d38d9...` before use) — not a hand-copied re-implementation, to
remove any risk of the comparison oracle silently drifting from the real baseline.

| Test | Case | Result |
|---|---|---|
| `test_a_different_bucket_active_state_correct` | A | ✅ old `feature` gone from active state |
| `test_a_different_bucket_retrieval_evidence_retains_prior_term` | A | ✅ retrieval evidence still has both `feature` and `material` |
| `test_b_same_bucket_active_state_replaces_value` | B | ✅ `color` → white in active state |
| `test_b_same_bucket_retrieval_matches_baseline_exactly` | B | ✅ retrieval evidence and query string byte-identical to real baseline agent (black does not survive in either — baseline's own same-key overwrite, not "arbitrary accumulation") |
| `test_c_unrelated_active_constraints_survive` | C | ✅ `material`/`budget` unaffected by the override |
| `test_d_ask_attribute_ignores_stale_retrieval_evidence` | D | ✅ `feature` present in `slots`, absent from `active_slots`, and correctly re-eligible to ask about |
| `test_e_retrieval_query_equivalence_representative_conversations` | E | ✅ 5 representative conversations (buying, browsing, both override shapes, boundary) — query string identical to real baseline agent in every case |
| `test_f_normal_buying_flow_matches_baseline` | F | ✅ |
| `test_f_normal_browsing_flow_matches_baseline` | F | ✅ |
| `test_f_normal_boundary_flow_matches_baseline` | F | ✅ |

```
Ran 10 tests in 0.014s — OK
```

---

## 5. 30-session Intent Override active-state validation

**Methodology note (an honest correction made mid-investigation, not hidden):** the first
version of this probe measured `active_slots` at the *end* of the full 10-turn
conversation, and reported 24/24 still "stale" — apparently no improvement at all. Before
reporting that, a single-session turn-by-turn trace was run
(`public_0002`) and showed `active_slots` was in fact correctly cleared immediately after
the override turn (`{'material': 'leather'}`, no `feature`) — but by turn 8, the
evaluator's own scripted customer volunteered "Buckle closure" *again*, as an honest reply
to a properly re-asked `feature` question. This is legitimate, not a bug: the evaluator's
`initial_message()` never adds an intent-override session's `old_value` to its own
`disclosed` set, so that fact remains "not yet told to the agent" from the evaluator's own
bookkeeping and can be honestly re-offered once the attribute is freed up — which is
exactly what FIX-01B0's `_next_ask_attribute` fix is supposed to allow (directive §7: a
freed-up active attribute must be askable again). The end-of-conversation snapshot
conflated "never removed" with "removed correctly, then legitimately re-stated later."
The probe was corrected to snapshot `active_slots` immediately after the override turn
instead, matching the same methodology already used and trusted for FIX-01A.

**Corrected result:**

| | Reference (baseline `slots`) | FIX-01B0 (`active_slots`, snapshotted right after override) |
|---|---:|---:|
| Cross-bucket cases | 24 | 24 |
| Stale old value present | **24/24** | **0/24** |

No anomalies in the corrected run.

---

## 6. Retrieval-query equivalence (30/30 real sessions)

For every one of the 30 real Intent Override sessions, at every turn (not just the
override turn), `patched._build_query(state)` was compared against
`baseline._build_query(state)` (baseline = the actual accepted-baseline `Agent` loaded
from its git blob, run in parallel on the identical message sequence).

```
Retrieval query mismatches vs baseline: 0/30
All 30/30 override sessions: retrieval query byte-identical to baseline at every turn.
```

No mismatches to list.

---

## 7. Full 200-session benchmark

| Metric | Baseline | FIX-01B0 | Delta |
|---|---:|---:|---:|
| HR@10 | 0.730000 | 0.730000 | **0** |
| MRR | 0.465458 | 0.465458 | **0** |
| MTTC | 6.345000 | 6.345000 | **0** |
| Efficiency | 0.465500 | 0.465500 | **0** |
| TechnicalScore | 0.597737 | 0.597737 | **0** |

---

## 8. Scenario metrics

| Scenario | Metric | Baseline | FIX-01B0 | Delta |
|---|---|---:|---:|---:|
| Buying | HR@10 | 0.7875 | 0.7875 | 0 |
| Buying | MRR | 0.436796 | 0.436796 | 0 |
| Buying | MTTC | 6.2875 | 6.2875 | 0 |
| Browsing | HR@10 | 0.7125 | 0.7125 | 0 |
| Browsing | MRR | 0.470184 | 0.470184 | 0 |
| Browsing | MTTC | 6.025 | 6.025 | 0 |
| Intent Override | HR@10 | 0.633333 | 0.633333 | 0 |
| Intent Override | MRR | 0.520556 | 0.520556 | **0** |
| Intent Override | MTTC | 7.233333 | 7.233333 | **0** |
| Boundary | HR@10 | 0.7 | 0.7 | 0 |
| Boundary | MRR | 0.491667 | 0.491667 | 0 |
| Boundary | MTTC | 6.7 | 6.7 | 0 |

Every scenario, every metric: zero delta. This is the outcome FIX-01A could not achieve —
Intent Override's MRR/MTTC (which regressed under FIX-01A) are here fully preserved.

---

## 9. Session-level differences

Full 200-session `sessions` array compared by `sample_id` (hit / best_rank /
first_hit_turn) between the restored baseline run and the FIX-01B0 patched run:

```
Total sessions compared: 200
Sessions with changed outcome: 0
```

Not a single session's hit status, rank, or turn changed — including all 30 Intent
Override sessions, and specifically the 7 sessions that changed under FIX-01A
(`public_0004`, `public_0013`, `public_0084`, `public_0089`, `public_0103`, `public_0123`,
`public_0130`) are confirmed unchanged from baseline here.

---

## 10. Determinism

```bash
python3 -m evaluator.local_evaluator   # run 1
python3 -m evaluator.local_evaluator   # run 2
```
`diff` of the two run outputs (session UUIDs excluded) is empty. Deterministic.

---

## 11. Claims established (directly supported by evidence in this pass)

- Active-intent semantics are correct: 24/24 → 0/24 stale, measured immediately after the
  override turn on all 30 real sessions (same standard as FIX-01A's proof).
- Retrieval evidence is baseline-equivalent, not just "similar": 0/30 query-string
  mismatches across every turn of all 30 real override sessions, plus 10/10 targeted
  tests including exact-string comparisons against the real baseline `Agent` class loaded
  from git.
- Full 200-session benchmark shows **zero delta on every metric, every scenario, and
  every individual session** — the ideal outcome the directive names in its acceptance
  logic.
- `_next_ask_attribute` correctly treats a freed-up (post-override) attribute as
  re-askable, verified both by unit test (case D) and by the real-data finding in §5 that
  led to correcting the probe's own methodology.
- Existing `tests/test_evaluator.py` (3/3) is unaffected. The existing
  `tests/test_intent_override_fix01.py` (FIX-01A's suite) now has one expected failure:
  `test_different_attribute_override_removes_old_and_sets_new` asserts correctness via
  `state.slots` directly, which was FIX-01A's design (single store, `slots` *was* the
  corrected active state). Under FIX-01B0, `slots` is deliberately reverted to pure
  baseline-preserving retrieval evidence by design, and correctness now lives in
  `active_slots` — proven by this handover's own suite (case A). This is a
  known, understood consequence of the architecture change, not a regression; the file
  was preserved unmodified per directive §14 rather than "fixed" to keep passing.

## 12. Claims NOT established (explicit uncertainty)

- Whether this decoupling would also hold on the private 800-session set — not testable
  from this repo. The structural argument (same `intent_card()` code path, so old/new
  values sharing a target product) is the same inference already labeled in
  `fix01a_revert_and_architectural_finding.md` §E, carried forward unchanged, not
  re-verified independently here.
- Whether `active_slots` should eventually influence ranking (e.g., weighting active
  terms more heavily than merely-historical ones) — explicitly out of scope for FIX-01B0
  per the directive ("not supposed to beat the baseline... decouple first").
- Whether the one-off methodology bug in the first probe run (end-of-conversation
  snapshot) affected any other measurement in this handover — checked and ruled out: the
  query-equivalence check was always per-turn (not end-of-conversation only), and the
  full 200-session benchmark is an independent measurement unaffected by that probe's
  internal bug.

## 13. Recommendation (advisory only)

This is the directive's **ideal outcome**: active override semantics PASS, retrieval
query equivalence PASS (measured exactly, not approximately), full 200-session benchmark
is IDENTICAL to baseline on every metric and every individual session, and no commit has
been made pending review.

Advisory recommendation: **KEEP as a candidate for review** — unlike FIX-01A, there is no
measured cost to weigh against the semantic correctness gain. The open question is not
"is this worth the regression" (there is none) but whether the team wants to proceed to a
follow-up experiment that lets `active_slots` actually influence ranking (a new,
separate, not-yet-authorized piece of work) — this handover takes no position on that,
per the directive's explicit scope lock ("Decouple first").

No commit has been made. Working tree currently:
```
 M starter/agent.py
?? markdowns/fix01b0_state_retrieval_decoupling_handover.md
?? markdowns/probes/probe_fix01b0_override_and_equivalence.py
?? tests/test_fix01b0_state_retrieval_decoupling.py
```
(plus the pre-existing untracked FIX-01/FIX-01A markdown and test files, all preserved
unmodified per directive §14).
