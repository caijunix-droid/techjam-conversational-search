# FIX-01 — Restored Baseline (steps 1–4 of the mandatory sequence, complete)

Status: cleanup executed and proven. **No FIX-01 implementation (provenance-aware
override replacement) has started yet** — this document covers only:

```
INSPECT 068e8fa                        ✅ (see markdowns/fix01_cleanup_inspection.md)
SURGICALLY REMOVE OUT-OF-SCOPE CHANGES ✅ (this document, §1)
PROVE RESTORED BASELINE                ✅ (this document, §2–§3)
REPRODUCE OVERRIDE DEFECT AGAIN         ✅ (this document, §4)
IMPLEMENT PROVENANCE-AWARE FIX-01       ⬜ not started
```

---

## 1. Cleanup performed

```bash
git revert --no-edit 068e8fa
```

Result:
```
[main 037b52d] Revert "Fix budget parsing and vague-answer handling in agent."
 2 files changed, 3 insertions(+), 29 deletions(-)
```

Applied cleanly, no conflicts, no manual hunk resolution needed (consistent with the
dry-run tested in `fix01_cleanup_inspection.md`).

**Verification that this is an exact restoration, not an approximation:**
```bash
git diff 9b5fc2f HEAD -- starter/agent.py demo/interactive.py   # empty
```
`starter/agent.py` and `demo/interactive.py` are now byte-identical to their state at
`9b5fc2f` (immediately before `068e8fa`). This removes exactly the 5 out-of-scope items
(expanded `BUDGET_RE`, expanded `NO_PREFERENCE_PHRASES`, `known_slot_count()`, the
demo's dynamic display, and the "0.73 → 0.675" comment) and nothing else — confirmed by
the identical hunk-for-hunk match already established in `fix01_cleanup_inspection.md`.

**Control-set files confirmed untouched:**
```bash
git diff 9b5fc2f..HEAD --stat -- evaluator/ docs/ data/public_set.jsonl starter/agent_baseline.py
# empty
```

**`markdowns/` preserved**: the revert only modified `starter/agent.py` and
`demo/interactive.py`; `c6461c4` (markdowns) and the two markdown files from this
investigation remain untouched and untracked.

---

## 2. Three-way state comparison

| | Branch/commit | git status | SHA256 `starter/agent.py` | SHA256 `demo/interactive.py` |
|---|---|---|---|---|
| **CURRENT-HEAD PRE-CLEANUP** | `main` @ `c6461c4` | clean | `03d4ecfcc0fdc0337c8d04465105b580c363b8591d797f1905276391fd4ed371` | (not separately hashed in prior pass) |
| **RESTORED FIX-01 BASELINE** | `main` @ `037b52d` | clean (+2 untracked `markdowns/*.md`) | `5b1d38d99fd49d8ba61e5f2ea278e8acfd665f8dfc50aa69f130e20415313544` | `53ef6c19903cca7c1cd85c61a6da7e78933ffde6ed627437e000def2a6f5c2b9` |
| **POST-FIX-01** | not yet reached | — | — | — |

`restored_baseline_agent.py`'s hash was independently confirmed to equal `9b5fc2f`'s
`starter/agent.py` hash via the empty `git diff` above (exact match, not merely "close").

---

## 3. Restored baseline — metrics (proven, not assumed)

Commands run twice, independent processes:
```bash
python3 -m unittest tests.test_evaluator
python3 -m evaluator.local_evaluator   # x2
```

**Unit tests**: 3/3 pass.

**Overall metrics** (identical across both runs — diff empty except session UUIDs):

| Metric | CURRENT-HEAD PRE-CLEANUP (prior pass) | RESTORED FIX-01 BASELINE | Delta |
|---|---:|---:|---:|
| Hit Rate@10 | 0.73 | 0.73 | 0 |
| MRR | 0.465458 | 0.465458 | 0 |
| MTTC | 6.345 | 6.345 | 0 |
| Efficiency | 0.4655 | 0.4655 | 0 |
| TechnicalScore | 0.597737 | 0.597737 | 0 |

**Scenario metrics** (restored baseline, both runs identical):

| Scenario | n | Hit Rate@10 | MRR | MTTC |
|---|---:|---:|---:|---:|
| Buying | 80 | 0.7875 | 0.436796 | 6.2875 |
| Browsing | 80 | 0.7125 | 0.470184 | 6.025 |
| Intent Override | 30 | 0.633333 | 0.520556 | 7.233333 |
| Boundary | 10 | 0.7 | 0.491667 | 6.7 |

**Zero metric delta from cleanup.** This is expected, not just tolerated: `068e8fa` only
changed `BUDGET_RE`/`NO_PREFERENCE_PHRASES` (phrasings the scripted evaluator's customer
never emits) and a cosmetic demo display — none of which the scripted 200-session
benchmark can exercise. Per the correction doc's own framing ("metric-neutral does not
mean behavior-neutral"), this zero-delta result is being reported as a fact about *this*
benchmark's coverage, not as proof the removed code was inert in every context (e.g. the
live demo, which does hit those phrasings — untested here, out of scope for FIX-01).

No STOP condition triggered — cleanup did not change any metric, so per the correction
doc's instruction, proceeding to defect re-reproduction (§4) rather than halting.

---

## 4. Override defect re-reproduced against restored baseline

Ran `markdowns/probes/probe_override_batch.py` (unchanged, itself untouched by the
revert) against the restored `037b52d` state:

```
Total override sessions: 30
old/new classified to SAME bucket (override overwrites cleanly): 6
old/new classified to DIFFERENT buckets: 24
Of those different-bucket cases, stale old value verified still present in slots after override: 24
```

**Identical to the pre-cleanup reproduction** (`fix01_prepatch_verification.md` §2):
24/30 cross-bucket sessions, 24/24 stale-state confirmed. The defect is not an artifact
of the now-removed `068e8fa` changes — it exists identically in the clean, isolated
baseline.

---

## 5. Conclusion — ready for FIX-01 implementation

| Correction-doc gate | Result |
|---|---|
| `068e8fa` fully and exactly reverted | ✅ confirmed via empty diff against `9b5fc2f` |
| Control-set files (evaluator/docs/data/baseline agent) untouched | ✅ confirmed via empty diff |
| Unrelated markdown work preserved | ✅ `markdowns/` untouched |
| Restored baseline metrics proven, not assumed | ✅ 2 runs, deterministic |
| No metric changed as a result of cleanup → no STOP triggered | ✅ zero delta on all 5 headline metrics and all 4 scenario breakdowns |
| Override defect re-confirmed on clean baseline | ✅ 24/30, 24/24 — unchanged |

All gates in the mandatory sequence up to "REPRODUCE OVERRIDE DEFECT AGAIN" are satisfied
against the actual restored code, not assumed from the pre-cleanup pass. The
provenance-aware Intent Override implementation itself (mandatory sequence step 5
onward — targeted tests, 30-session backtest, full 200-session A/B, session-level deltas,
final handover) has **not** started and awaits explicit go-ahead, consistent with the
scope lock (no other optimization, no touching price/budget/dense-retrieval/etc.).
