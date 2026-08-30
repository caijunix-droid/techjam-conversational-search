# FIX-01B2 — Active-Term Coverage Implementation Handover

Produced per the `FIX-01B2 IMPLEMENTATION AUTHORIZATION` (§11–§20) in
`FIX-01B2 — INDEPENDENT END-TO-END SIMULATION REVIEW.md`. Scope: implement exactly the
frozen active-term-coverage mechanism in `starter/agent.py`, verify it against the real
evaluator, and report whether it reproduces the simulation reference **without tuning
toward it**. **Implemented, tested, benchmarked — NOT committed, NOT pushed.**

---

## 1. Starting state (verified before editing)

```bash
git rev-parse HEAD
  # 500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647
shasum -a 256 starter/agent.py
  # 0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
python3 -m unittest discover -s tests -p 'test*.py'
  # Ran 13 tests in 0.020s — OK
python3 -m evaluator.local_evaluator
  # HR@10 0.730000  MRR 0.465458  MTTC 6.345000  TechnicalScore 0.597737
```

All matched the required starting state exactly before any edit was made.

---

## 2. Implementation diff (`starter/agent.py`, uncommitted)

```diff
diff --git a/starter/agent.py b/starter/agent.py
index ce97ec1..08edd73 100644
--- a/starter/agent.py
+++ b/starter/agent.py
@@ -252,6 +252,14 @@ class Agent:
         unique_terms = list(dict.fromkeys(_terms(combined)))[:40]
         return " OR ".join(f'"{term}"' for term in unique_terms)
 
+    def _active_terms(self, state: SessionState) -> list[str]:
+        # FIX-01B2: distinct active-intent terms only, from state.active_slots
+        # alone (never state.slots/category/profile_terms) -- same tokenizer
+        # as _build_query(). Used only to reorder an already-fixed candidate
+        # pool, never to change candidate generation itself.
+        combined = " ".join(state.active_slots.values())
+        return list(dict.fromkeys(_terms(combined)))[:40]
+
     def _next_ask_attribute(self, state: SessionState) -> str | None:
         for attr in ASK_ORDER:
             if attr in state.active_slots:
@@ -273,12 +281,47 @@ class Agent:
         if not expression:
             recommendations: list[dict] = []
         else:
+            # FIX-01B2: candidate generation query is unchanged (same
+            # expression/ORDER BY/field weights); only the retrieval depth is
+            # widened so a second-stage ranker has more than top_k candidates
+            # to reorder within. Never narrower than the caller's requested
+            # top_k, so the external top_k contract is preserved regardless.
+            internal_depth = max(50, top_k)
             rows = self.connection.execute(
                 "SELECT parent_asin FROM products WHERE products MATCH ? "
                 "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
-                (expression, top_k),
+                (expression, internal_depth),
             ).fetchall()
-            recommendations = [{"parent_asin": str(row[0])} for row in rows]
+            candidate_asins = [str(row[0]) for row in rows]
+
+            # FIX-01B2: active-term-coverage second-stage ranking. Candidate
+            # generation above is untouched; this only reorders the
+            # already-fixed candidate pool. Each candidate's score is the
+            # fraction of distinct active-intent terms it matches (no
+            # weights, no threshold); ties (including "no active terms at
+            # all", where every candidate scores 0/0 -> treated as equal)
+            # keep the original BM25 order.
+            active_terms = self._active_terms(state)
+            if active_terms and candidate_asins:
+                placeholders = ",".join("?" for _ in candidate_asins)
+                term_matches: dict[str, set[str]] = {}
+                for term in active_terms:
+                    term_expr = f'"{term}"'
+                    term_rows = self.connection.execute(
+                        f"SELECT parent_asin FROM products WHERE products MATCH ? "
+                        f"AND parent_asin IN ({placeholders})",
+                        (term_expr, *candidate_asins),
+                    ).fetchall()
+                    term_matches[term] = {str(r[0]) for r in term_rows}
+                baseline_index = {asin: i for i, asin in enumerate(candidate_asins)}
+
+                def _coverage(asin: str) -> float:
+                    matched = sum(1 for term in active_terms if asin in term_matches[term])
+                    return matched / len(active_terms)
+
+                candidate_asins.sort(key=lambda asin: (-_coverage(asin), baseline_index[asin]))
+
+            recommendations = [{"parent_asin": asin} for asin in candidate_asins[:top_k]]
 
         ask_attribute: str | None = None
         message = "Here are the closest matches I found so far."
```

### Exact candidate-depth logic

