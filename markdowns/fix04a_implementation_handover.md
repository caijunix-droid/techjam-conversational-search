# FIX-04A — IMPLEMENTATION REPORT

Written 2026-08-31. Executes `FIX-04A — IMPLEMENTATION AUTHORIZATION.md`
exactly. This pass performed implementation + verification only, per that
authorization's own governance section (§13/§16): **no stage, no commit, no
push.** Everything below is evidence for an independent commit-review
decision, not a done deal.

```text
IMPLEMENTATION: DONE
COMMIT:         NOT DONE
PUSH:           NOT DONE
```

---

## 1. HEAD / git state

```text
HEAD (unchanged throughout this pass): f5f4255a67f2884eeb798ffe0f20adfe71de1e5d
```

```bash
git status --short
```
```
 M starter/agent.py
 M tests/test_fix03a_override_correction.py
?? markdowns/MASTER_HANDOVER_ROUND3.md
?? tests/test_fix04a_slots_preservation.py
```

`markdowns/MASTER_HANDOVER_ROUND3.md` is pre-existing, unrelated to this
pass (already untracked before this work started). Nothing has been staged.

---

## 2. `starter/agent.py` SHA before / after

```text
before: c839811324f491049d397cad8b0b0c0a75d2466df272482037870a5ccddffb82
        (== accepted FIX-03A commit 1e2848e, verified identical before edit)
after:  2382dfb8f80697c7afe5918c9be5afd129ec3b7604ec474039f99230a277aed6
```

---

## 3. Production diff

The atomic mechanism change is exactly the diff specified in the
authorization's §3, applied at the one call site that overwrote retrieval
evidence unconditionally (`starter/agent.py`, override-message handler,
originally line 208):

```diff
@@ -203,9 +204,18 @@ class Agent:
                 state.override_source_value = None
             if new_value:
                 attr = classify(new_value)
-                # Retrieval evidence: unchanged baseline behaviour -- just
-                # overwrite this bucket, same as before the FIX-01 work.
-                state.slots[attr] = new_value
+                # FIX-04A: same rationale as the active_slots merge below --
+                # the override message only ever names ONE prior preference
+                # (the tracked source_attr). If the new value lands in a
+                # DIFFERENT retrieval-evidence bucket that already holds a
+                # value, that value was never named as superseded and must
+                # not be silently destroyed -- merge instead of overwrite.
+                # If the bucket is empty, or is the tracked source bucket
+                # itself, behavior is unchanged from prior production.
+                if attr in state.slots and attr != tracked_source_attr:
+                    state.slots[attr] = state.slots[attr] + "; " + new_value
+                else:
+                    state.slots[attr] = new_value
                 # FIX-03A: the override message ("ignore my earlier
                 # preference") only ever refers to ONE prior preference --
                 # the tracked source_attr/source_value handled above. If the
```

`tracked_source_attr` was already computed above this site (line 190,
`tracked_source_attr = state.override_source_attr`, pre-existing FIX-03A
code) — reused, not reintroduced. Nothing else in the diff is a behavior
change.

**Three pre-existing comments were also corrected** (no logic touched).
Each described the pre-FIX-04A scope boundary — "retrieval evidence never
uses this / is intentionally left out of this bookkeeping" — that this
exact authorized mechanism supersedes; left as-is they would misdescribe
production behavior to a future reader:

```diff
@@ -82,8 +82,8 @@ class SessionState:
     def __init__(self, profile_terms: str) -> None:
         self.category = ""
         # Retrieval evidence: lexical terms accumulated from the conversation.
-        # Feeds _build_query() and is intentionally left byte-equivalent to
-        # the accepted baseline's accumulation behaviour, override included.
+        # Feeds _build_query(). FIX-04A: on override, unrelated buckets are
+        # merged rather than overwritten (same rule as active_slots below).
         self.slots: dict[str, str] = {}
@@ -96,8 +96,9 @@ class SessionState:
         self.last_turn_asked: str | None = None
         # Provenance for the one active preference an Intent Override turn
         # may later supersede: which bucket it was filed under, and its
-        # exact value at the time it was recorded. Scoped to active_slots
-        # only -- retrieval evidence never uses this.
+        # exact value at the time it was recorded. The bucket (attr) is also
+        # consulted by the FIX-04A retrieval-evidence merge below; the value
+        # is only ever consulted for the active_slots deletion-safety check.
         self.override_source_attr: str | None = None
         self.override_source_value: str | None = None
@@ -177,9 +178,9 @@ class Agent:
                     state.slots[attr] = remainder
                     state.active_slots[attr] = remainder
                     # Remember this as the active preference a later override
-                    # may supersede. Retrieval evidence (`slots`) is
-                    # intentionally left out of this bookkeeping so it keeps
-                    # accumulating exactly like the accepted baseline.
+                    # may supersede. FIX-04A: the bucket name (attr) is also
+                    # read by the retrieval-evidence merge on override; the
+                    # value is only ever read for the active_slots check.
                     state.override_source_attr = attr
                     state.override_source_value = remainder
             return
```

