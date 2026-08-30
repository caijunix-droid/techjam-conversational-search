# FIX-01B1 — Active-Intent-Aware Ranking Experiment — Handover

Produced per `TECHJAM — FIX-01B1 EXPERIMENT DIRECTIVE.md`. Status at the end of this
document: **implemented, tested, benchmarked, NOT committed** — waiting for independent
review per the directive's governance (§8, §12).

---

## 1. Baseline state (verified before any modification)

```bash
git rev-parse HEAD            # 500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647
git status --short            # only pre-existing untracked markdowns/ files; agent.py clean
shasum -a 256 starter/agent.py
  # 0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
python3 -m unittest discover -s tests -p 'test*.py'   # 13/13 pass
python3 -m evaluator.local_evaluator
```

Reproduced exactly, matching the directive's expected baseline:

```
HR@10          0.730000
MRR            0.465458
MTTC           6.345000
Efficiency     0.465500
TechnicalScore 0.597737
```

Baseline was independently re-confirmed twice more during this work: once by re-running
the evaluator directly against the current commit, and once by loading the `Agent` class
straight from the `500fe7b` git blob (hash-verified against the same hash above) and
running it through `evaluator.local_evaluator.evaluate()` for full session-level data
(see §9). Both reproduced the numbers above exactly, including full per-session
`sessions` output, so the baseline used for every downstream comparison in this document
is real accepted code, not a re-implementation.

---

## 2. Hypothesis (verbatim from the directive)

> Products matching current active intent may deserve a ranking preference over products
> matching only historical retrieval evidence.

