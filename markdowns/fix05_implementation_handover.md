# FIX-05 — EXACT-PHRASE TIE-BREAK IMPLEMENTATION REPORT

Written 2026-08-31. Executes `FIX-05 — FINAL IMPLEMENTATION AUTHORIZATION.md`
exactly, against the verified `fix05p0_exact_phrase_tiebreak_simulation.md`.
**No stage, no commit, no push**, per §13/§16 of the authorization — this
report is for final-commit review only.

```text
IMPLEMENTATION: DONE
COMMIT:         NOT DONE
PUSH:           NOT DONE
```

---

## 1. HEAD / git state

```text
HEAD (unchanged throughout this pass): cd03f1974dc340869f11069d2af229112f8370b2
```

```bash
git status --short
```
```
 M starter/agent.py
?? markdowns/MASTER_HANDOVER_ROUND3.md
?? markdowns/fix04a_commit_and_merge_reconciliation.md
?? markdowns/fix04a_implementation_handover.md
?? markdowns/fix05p0_exact_phrase_tiebreak_simulation.md
?? tests/test_fix05_phrase_tiebreak.py
```

The four untracked markdown files predate this pass or are its own
research artifacts. Nothing has been staged.

---

## 2. `starter/agent.py` SHA before / after

```text
before: fc85aa59b5865458da45c9c51d6bb206b385fb44105c2a0d6c5dbf344dabed23  (== accepted cd03f19)
after:  ab99c72e53ff2e563505e09ca7dfd7862b9a654d6d366faf459a12964f71ca63
```

---

## 3. Production diff — the exact frozen mechanism, nothing else

Two additions: a new method (`_matchable_phrases`) and the new tertiary
sort key wired into the existing ranking block. Full diff:

```diff
@@ -336,6 +336,19 @@ class Agent:
                 matchable.append(terms)
         return matchable
 
+    def _matchable_phrases(self, state: SessionState) -> list[str]:
+        # FIX-05: active slot values with >=2 usable tokens, as their
+        # COMPLETE normalized token sequence (order preserved, NOT deduped
+        # -- unlike _active_terms()/_matchable_slots(), which do set-based
+        # coverage; a contiguous-phrase check needs the real word order).
+        # Same tokenizer as the rest of the file.
+        phrases: list[str] = []
+        for value in state.active_slots.values():
+            terms = _terms(value)
+            if len(terms) >= 2:
+                phrases.append(" ".join(terms))
+        return phrases
+
     def _next_ask_attribute(self, state: SessionState) -> str | None:
         for attr in ASK_ORDER:
             if attr in state.active_slots:
@@ -417,8 +430,50 @@ class Agent:
                     )
                     return satisfied / len(matchable_slots)
 
+                # FIX-05: exact active multi-token slot phrase coverage --
+                # tertiary tie-break, used only to separate candidates
+                # already equal on BOTH term coverage and slot coverage
+                # (both remain untouched as the primary/secondary keys --
+                # this can never promote a candidate with lower coverage on
+                # either). One additional batched (non-FTS) row fetch --
+                # not per-phrase, not per-candidate -- reads the same
+                # title/features/details/description text already indexed
+                # for FTS, via the identical _text() flattening already
+                # baked into those columns at index time. A phrase is
+                # "satisfied" for a candidate if its complete normalized
+                # token sequence occurs contiguously in that combined text;
+                # score is satisfied/matchable multi-token phrases, no
+                # weights, no threshold. With zero matchable phrases this is
+                # 0.0 for every candidate -- a no-op that falls through to
+                # the unchanged baseline-BM25-order final tiebreak,
+                # identical to FIX-04A.
+                matchable_phrases = self._matchable_phrases(state)
+
+                candidate_field_text: dict[str, str] = {}
+                if matchable_phrases:
+                    field_rows = self.connection.execute(
+                        f"SELECT parent_asin, title, features, details, description "
+                        f"FROM products WHERE parent_asin IN ({placeholders})",
+                        candidate_asins,
+                    ).fetchall()
+                    candidate_field_text = {
+                        str(row[0]): " ".join(
+                            " ".join(_terms(field_value)) for field_value in row[1:]
+                        )
+                        for row in field_rows
+                    }
+
+                def _phrase_coverage(asin: str) -> float:
+                    if not matchable_phrases:
+                        return 0.0
+                    text = candidate_field_text.get(asin, "")
+                    satisfied = sum(1 for phrase in matchable_phrases if phrase in text)
+                    return satisfied / len(matchable_phrases)
+
                 candidate_asins.sort(
-                    key=lambda asin: (-_coverage(asin), -_slot_coverage(asin), baseline_index[asin])
+                    key=lambda asin: (
+                        -_coverage(asin), -_slot_coverage(asin), -_phrase_coverage(asin), baseline_index[asin]
+                    )
                 )
```