No dedup, weights, BM25 changes, synonyms, IDF, phrase scoring, special
material handling, scenario routing, ASIN-specific logic, session-specific
logic, thresholds, or query/candidate-depth changes were added — verified by
inspection of the full diff above, which is its entire content.

---

## 4. Existing test consequence (flagged, not silently absorbed)

`tests/test_fix03a_override_correction.py`'s `test_e_retrieval_evidence_unaffected`
explicitly pinned the **pre-FIX-04A** scope boundary: "retrieval evidence
(`slots`) keeps its unconditional-overwrite behavior." That premise is
exactly what this authorized mechanism changes, so the assertion
`state.slots.get("material") == "cotton"` would now fail — correctly,
because the authorized new behavior for that bucket is the merged value.

This is **not** a weakened test: the assertion that pinned now-superseded
behavior was replaced with an assertion the merge doesn't over-apply (the
untouched `feature` bucket stays exactly `"Pull On closure"`), and the test
was renamed/commented to state plainly that FIX-03A's own test file scopes
to the FIX-03A commit, with FIX-04A's extension covered separately. Full
diff:

```diff
-    # E. The correction touches only active_slots; retrieval evidence
-    # (`slots`) keeps its unconditional-overwrite behavior, unchanged --
-    # the B0/B2 active_slots-vs-slots separation is not reopened.
-    def test_e_retrieval_evidence_unaffected(self) -> None:
+    # E. FIX-03A's own scope: this test file pins active_slots behavior at
+    # the FIX-03A commit only. FIX-04A (a later, separately authorized
+    # change -- see test_fix04a_slots_preservation.py) intentionally
+    # extends the same merge rule to retrieval evidence (`slots`), so this
+    # test no longer pins slots to unconditional-overwrite; it pins the
+    # feature bucket, which this scenario never touches on override, to
+    # confirm the merge is scoped to the actually-overridden bucket only.
+    def test_e_retrieval_evidence_untouched_buckets_unaffected(self) -> None:
         session_id = "case_e"
         messages = [
             "I'm looking for Shoes. Pull On closure",
@@ -150,9 +154,8 @@
         ]
         self._replay(self.patched, session_id, messages)
         state = self.patched._sessions[session_id]
-        # Retrieval evidence still just overwrites the bucket -- no merge --
-        # identical to prior production semantics for `slots`.
-        self.assertEqual(state.slots.get("material"), "cotton")
+        # The feature bucket (tracked source, never targeted by this
+        # override's classified attr) is untouched, exactly as before.
         self.assertEqual(state.slots.get("feature"), "Pull On closure")
```

No test was deleted. No existing test's coverage was reduced without a
replacement assertion at least as strict for what it still can validly
claim.

---

## 5. New tests — `tests/test_fix04a_slots_preservation.py` (8 tests, A–H)

Reference agent: the accepted FIX-03A commit (`1e2848e`), loaded via
`git show` and SHA-verified (`c8398113...`) before use — same pattern the
existing FIX-03A test file uses against FIX-02A2. All 8 required cases from
§6 of the authorization are covered:

| Test | Covers |
|---|---|
| `test_a_unrelated_retrieval_evidence_preserved` | Case A: unrelated `state.slots` bucket merged, not destroyed |
| `test_b_tracked_source_bucket_still_replaces` | Case B: same-bucket override stays a clean replace |
| `test_c_empty_destination_bucket_matches_fix03a` | Case C: empty bucket behaves identically to FIX-03A, including recommendation output |
| `test_d_active_slots_fix03a_semantics_intact` | `active_slots` dict byte-for-byte identical to the FIX-03A reference agent for the same scenario |
| `test_e_buying_browsing_boundary_unaffected` | Buying/Browsing/Boundary recommendations identical to FIX-03A reference |
| `test_f_merged_retrieval_evidence_reaches_build_query` | Merged value is actually present in `_build_query()`'s output, not dead state |
| `test_g_public_style_multi_value_material_preserved` | The exact "Cotton, Rayon" + override "cotton" → `"Cotton, Rayon; cotton"` example from the authorization's §5 |
| `test_h_recommendations_never_exceed_top_k` | `top_k` contract holds on the override-merge path across `top_k` ∈ {1,2,5,10} |