`internal_depth = max(50, top_k)` — retrieves at least 50 candidates via the unchanged
BM25 query, but never fewer than whatever `top_k` the caller actually requested (per
§13's robustness requirement: "internal candidate depth should never be less than
requested `top_k`"). The official harness always calls with `top_k=10`
(`docs/agent_api_contract.json`: `"top_k": {"const": 10}`), so `internal_depth` is 50 in
every real scored call; the `max()` only matters for a caller requesting more than 50,
which the contract does not permit but the code does not assume.

### Term-coverage computation and tie-breaking

`coverage(candidate) = (count of active_terms matched) / len(active_terms)`, computed
via one small `MATCH ... AND parent_asin IN (...)` query per active term, restricted to
the already-fetched candidate pool (never touching candidate generation). Candidates are
sorted by `(-coverage, baseline_index)` — Python's `sorted()`/`list.sort()` is stable, so
this is a pure comparator: descending coverage, and *any* tie (equal coverage, including
the "no active terms" case where the `if active_terms and candidate_asins:` guard skips
sorting entirely) falls back to the original BM25 order. The final response is always
`candidate_asins[:top_k]` — sliced after reordering, so it can never exceed the caller's
requested size regardless of how deep `internal_depth` was.

---

## 3. Targeted tests (A–I, directive §15)

New file: `tests/test_fix01b2_term_coverage_ranking.py`, using the same technique as the
FIX-01B0/B1 test suites — a controlled synthetic catalog plus the accepted `500fe7b`
`Agent` loaded from its git blob (hash-verified) as the baseline-equivalence reference.

| Case | What it asserts | Result |
|---|---|---|
| A. No active terms | Output byte-identical to B0 baseline (pure fallback) | pass |
| B. Higher coverage outranks lower | A 2/2-term candidate ranks ahead of two 1/2-term candidates | pass |
| C. Equal coverage preserves baseline order | Tie-broken candidates keep their original BM25 relative order | pass |
| D. Final recommendations ≤ `top_k` | Requesting `top_k=3` against a 10-candidate catalog returns exactly 3 | pass |
| E. Target outside internal depth never surfaces | A candidate with perfect (2/2) coverage but baseline rank 56 (of 56, in a 55-filler catalog engineered so fillers structurally outrank it on the *baseline* query) never appears in the top 10, proving the `LIMIT internal_depth` cutoff is enforced *before* reordering, not after | pass |
| F. Buying flow | Candidate set matches B0 baseline exactly; leather match promoted to front | pass |
| G. Browsing flow | No corruption, output identical to baseline | pass |
| H. Intent Override | `_active_terms()` contains the new term ("leather"), excludes the superseded old term ("buckle"/"closure"); `state.slots` still retains the old term (B0 untouched) | pass |
| I. Boundary flow | No corruption, output identical to baseline | pass |

```
python3 -m unittest tests.test_fix01b2_term_coverage_ranking -v
# Ran 9 tests in 0.015s — OK
python3 -m unittest discover -s tests -p 'test*.py'
# Ran 22 tests in 0.027s — OK   (13 pre-existing + 9 new, 0 fail, 0 error)
```

---

## 4. Real evaluator results vs. simulation reference

Ran `python3 -m evaluator.local_evaluator` against the actual implemented, uncommitted
`starter/agent.py` — **no code was adjusted to match the reference; this is what the
implementation produced on the first run.**

| Metric | Simulation reference | **Actual implementation** | Match |
|---|---|---|---|
| HR@10 | 0.805000 | **0.805000** | exact |
| MRR | 0.499431 | **0.499431** | exact |
| MTTC | 5.910000 | **5.910000** | exact |
| Efficiency | 0.509000 | **0.509000** | exact |
| TechnicalScore | 0.654129 | **0.654129** | exact |

Scenario metrics also matched exactly on every field (Boundary 0.8/0.501667/6.6,
Browsing 0.8/0.509142/5.6625, Buying 0.85/0.478378/5.75, Intent Override
0.7/0.528929/6.766667). **No divergence occurred, so no investigation or tracing was
required, and no tuning was performed or needed.**

---

## 5. Full 200-session comparison vs. B0

Computed against the real accepted `500fe7b` `Agent` (loaded from its git blob,
hash-verified) — not the simulation's synthetic proxy.

```
new hits:                    15
new misses:                   0
rank improvements:           30
rank regressions:              6
first-hit-turn improvements:   7
first-hit-turn regressions:    0
unchanged:                   149
```

`15 + 0 + 30 + 6 + 149 = 200` ✓. **Every one of these counts is identical to the
simulation's §17 reference table**, and — checked at the individual session level, not
just aggregate counts — the same 15 `sample_id`s are the new hits, with the same exact
turn/rank for each, and the same 6 `sample_id`s are the rank regressions, with the same
exact before/after rank and turn for each:

**New hits** (identical to simulation, all 15):
`public_0015` (t8/r1), `public_0016` (t10/r8), `public_0017` (t2/r8), `public_0035`
(t10/r10), `public_0040` (t3/r8), `public_0058` (t9/r9), `public_0064` (t4/r7),
`public_0078` (t8/r4), `public_0095` (t9/r5), `public_0097` (t9/r10), `public_0120`
(t8/r4), `public_0127` (t3/r6), `public_0171` (t9/r4), `public_0172` (t8/r5),
`public_0184` (t8/r6).

**Rank regressions** (identical to simulation, all 6):

| sample_id | scenario | B0 rank/turn | B2 rank/turn |
|---|---|---|---|
| public_0023 | intent_override | 1 / 9 | 10 / 5 |
| public_0093 | buying | 1 / 9 | 4 / 7 |
| public_0103 | intent_override | 5 / 4 | 8 / 4 |
| public_0116 | buying | 2 / 9 | 6 / 1 |
| public_0148 | buying | 5 / 7 | 10 / 1 |
| public_0190 | buying | 2 / 9 | 4 / 7 |

This is the same finding already documented in
`markdowns/fix01b2_term_coverage_end_to_end_simulation.md` §5 — the real implementation
did not surface anything the simulation missed, and vice versa.

---

## 6. Determinism

Real evaluator run twice against the implemented code:

```bash
python3 -m evaluator.local_evaluator --output run1.json
python3 -m evaluator.local_evaluator --output run2.json
```

Full `sessions` arrays and summary metrics compared programmatically:
`sessions identical: True`, `summary identical: True`.

---

## 7. Runtime measurement

Measured with matched methodology for both agents (index construction timed separately
from the 200-session `evaluate()` call, both via the same in-process harness — not one
via shell `time` and the other via an internal timer, which would not be an equivalent
comparison):

| | Index construction | `evaluate()` (200 sessions) | Total |
|---|---|---|---|
| B0 (`500fe7b`, unmodified) | 1.7647s | 29.2928s | 31.0575s |
| B2 (implemented, this pass) | 1.5274s | 54.7356s | 56.2630s |

```
Absolute increase (evaluate() only): +25.4428s
Relative multiplier:                 1.8686x   (B2 takes ~87% longer than B0)
Per-session average, B0:             0.1465s
Per-session average, B2:             0.2737s
```

**Note on interpretation, not optimization**: B2's average MTTC (5.91) is lower than
B0's (6.345), meaning B2 sessions terminate in fewer turns on average — so the 1.87x
runtime increase occurred *despite* B2 executing somewhat fewer total `respond()` calls
across the 200-session run than B0 would have at the same termination rate. The
per-call cost increase is therefore understated, not overstated, by the raw 1.87x
total-time ratio. This is attributable to the `active_terms` loop issuing one additional
small FTS `MATCH` query per active term per turn (in addition to the original single
query) — a direct, expected consequence of the frozen mechanism's design, not a
regression introduced during implementation. Per the directive, **no optimization was
attempted in this pass** — this is a measurement only.

```
PERFORMANCE INVESTIGATION REQUIRED: flagging per directive §10/§18 — a ~1.87x runtime
multiplier on a per-turn ranking cost is a material change, and worth a dedicated look
at whether it fits competition timeout/latency constraints (docs/submission_rules.md
notes the organizer may run submissions "under CPU, memory, timeout, and network
restrictions", but does not state a specific numeric limit anywhere in this repo's
tracked files) before this candidate is considered for commit. Not investigated further
here, per explicit instruction not to optimize in this pass.
```

---

## 8. Git status

```
 M starter/agent.py
?? tests/test_fix01b2_term_coverage_ranking.py
?? markdowns/fix01b2_term_coverage_implementation_handover.md
(plus the pre-existing untracked markdowns/ files from prior FIX-01/FIX-01B0/FIX-01B1/
 FIX-01B2 simulation work, unrelated to this implementation pass)
```

```bash
shasum -a 256 starter/agent.py
  # e3f324caf8e6c940d44293beffd6a71df489f56564639c5af800d70d2975b9b5
git rev-parse HEAD
  # 500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647   (unchanged)
```

---

## 9. Confirmation

```
NO COMMIT.   -- nothing staged or committed; HEAD unchanged at 500fe7b.
NO PUSH.     -- no git push was run.
NO TUNING.   -- the real implementation reproduced the frozen simulation reference on
                the first run, exactly, at both the aggregate and full session level;
                there was nothing to tune toward, and no parameter exists in the
                mechanism to tune.
```

`starter/agent.py` is left modified in the working tree only, per the directive's
governance (`IMPLEMENT → TEST → BENCHMARK → SHOW ACTUAL RESULTS → REVIEW → USER APPROVAL
→ ONLY THEN COMMIT`).

---

## Summary for the next decision

The implementation matches the frozen simulation exactly — same aggregate metrics
(HR@10 0.730→0.805, MRR 0.465458→0.499431, TechnicalScore 0.597737→0.654129), same 15
new hits with identical turns and ranks, same 6 rank regressions with identical
before/after values, deterministic across two independent runs. The one new fact this
pass adds beyond the simulation is runtime: **B2 is ~1.87x slower than B0** on the
200-session public evaluator (29.29s → 54.74s), driven by the additional per-active-term
FTS query the frozen mechanism requires. This is reported as a flag for the next review
step, not resolved or optimized here, per explicit instruction. Stopping for independent
review before any commit decision.