Note on §6 of the authorization (the harness lesson): `candidate_field_text`
is built from a plain `SELECT ... WHERE parent_asin IN (...)` over the
production FTS table's own columns — not via
`evaluator.local_evaluator.normalize_recommendations()` at all. That
function (and its hardcoded `TOP_K` cap) is test/evaluator-only code and
was never reachable from production; the harness bug documented in
FIX-05P0 §0 was confined to the *simulation* script, not `starter/agent.py`.
Confirmed by inspection: `starter/agent.py` has no import of
`evaluator.local_evaluator` at all.

No IDF, rarity weighting, phrase-length weighting, field weighting, fuzzy
matching, synonyms, stemming, embeddings, BM25 changes, candidate-depth
changes, scenario routing, session-specific logic, ASIN-specific rules, or
thresholds were added — verified by inspection of the full diff above,
which is its entire content.

---

## 4. Targeted tests — `tests/test_fix05_phrase_tiebreak.py` (10 tests, A–J)

All 10 required cases from the authorization's §7, tested black-box via
`respond()` output (the phrase logic is a nested closure inside `respond()`,
not a standalone method, so this matches the project's existing testing
style for prior tie-break tiers).

| Test | Covers |
|---|---|
| `test_a_phrase_breaks_double_coverage_tie` | Case A: contiguous-phrase candidate ranks first among term/slot-tied candidates |
| `test_b_term_coverage_dominates_phrase` | Case B: lower term coverage never outranks higher, even with the phrase |
| `test_c_slot_coverage_dominates_phrase` | Case C: lower slot coverage never outranks higher, when term coverage ties |
| `test_d_equal_phrase_preserves_prior_order` | Case D: phrase-tied candidates keep the order the FIX-04A reference agent (no phrase key) would produce |
| `test_e_boilerplate_phrase_shared_by_all_is_a_noop` | Case E: 3-way boilerplate tie matches the FIX-04A reference agent's order exactly |
| `test_f_no_multi_token_slot_matches_fix04a_reference` | Case F: single-token-only active slots reduce exactly to FIX-04A |
| `test_g_contiguous_requires_exact_order` | Case G: same tokens in the WRONG order get no phrase credit |
| `test_h_field_scope_excludes_categories_and_store` | Case H: title/features/details/description recognized; categories (indexed for term matching) is not — parameterized across all 4 allowed fields |
| `test_i_recommendations_never_exceed_top_k` | Case I: `top_k` contract holds on the phrase path, `top_k` ∈ {1,2,5,10} |
| `test_j_fix04a_override_merge_behavior_intact` | Case J: the FIX-04A `state.slots` override-merge is untouched — reproduces its exact public-style example |

**Methodology correction found while writing D/E**: an initial version of
both tests compared against a "no active terms" baseline call to establish
"pure BM25 order," and failed. Traced directly: `baseline_index` is
specific to the query *expression actually used* (which depends on the
populated active slots), not a universal ordering independent of them — the
no-active-terms baseline call builds a different, shorter query expression
entirely. Fixed by comparing against the accepted FIX-04A reference agent
(`cd03f19`, no phrase key at all) run on the *identical* messages instead —
an apples-to-apples comparison. Both tests pass after the fix; disclosed
here rather than silently corrected, matching this project's own §0
precedent from the FIX-05P0 simulation pass.

---

## 5. Full test suite

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```
```text
Ran 54 tests in 0.062s
OK
```

```text
number of tests: 54   (44 pre-existing + 10 new FIX-05 tests)
failures:         0
errors:           0
```

No existing test was deleted or weakened.

---

## 6. Real 200-session evaluator

```bash
python3 -m evaluator.local_evaluator
```
```json
{
  "sample_count": 200,
  "hit_rate_at_10": 0.88,
  "mrr": 0.567583,
  "mttc": 5.495,
  "efficiency": 0.5505,
  "recommended_technical_score": 0.720375,
  "scenario_metrics": {
    "boundary":        {"sample_count": 10, "hit_rate_at_10": 0.8,      "mrr": 0.502778, "mttc": 6.6},
    "browsing":        {"sample_count": 80, "hit_rate_at_10": 0.9,      "mrr": 0.618204, "mttc": 5.3},
    "buying":          {"sample_count": 80, "hit_rate_at_10": 0.8875,   "mrr": 0.495288, "mttc": 5.5},
    "intent_override": {"sample_count": 30, "hit_rate_at_10": 0.833333, "mrr": 0.646984, "mttc": 5.633333}
  }
}
```

**Exact reproduction of §9's required numbers, including every scenario
metric to the last decimal.** No discrepancy to investigate.

---

## 7. Full 200-session equivalence (0/200 mismatches)

Compared production's own `results.json` sessions (hit / best_rank /
first_hit_turn) against the verified FIX-05P0 simulation's saved sessions,
sample-ID for sample-ID:

```text
total sessions:                       200
simulation-vs-production mismatches:    0
```

Session deltas against the `cd03f19` baseline, computed independently from
production's own results (not copied from the simulation report):

```text
new hits:              10   public_0011, public_0012, public_0019,
                             public_0054, public_0055, public_0057,
                             public_0115, public_0151, public_0159,
                             public_0170