---

## 6. Full test suite

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```
```text
Ran 44 tests in 0.058s

OK
```

```text
number of tests: 44   (36 pre-existing + 8 new FIX-04A tests)
failures:         0
errors:           0
```

---

## 7. Real 200-session evaluator

```bash
python3 -m evaluator.local_evaluator
```
```json
{
  "sample_count": 200,
  "hit_rate_at_10": 0.83,
  "mrr": 0.512694,
  "mttc": 5.645,
  "efficiency": 0.5355,
  "recommended_technical_score": 0.675908,
  "scenario_metrics": {
    "boundary":        {"sample_count": 10, "hit_rate_at_10": 0.8,      "mrr": 0.501667, "mttc": 6.6},
    "browsing":        {"sample_count": 80, "hit_rate_at_10": 0.8,      "mrr": 0.509142, "mttc": 5.6},
    "buying":          {"sample_count": 80, "hit_rate_at_10": 0.8625,   "mrr": 0.469871, "mttc": 5.575},
    "intent_override": {"sample_count": 30, "hit_rate_at_10": 0.833333, "mrr": 0.64004,  "mttc": 5.633333}
  }
}
```

**Exact reproduction of §8's required numbers** (0.830000 / 0.512694 /
5.645000 / 0.535500 / 0.675908). Boundary/Browsing/Buying scenario metrics
are byte-identical to the accepted FIX-03A baseline's own numbers (re-run
fresh in this pass as a cross-check — see §9). No discrepancy to
investigate.

---

## 8. Full session-level equivalence (200/200)

The FIX-03A baseline was **re-run fresh in this pass** (not assumed from a
prior handover) by loading the accepted FIX-03A commit (`1e2848e`,
SHA-verified) through the identical `evaluate()` harness, to get a true
apples-to-apples per-session comparison:

```text
FIX-03A baseline (re-run fresh): HR@10 0.825000, MRR 0.510105,
MTTC 5.680000, TechnicalScore 0.671932 -- exact match to the accepted
baseline's own recorded numbers.
```

Diffing all 200 sessions (`hit`, `best_rank`, `first_hit_turn`) between that
fresh baseline run and the FIX-04A implementation's run:

```text
total sessions:     200
changed sessions:     5
unchanged sessions: 195

public_0052: hit True->True   rank 4->3     turn 3->3
public_0064: hit True->True   rank 2->1     turn 4->4
public_0080: hit True->True   rank 2->3     turn 4->4
public_0177: hit False->True  rank None->7  turn None->4
public_0183: hit True->True   rank 6->8     turn 4->4
```

```text
new hits:            1   (public_0177, rank 7, turn 4)
new misses:          0
rank improvements:   2   (public_0052 4->3, public_0064 2->1)
rank regressions:    2   (public_0080 2->3, public_0183 6->8)
turn improvements:   0
turn regressions:    0
```

**Simulation-vs-production mismatches: 0/200.** Every changed session
matches the authorized simulation's §9 exactly — same 5 sample_ids, same
directions, same magnitudes. No hidden additional movement.

All 5 changed sessions are `intent_override`; **0 non-override sessions
changed** (checked directly across all 195 unchanged + verified by scenario
type on the 5 changed ones) — §11 satisfied.

---

## 9. Explicit regression check (§10)

```text
public_0080: 2 -> 3   (still a hit, same turn)
public_0183: 6 -> 8   (still a hit, same turn)
```

Matches exactly what the authorization pre-accepted for simulation review:
both remain hits, no first-hit turn worsens, net HR improves, MRR improves,
TechnicalScore improves. **No unexplained additional regression occurred** —
production reproduces the simulation's regression surface exactly, nothing
worse.

---

## 10. Runtime comparison

Matched-methodology, alternating baseline/implemented full-200-session
`evaluate()` calls in the same process (3 runs each, per §12's "2-3 matched
runs" guidance):

```text
FIX-03A baseline (s):    [52.182, 53.114, 61.044]   median 53.114
FIX-04A implemented (s): [51.714, 66.701, 55.211]   median 55.211
```

Median delta: **+2.1s** (~4% of a ~53s run). The two distributions overlap
substantially (52–61s vs 51–67s) — consistent with ordinary run-to-run
noise on this machine, not a systematic regression. This matches the
authorization's stated hypothesis (no new retrieval query layer added), and
that hypothesis was **measured, not assumed** — no optimization attempted,
per §12's own instruction not to optimize absent a real regression.

---

## 11. Git status (final)

```bash
git status --short
```
```
 M starter/agent.py
 M tests/test_fix03a_override_correction.py