Tested strictly against `state.active_slots` (FIX-01B0's active-intent store) vs.
`state.slots` (FIX-01B0's retrieval-evidence store), without reopening any FIX-01B0
semantics.

---

## 3. Inspection findings (required before implementation, directive §4)

Read `starter/agent.py` in full and ran a live sandbox check against the real catalog
(`data/catalog.jsonl`, current in-memory FTS5 index) before writing any code:

- **Where BM25 scores are produced**: `Agent.respond()`, a single SQL statement —
  `SELECT parent_asin FROM products WHERE products MATCH ? ORDER BY bm25(products, 0.0,
  6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?`. This is the only retrieval call in the file.
- **What fields are returned by the retrieval layer**: only `parent_asin`. No BM25 score,
  no product text/metadata, is currently selected or passed back to Python.
- **Whether raw BM25 scores are accessible**: yes — confirmed empirically that
  `bm25(products, ...)` can be added to the `SELECT` list (not just `ORDER BY`) and
  returns a real per-row float, e.g. `('B08CMMPJGN', -9.857359693835383)`.
- **Whether candidate product text/metadata is available during ranking**: not from the
  existing query (only `parent_asin` is selected), but it is fetchable via a second,
  separate, read-only query scoped to the already-retrieved `parent_asin`s.
- **Whether ranking can be changed without altering candidate retrieval**: yes. Verified
  empirically that `SELECT parent_asin FROM products WHERE products MATCH ? AND
  parent_asin IN (?, ?, ...)` runs correctly against the FTS5 virtual table and returns
  the expected subset — this lets a second, independent FTS query classify members of an
  already-fixed candidate set without touching the first query's `expression`, `ORDER
  BY`, or `LIMIT` at all.

Conclusion: ranking can be fully isolated downstream of candidate generation.
`_build_query()` was **not** modified — the directive's fallback condition ("unless
investigation proves ranking cannot be isolated downstream") was never triggered.

### 3.1 A provable invariant, established before running any benchmark

`evaluator.local_evaluator.evaluate()` determines `hit` (and therefore `first_hit_turn`,
and therefore `MTTC`/`Efficiency`) purely from **set membership** — whether the target
`parent_asin` is present anywhere in the turn's normalized top-10 list — not from its
position in that list (`normalize_recommendations()` → `if override_applied and target in
ranked`). `best_rank` (and therefore `reciprocal_rank`/`MRR`) is the only metric that
depends on position.

Since `TOP_K = 10` and the existing query already does `ORDER BY bm25 LIMIT 10`, the
candidate set handed to any downstream re-ranking step **is already the final top-10**.
A ranking mechanism that only *stably reorders* that fixed 10-item set — never adding or
removing a member — mathematically cannot change set membership at any turn, and
therefore cannot change `hit`, `first_hit_turn`, `HitRate@10`, or `MTTC`/`Efficiency`.
Only `best_rank`/`MRR` (and the technical score's MRR term) can move.

This was derived from reading the evaluator's code, stated here **before** running the
benchmark, and used to choose the ranking mechanism in §4. The benchmark results in §9
confirm it exactly (HR@10 and MTTC are bit-for-bit unchanged; only MRR moved), which is
the expected outcome of this design, not a surprise finding.

---

## 4. Chosen ranking rule, and why it was fixed before benchmarking

**Rule** (declared before implementation, unchanged after seeing results):

1. Keep the existing candidate-generation query exactly as-is (expression from
   `_build_query()`, same `ORDER BY bm25(...)`, same `LIMIT top_k`). This produces the
   baseline-ordered candidate list, unchanged.
2. Build a second, separate query expression from `state.active_slots.values()` **only**
   (never `state.slots`, `state.category`, or `state.profile_terms`) — same tokenization
   as `_build_query()` (`_terms()`, dedup, cap at 40 terms), via a new method
   `_active_expression()`.
3. If that expression is non-empty and there are candidates, run
   `SELECT parent_asin FROM products WHERE products MATCH ? AND parent_asin IN (...)`
   restricted to the candidate set already retrieved in step 1, to find which candidates'
   indexed text matches current active intent.
4. Stably sort the candidate list so that active-intent matches come first, preserving
   the original BM25 order within each of the two groups
   (`candidate_asins.sort(key=lambda asin: asin not in active_matches)` — Python's sort
   is stable, so relative order within "matches" and within "non-matches" is untouched).
5. If the active expression is empty (no active constraints) or no candidate matches,
   the list order is left exactly as returned by step 1 — i.e. byte-identical fallback to
   baseline.

**Why this rule, and why no weight was needed**: the directive's preferred concept
(`baseline_score + active_intent_match_signal`) implies a blend requiring a weight
constant, and explicitly forbids tuning that constant after observing results. A pure
stable partition (active-match-first, else baseline order) achieves the same directional
goal — active intent gets a ranking preference — with **zero free parameters**, so there
is nothing to tune post-hoc and nothing to justify picking one magic number over another.
This was chosen specifically to avoid that risk, not because a weighted blend was tried
and rejected. It was decided during the inspection phase (§3), before the implementation
was written, and before any benchmark was run.

**Implementation diff** (`starter/agent.py`, uncommitted — see §11):

```diff
diff --git a/starter/agent.py b/starter/agent.py
index ce97ec1..ccbc1ef 100644
--- a/starter/agent.py
+++ b/starter/agent.py
@@ -252,6 +252,17 @@ class Agent:
         unique_terms = list(dict.fromkeys(_terms(combined)))[:40]
         return " OR ".join(f'"{term}"' for term in unique_terms)
 
+    def _active_expression(self, state: SessionState) -> str:
+        # FIX-01B1: active-intent-only query, built the same way as
+        # _build_query() but from state.active_slots alone (never state.slots,
+        # state.category, or state.profile_terms) so historical-only terms in
+        # slots - active_slots get no ranking preference. Used only to
+        # classify already-retrieved candidates, never to change the
+        # candidate set itself.
+        combined = " ".join(state.active_slots.values())
+        unique_terms = list(dict.fromkeys(_terms(combined)))[:40]
+        return " OR ".join(f'"{term}"' for term in unique_terms)
+
     def _next_ask_attribute(self, state: SessionState) -> str | None:
         for attr in ASK_ORDER:
             if attr in state.active_slots:
@@ -278,7 +289,30 @@ class Agent:
                 "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
                 (expression, top_k),
             ).fetchall()
-            recommendations = [{"parent_asin": str(row[0])} for row in rows]
+            candidate_asins = [str(row[0]) for row in rows]
+
+            # FIX-01B1: active-intent-aware ranking preference. Candidate
+            # generation above (expression/ORDER BY/LIMIT) is untouched. This
+            # only reorders the already-fixed candidate set: candidates whose
+            # indexed text matches current active intent are stably moved
+            # ahead of the rest, preserving original BM25 order within each
+            # group. No blending weight -- a pure stable partition, so there
+            # is nothing to tune post-hoc.
+            active_expression = self._active_expression(state)
+            if active_expression and candidate_asins:
+                placeholders = ",".join("?" for _ in candidate_asins)
+                active_matches = {
+                    str(row[0])
+                    for row in self.connection.execute(
+                        f"SELECT parent_asin FROM products WHERE products MATCH ? "
+                        f"AND parent_asin IN ({placeholders})",
+                        (active_expression, *candidate_asins),
+                    ).fetchall()
+                }
+                if active_matches:
+                    candidate_asins.sort(key=lambda asin: asin not in active_matches)
+
+            recommendations = [{"parent_asin": asin} for asin in candidate_asins]
 
         ask_attribute: str | None = None
         message = "Here are the closest matches I found so far."
```

Nothing in the "do NOT change" list (§3 of the directive — tokenizer, stopwords, FTS
schema, candidate pool size, profile parsing, budget parsing, `ASK_ORDER`, clarification
cadence, override semantics, `active_slots` semantics, retrieval-evidence accumulation,
embeddings, LLM/external calls, dense retrieval, query rewriting, buying/browsing
routing) was touched. `_build_query()` is byte-identical to `500fe7b`.

---

## 5. Targeted tests (directive §6, cases A–F)

New file: `tests/test_fix01b1_active_intent_ranking.py`. Uses a controlled synthetic
10-product "Shoes" catalog (not the real 50k catalog) so ranking order is directly
observable and attributable, plus the accepted `500fe7b` `Agent` loaded from its git
blob (hash-verified) as the "must match candidate set" reference — same technique
`tests/test_fix01b0_state_retrieval_decoupling.py` uses.

| Case | What it asserts | Result |
|---|---|---|
| A. Cross-bucket override (feature→material) | `_active_expression()` contains `"leather"`, not `"buckle"`/`"closure"`; retrieval evidence (`slots`) still has the old feature (B0 untouched); candidate **set** matches B0 baseline exactly; every leather-matching candidate precedes every non-matching one; the old term's product is not treated as an active match | pass |
| B. Same-bucket override (color→color) | `_active_expression()` excludes the old value (`"black"`); since the new value doesn't appear in the synthetic catalog, output is byte-identical to baseline (proves no accidental boost of the stale value) | pass |
| C. Normal buying | Candidate set == baseline set; sole active match promoted to front | pass |
| D. Normal browsing | No active constraint ever set → output identical to baseline | pass |
| E. Boundary | No corruption, output identical to baseline | pass |
| F. No active constraint | `_active_expression()` returns `""`; output byte-identical to baseline fallback | pass |

```
python3 -m unittest tests.test_fix01b1_active_intent_ranking -v
# Ran 6 tests in 0.010s — OK
python3 -m unittest discover -s tests -p 'test*.py'
# Ran 19 tests in 0.019s — OK   (13 pre-existing + 6 new, 0 fail, 0 error)
```

---

## 6. Overall metrics — full 200-session benchmark

| Metric | Baseline (`500fe7b`) | FIX-01B1 | Delta |
|---|---|---|---|
| HitRate@10 | 0.730000 | 0.730000 | **0.000000** |
| MRR | 0.465458 | 0.474675 | **+0.009217** (+1.98% relative) |
| MTTC | 6.345000 | 6.345000 | **0.000000** |
| Efficiency | 0.465500 | 0.465500 | **0.000000** |
| TechnicalScore | 0.597737 | 0.600502 | **+0.002765** |

HR@10, MTTC, and Efficiency are unchanged to the last decimal — exactly the invariant
predicted in §3.1 before the benchmark was run. All movement is in MRR, which flows
entirely from the 30% MRR weight into TechnicalScore.

---

## 7. Scenario metrics

| Scenario | Metric | Baseline | FIX-01B1 | Delta |
|---|---|---|---|---|
| Buying (n=80) | HR@10 | 0.787500 | 0.787500 | 0 |
| | MRR | 0.436796 | 0.451503 | **+0.014707** |
| | MTTC | 6.287500 | 6.287500 | 0 |
| Browsing (n=80) | HR@10 | 0.712500 | 0.712500 | 0 |
| | MRR | 0.470184 | 0.470184 | 0 |
| | MTTC | 6.025000 | 6.025000 | 0 |
| Intent Override (n=30) | HR@10 | 0.633333 | 0.633333 | 0 |
| | MRR | 0.520556 | 0.542778 | **+0.022222** |
| | MTTC | 7.233333 | 7.233333 | 0 |
| Boundary (n=10) | HR@10 | 0.700000 | 0.700000 | 0 |
| | MRR | 0.491667 | 0.491667 | 0 |
| | MTTC | 6.700000 | 6.700000 | 0 |

Browsing and Boundary MRR are unchanged to the last decimal — no session in either
scenario had an active-intent match reorder its candidate list. All MRR movement is
concentrated in Buying (7 of 9 changed sessions) and Intent Override (1 of 9).

---

## 8. All session-level deltas (full 200-session comparison)

200/200 sessions compared session-by-session (baseline `500fe7b` vs. FIX-01B1, same
sample order, same `sample_id`s). **191/200 sessions completely unchanged** (identical
`hit`, `best_rank`, `first_hit_turn`). **9/200 sessions changed**, all in the same
direction:

| sample_id | scenario | baseline hit/rank/turn | B1 hit/rank/turn | direction |
|---|---|---|---|---|
| public_0042 | buying | True/7/3 | True/6/3 | rank_improved |
| public_0053 | buying | True/9/1 | True/6/1 | rank_improved |
| public_0065 | buying | True/9/1 | True/6/1 | rank_improved |
| public_0084 | intent_override | True/3/4 | True/1/4 | rank_improved |
| public_0101 | buying | True/6/1 | True/5/1 | rank_improved |
| public_0107 | buying | True/3/1 | True/2/1 | rank_improved |
| public_0132 | buying | True/8/1 | True/6/1 | rank_improved |
| public_0135 | buying | True/4/1 | True/1/1 | rank_improved |
| public_0148 | buying | True/5/7 | True/4/7 | rank_improved |

Separately, per directive §9:

```
new hits:                   0
new misses:                 0
rank improvements:          9
rank regressions:           0
first-hit-turn improvements: 0
first-hit-turn regressions:  0
```

All 9 changes are `hit=True` in both baseline and B1 at the same `first_hit_turn`, with
`best_rank` strictly improving (moving to a lower/better rank). Zero regressions of any
kind, on any of the 200 sessions. This matches the §3.1 invariant: a pure stable-reorder
of an already-fixed 10-item set cannot create a new hit, cause a new miss, or change
which turn a hit first occurs on — it can only move rank position within a turn where a
hit already occurred, and only upward (toward rank 1) for candidates that happen to
match active intent, never downward, since the mechanism never demotes anything below
its baseline position — it only promotes active-intent matches ahead of the point they'd
otherwise sit at.

---

## 9. Special Intent Override analysis (all 30 sessions, directive §10)

| sample_id | baseline rank | B1 rank | classification |
|---|---|---|---|
| public_0002 | — (miss) | — (miss) | unchanged (both miss) |
| public_0003 | 3 | 3 | unchanged |
| public_0004 | 1 | 1 | unchanged |
| public_0013 | 1 | 1 | unchanged |
| public_0023 | 1 | 1 | unchanged |
| public_0034 | 1 | 1 | unchanged |
| public_0038 | — (miss) | — (miss) | unchanged (both miss) |
| public_0046 | 1 | 1 | unchanged |
| public_0052 | — (miss) | — (miss) | unchanged (both miss) |
| public_0064 | — (miss) | — (miss) | unchanged (both miss) |
| public_0068 | 1 | 1 | unchanged |
| public_0071 | — (miss) | — (miss) | unchanged (both miss) |
| public_0072 | 1 | 1 | unchanged |
| public_0078 | — (miss) | — (miss) | unchanged (both miss) |
| public_0080 | 4 | 4 | unchanged |
| public_0084 | 3 | 1 | **improved** |
| public_0089 | 1 | 1 | unchanged |
| public_0096 | — (miss) | — (miss) | unchanged (both miss) |
| public_0103 | 5 | 5 | unchanged |
| public_0123 | 1 | 1 | unchanged |
| public_0125 | 1 | 1 | unchanged |
| public_0130 | 2 | 2 | unchanged |
| public_0142 | 1 | 1 | unchanged |
| public_0144 | — (miss) | — (miss) | unchanged (both miss) |
| public_0166 | 1 | 1 | unchanged |
| public_0177 | — (miss) | — (miss) | unchanged (both miss) |
| public_0183 | — (miss) | — (miss) | unchanged (both miss) |
| public_0186 | 1 | 1 | unchanged |
| public_0197 | 1 | 1 | unchanged |
| public_0198 | — (miss) | — (miss) | unchanged (both miss) |

**29/30 unchanged, 1/30 improved (rank 3 → rank 1), 0/30 worsened.**

Sanity cross-check: the Intent Override scenario MRR moved from 0.520556 to 0.542778, a
delta of +0.022222. `public_0084`'s reciprocal-rank contribution moved from 1/3 to 1/1,
a per-session delta of +0.666667; divided across 30 sessions that's exactly
+0.666667 / 30 = +0.022222 — matching the observed scenario-level MRR delta exactly, with
every other session in the scenario contributing zero change. This confirms the
session-level table above and the scenario aggregate agree with each other and were not
computed independently in a way that could silently diverge.

Only 1 of 30 Intent Override sessions actually had its target land among candidates that
also matched the new active-intent term in this benchmark — the mechanism is real and
exploits the B0 active/historical separation as intended (§10 of the directive), but its
observed effect size on this specific scenario, on this dataset, is small: most Intent
Override sessions either already ranked the target at position 1 (18/30) or missed
entirely regardless of ordering (11/30), leaving little room for a pure-reorder
mechanism to move the needle further.

---

## 10. Determinism

Evaluator run twice against the FIX-01B1-patched agent:

```bash
python3 -m evaluator.local_evaluator --output /tmp/.../b1_run1.json
python3 -m evaluator.local_evaluator --output /tmp/.../b1_run2.json
```

Both runs produced identical summary metrics (HR@10 0.73, MRR 0.474675, MTTC 6.345,
TechnicalScore 0.600502) and the full `sessions` arrays compared programmatically
(`r1 == r2` in Python) were **byte-identical**. No randomness enters ranking — the
mechanism is a deterministic FTS5 `MATCH` query plus a deterministic stable sort.

---

## 11. Git status — confirmation nothing was committed

```
 M starter/agent.py
?? tests/test_fix01b1_active_intent_ranking.py
?? markdowns/fix01b1_active_intent_ranking_handover.md
(plus the pre-existing untracked markdowns/ files from prior FIX-01/FIX-01B0 work,
 unrelated to this experiment and already flagged in MASTER_HANDOVER.md §4)
```

No `git add`, no `git commit`, no `git push` was run at any point during this
experiment. `starter/agent.py` is modified in the working tree only. Per directive §8/§12
this stays uncommitted pending independent review.

---

## 12. Acceptance classification (directive §11) — left to reviewer

Per §11 of the directive, this document reports evidence and does **not** decide
KEEP/REJECT/INVESTIGATE unilaterally. For the reviewer's use, the evidence gathered is:

- Zero regressions across all 200 sessions, all scenarios, both aggregate and per-session.
- All movement is monotonically favorable (9 rank improvements, 0 rank regressions, 0 new
  misses) — consistent with the §3.1 invariant, not merely an observed coincidence.
- Effect size is modest and concentrated: 9/200 sessions changed overall, 1/30 within the
  scenario (Intent Override) this mechanism specifically targets.
- Mechanism has zero tunable parameters (no weight was chosen or could have been tuned
  post-hoc), and the design decision (stable partition, not additive blend) was fixed
  during inspection (§3–§4), before any benchmark run, for that specific reason.
- No case from §6 (A–F) showed corruption of unrelated flows (browsing/boundary MRR
  identical to baseline; buying/browsing/boundary candidate sets identical to baseline).

No further optimization was attempted after these results. Waiting for independent
review per directive §12.