new misses:              0

rank improvements:      35
rank regressions:        4   public_0103, public_0117, public_0130, public_0189

turn improvements:       2   public_0117, public_0153
turn regressions:        0
```

**Exact match to §2's expected new-hit and rank-regression sample-ID
lists**, and to §10's expected counts (10/0/35/4/2/0). No unexplained
additional movement.

---

## 8. Explicit `public_0117` check (§11)

```bash
old: rank 1 / turn 3
new: rank 6 / turn 1
```

Exact match to the authorization's required values. No special-casing was
added for this or any other session — this is the mechanism's natural,
unmodified output. Accepted per §11 as a legitimate MTTC-for-MRR trade-off
(earlier genuine hit, evaluator stops at first hit) — see
`fix05p0_exact_phrase_tiebreak_simulation.md` §6 for the full turn-by-turn
trace of why this happens.

---

## 9. Runtime — a real, confirmed slowdown, reported plainly (§12)

```text
cd03f19 baseline:    52.63s  (full 200-session evaluate())
FIX-05 implemented:  84.68s  (same, one run)

confirmation run (full `python3 -m evaluator.local_evaluator` subprocess):
                     86.80s
```

**This is an obvious slowdown (+~60%, +32–34s), not noise** — prior runtime
checks in this project (FIX-04A's own matched-methodology comparison) found
run-to-run variance in the ~52–67s band for agent versions *without* this
change; both FIX-05 measurements here fall well outside that band,
confirmed with a second independent run rather than accepted on one sample.

**Likely cause (stated as a hypothesis, not measured with a profiler — per
§12's own instruction not to over-invest in profiling this pass):** the new
`SELECT parent_asin, title, features, details, description FROM products
WHERE parent_asin IN (...)` query runs against an FTS5 virtual table where
`parent_asin` is declared `UNINDEXED`. Unlike the existing `MATCH`-based
queries (which use FTS5's own index), a plain `WHERE column IN (...)`
predicate on an `UNINDEXED` FTS5 column has no secondary index to use and
may fall back to a full table scan per call — and this query runs once per
turn whenever any multi-token active slot exists (i.e., on most turns past
the first disclosure in most scenarios). This is a plausible, structural
explanation, not a confirmed root cause.

**This was not optimized in this pass** — the authorization's own
"correctness and final packaging have priority" instruction, combined with
"do NOT spend time on repeated performance profiling," was read as
permission to surface this rather than chase it. It is reported here
prominently, ahead of the commit classification below, so the decision to
accept, defer, or require a fix is made by the reviewer, not assumed.

---

## 10. Git status (final)

```bash
git status --short
```
```
 M starter/agent.py
?? markdowns/MASTER_HANDOVER_ROUND3.md
?? markdowns/fix04a_commit_and_merge_reconciliation.md
?? markdowns/fix04a_implementation_handover.md
?? markdowns/fix05p0_exact_phrase_tiebreak_simulation.md
?? tests/test_fix05_phrase_tiebreak.py
```

No `git add`, no `git commit`, no `git push` performed at any point in this
pass, per §13/§16.

---

## 11. Classification

```text
READY FOR FINAL COMMIT
```

Every explicit correctness gate in the authorization is satisfied exactly:
full test suite green (54/54), evaluator numbers match §9 to the full
reported precision including every scenario metric, session-level diff
matches §10 with 0/200 mismatches and the exact expected sample-ID lists,
and the explicit `public_0117` check matches §11 precisely. Runtime is
**not** listed as a blocking gate in the authorization, but the confirmed
~60% slowdown (§9 above) is real and should be weighed by whoever authorizes
the commit — this report does not resolve that question on its own.

**STOP. No stage. No commit. No push**, per authorization §13/§16. This
report is for independent final-commit review only.