?? markdowns/MASTER_HANDOVER_ROUND3.md
?? tests/test_fix04a_slots_preservation.py
```

No `git add`, no `git commit`, no `git push` performed at any point in this
pass, per §13/§16.

---

## 12. Classification

```text
READY FOR COMMIT REVIEW
```

All required evidence reproduces the authorized simulation exactly: full
test suite green (44/44), evaluator numbers match §8 to 6 decimal places,
session-level diff matches §9 with 0/200 mismatches, the two pre-accepted
regressions are exactly as specified and nothing worse, Intent Override
scoping is confirmed, and runtime shows no measurable regression beyond
normal noise. The one consequential side-effect — one existing FIX-03A test
assertion needed updating because it pinned now-superseded scope — is
disclosed in full in §4, not absorbed silently.

**STOP. No stage. No commit. No push**, per authorization §16. This report
is for independent commit-review only.

---

## PART 2 (§14) — Bucket-A phrase-coherence descriptive collection (read-only)

Scope exactly as authorized: descriptive only, no weights, no scoring, no
reranking, no thresholds, no evaluator experiment. Collected for the
**post-FIX-04A** Bucket-A misses (i.e. using the implemented agent above,
not yet committed) since that is the forward-looking baseline the
authorization's own §15 already anticipates ("if FIX-04A locks at 83.0%").

### Method

Replayed the evaluator's own exact turn/behavior-generation logic (imported
`materialize_hidden_fields`, `initial_message`, `customer_reply` directly
from `evaluator/local_evaluator.py`, not reimplemented) for each of the 34
current misses. At each miss's final countable turn, recomputed
term/slot coverage using the agent's **own installed methods**
(`_active_terms`, `_matchable_slots`, `_build_query`) plus the identical SQL
already used in production (`starter/agent.py` lines 327–331,
copied verbatim for instrumentation, not re-derived) — nothing here
reimplements agent logic independently.

A session qualifies as Bucket A if, at that turn: target is present in the
internal Top-50 retrieval pool, `term_coverage == 1.0`, and
`slot_coverage == 1.0` (the exact definition established in `FIX-02-P0`
and `FIX-04`).

**Result: 14 of the 34 current misses are Bucket A** (20 are not — mostly
target absent from the Top-50 pool entirely, i.e. Bucket B/C/D). For each,
recorded whether each active multi-token slot value (e.g. `"95% Rayon, 5%
Spandex"`) occurs as an **exact contiguous phrase**, after the agent's own
tokenizer-normalization, in `title` / `features` / `details` / `description`
— for the target and its 1–3 immediately-higher-ranked pool competitors.
Full raw data: `phrase_coherence_output.json` (scratch, session-local).

### Finding 1 — MEASURED: phrase field placement is 100% `features`, confirming the prior audit

Every single phrase hit, across all 23 (record, active-multi-token-slot-value)
instances in the 14 Bucket-A sessions, that occurred at all occurred in
`features`. Zero hits in `title`, `details`, or `description`. Consistent
with — not new relative to — `FIX-04A`'s own prior bag-of-terms
characterization (§9 of that report), which already found `features` is the
dominant field for 100% of both misses and hits.

### Finding 2 — MEASURED: exact-phrase separation exists in 7/23 (30%) of instances — but the sample is small and possibly confounded

In 7 of 23 instances, the target's active slot value occurs as an exact
contiguous phrase in `features` while **all 1–3 immediately-higher-ranked
competitors** in the same pool do not — a genuine separation the earlier
bag-of-terms characterization did not test for and could not have found (a
bag-of-terms check is blind to word order/contiguity). In the other 16
instances there is no clean separation (target and competitors either both
match or both miss).

```text
public_0011  "undershirts closure"
public_0012  "Wrap closure"
public_0019  "Boot opening measures approximately 6.5\" around"
public_0054  "Soft Fabric"
public_0055  "Shaft measures approximately 1\" from arch"
public_0057  "Shaft measures approximately 0#inches from arch"
public_0151  "Shaft measures approximately Ankle from arch"
```

### Finding 3 — MEASURED, and this is the important caveat: these are exactly the LOW catalog-document-frequency phrases, not a novel coherence signal

A direct catalog-wide (50,000-item) document-frequency check on the exact
same normalized phrases (`phrase_catalog_df_check.py`, scratch) found:

```text
clean-separation phrases:            catalog df (out of 50,000)
  "undershirts closure"                   2
  "Wrap closure"                         50
  "Boot opening measures approx 6.5\""   92
  "Soft Fabric"                         822
  "Shaft measures approx 1\" from arch" 560
  "Shaft measures approx 0#in from arch"  9
  "Shaft measures approx Ankle from arch" 62

no-separation boilerplate examples:  catalog df (out of 50,000)
  "Pull On closure"                    7406
  "Machine Wash"                      10660
  "100% Cotton"                        3776
```

The 7 separating phrases are **low-frequency, specific phrases** (df 2–822);
the phrases that showed **no** separation (`"Pull On closure"`, `"Machine
Wash"`, `"100% Cotton"`) are catalog-wide boilerplate shared by thousands of
products (df 3776–10660). This means the separation observed is
consistent with plain **term/phrase specificity (an IDF-shaped signal)**,
not evidence that phrase-*contiguity* itself (as opposed to just "contains
this rare token") is what's doing the discriminating. **This measurement
cannot distinguish the two** — that would require comparing phrase-match
against single-rare-term-match on the same instances, which is a scoring
comparison and explicitly out of scope for this read-only pass.

**Additional structural caveat, also worth flagging plainly:** the
evaluator's own `intent_card()` (`evaluator/local_evaluator.py:52-71`)
constructs every disclosed constraint value **verbatim from the target
product's own `features`/`details` fields** (only whitespace-cleaned and
length-truncated). So an exact-phrase match against the target is expected
by construction whenever the phrase survives truncation intact — the
catalog-wide df numbers above show it is *not* purely tautological (these
phrases do appear on other products, 2 to 822 of them), but the mechanism
by which the disclosed text is generated is not independent of the target's
own catalog text, and that relationship should be weighed before treating
this as a clean, generalizable content signal.

### Conclusion — a real, measured, non-null result, but genuinely inconclusive on the underlying mechanism

Explicitly separated, following this project's own established discipline:

- **MEASURED**: field placement is 100% `features`, matching the prior null
  characterization.
- **MEASURED**: exact contiguous-phrase presence separates target from all
  immediately-higher competitors in 7/23 (30%) of Bucket-A instances —
  something the earlier bag-of-terms characterization structurally could not
  detect. This is a genuinely different, non-null result from FIX-04A Part
  B's own field-coherence null finding.
- **MEASURED**: the 7 separating cases are exactly the low-catalog-frequency
  phrases; the non-separating cases are exactly the high-frequency
  boilerplate ones. This is consistent with the separation being a
  restatement of term/phrase specificity (IDF-shaped), not proof that
  contiguity itself adds anything beyond rare-token presence.
- **NOT MEASURED, explicitly out of scope here**: whether phrase-contiguity
  discriminates beyond what a plain rare-token check would already achieve
  on the same instances; whether using this signal (in any form) would
  actually promote the target above these specific competitors if it were
  implemented (that requires scoring/reranking, explicitly prohibited in
  this pass); and whether the tautology caveat above materially weakens
  this as a production signal versus a real catalog-content association.
- **HYPOTHESIS**: none proposed for implementation. This finding is a
  genuinely different, more promising signal than FIX-04A Part B's null
  result, but it converges toward the same still-open, well-evidenced,
  never-simulated IDF-weighted-coverage question already on record in the
  Round-3 handover's open items — not a new, independent line. Any future
  proposal building on this should explicitly test whether phrase
  contiguity outperforms plain single-rare-term IDF weighting on the same
  instances before being recommended, per this project's own governing
  rule for IDF-shaped proposals.

Sample size caveat: 14 Bucket-A sessions, 23 (session, slot-value)
instances, 7 separating. This is descriptive evidence to inform a future
decision, not a validated mechanism.

---

## §STOP

No production code was staged, committed, or pushed. `starter/agent.py` and
the two test-file changes above are the complete set of working-tree
modifications from this pass. Part 2's phrase-coherence collection touched
no production or test files at all — it is fully external scratch, per
§14's own read-only instruction. Both parts are ready for independent
review.
