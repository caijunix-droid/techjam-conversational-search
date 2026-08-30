# FIX-01 Intent Override — Implementation + Verification Handover

Status: **implemented, tested, benchmarked. NOT committed** (working tree left modified,
per explicit instruction). No file outside `starter/agent.py` (production) and
`tests/test_intent_override_fix01.py` (new, isolated test file) was changed.

---

## 0. Repository state

| | Branch/commit | git status | SHA256 `starter/agent.py` |
|---|---|---|---|
| CURRENT-HEAD PRE-CLEANUP | `main` @ `c6461c4` | clean | `03d4ecfcc0fdc0337c8d04465105b580c363b8591d797f1905276391fd4ed371` |
| RESTORED FIX-01 BASELINE | `main` @ `037b52d` | clean | `5b1d38d99fd49d8ba61e5f2ea278e8acfd665f8dfc50aa69f130e20415313544` |
| POST-FIX-01 (current) | `main` @ `037b52d` + uncommitted patch | `M starter/agent.py`, new `tests/test_intent_override_fix01.py`, 3 pre-existing untracked `markdowns/*.md` | `d4572f1fca7e715b5826b4e0044401cdc06884dea6722eb9278ffe8e97ca19c4` |

No commit was created for the implementation. `demo/interactive.py`, `evaluator/`,
`docs/`, `data/`, and `starter/agent_baseline.py` are confirmed untouched by this patch
(`git diff --stat` empty for all of them except `starter/agent.py`).

---

## 1. Independent pre-patch reproduction

Already completed and reported in `fix01_restored_baseline.md` against the restored,
clean `037b52d` baseline (i.e., the actual code this patch was applied on top of):

```
HR@10 = 0.730000
MRR   = 0.465458
MTTC  = 6.345000
Efficiency = 0.4655
TechnicalScore = 0.597737
```

30-session override probe: 24/30 cross-bucket, 24/24 stale-state confirmed. Confirmed
independently reproducible (2 evaluator runs, deterministic; unit tests 3/3 pass) before
any patch code was written.

---

## 2. Root cause

**Code path**: `starter/agent.py`, `_parse_message()`, explicit-override branch (previously
lines ~161–167).

```python
if text.startswith("Actually, ignore my earlier preference. What I need is: "):
    new_value = ...
    attr = classify(new_value)
    state.slots[attr] = new_value   # only touches the NEW value's own bucket
```

**Why stale state occurs**: the handler only ever writes to
`state.slots[classify(new_value)]`. It never inspects which bucket the *old* value (set
at the Intent Override turn-1 opener, `"{category}. {old_value}"`) was filed under. When
`classify(old_value) != classify(new_value)` — true in 24/30 (80%) of real override
sessions — the old value's slot is never touched and survives, contradicting the
customer's explicit "ignore my earlier preference."

---

## 3. Patch

**File changed**: `starter/agent.py` only.

**Conceptual change**: `SessionState` gains two new fields,
`override_source_attr: str | None` and `override_source_value: str | None`. When the
Intent Override turn-1 opener is parsed, in addition to filling the slot as before, the
code now also records which bucket/value was just filed there. When the explicit override
message later arrives, before writing the new value the code checks whether that recorded
slot **still holds exactly that recorded value** — if so, it is deleted (the actual
provenance-aware replacement); if the slot's content has since changed (case D), nothing
is deleted, avoiding a blind/unsafe deletion. The provenance is then cleared (consumed)
either way, and the new value is classified and written as before.

**Diff** (full, verbatim):
```diff
 class SessionState:
-    __slots__ = ("category", "slots", "asked", "exhausted", "profile_terms", "last_turn_asked")
+    __slots__ = (
+        "category", "slots", "asked", "exhausted", "profile_terms", "last_turn_asked",
+        "override_source_attr", "override_source_value",
+    )

     def __init__(self, profile_terms: str) -> None:
         self.category = ""
@@
         self.profile_terms = profile_terms
         self.last_turn_asked: str | None = None
+        # Provenance for the one preference an Intent Override turn may later
+        # supersede: which bucket it was filed under, and its exact value at
+        # the time it was recorded.
+        self.override_source_attr: str | None = None
+        self.override_source_value: str | None = None
@@
             else:
                 # intent_override opener: "{category}. {old_value}"
                 category, _, remainder = rest.partition(". ")
                 state.category = category.strip()
                 remainder = remainder.rstrip(".").strip()
                 if remainder:
-                    state.slots[classify(remainder)] = remainder
+                    attr = classify(remainder)
+                    state.slots[attr] = remainder
+                    # Remember this as the preference a later override may
+                    # supersede -- both which bucket it landed in and its
+                    # exact value, so we can tell it apart from anything
+                    # else that bucket picks up before the override arrives.
+                    state.override_source_attr = attr
+                    state.override_source_value = remainder
             return

         # Explicit intent override mid-conversation.
         if text.startswith("Actually, ignore my earlier preference. What I need is: "):
             new_value = text[len("Actually, ignore my earlier preference. What I need is: "):].rstrip(".").strip()
+            if state.override_source_attr is not None:
+                source_attr = state.override_source_attr
+                source_value = state.override_source_value
+                # Only remove the superseded preference if it still occupies
+                # its original slot unchanged -- if something else already
+                # overwrote that slot, this provenance no longer applies and
+                # we must not delete the newer value blindly.
+                if state.slots.get(source_attr) == source_value:
+                    del state.slots[source_attr]
+                state.override_source_attr = None
+                state.override_source_value = None
             if new_value:
                 attr = classify(new_value)
-                # Drop any stale value under the same bucket, then set the new one.
                 state.slots[attr] = new_value
             return
```

Nothing else in the file changed: BM25 field weights, FTS schema, tokenization,
`ASK_ORDER`, clarification policy (`_next_ask_attribute`), profile logic, and budget
handling (`BUDGET_RE`, `_build_query`) are byte-identical to the restored baseline.

---

## 4. Targeted semantic tests

New file: `tests/test_intent_override_fix01.py` (7 tests, all passing). Not modifying any
existing test file. Uses a tiny synthetic single-product catalog since these tests exercise
`SessionState`/`_parse_message` logic, not retrieval quality.

| Test | Directive case | Result |
|---|---|---|
| `test_different_attribute_override_removes_old_and_sets_new` | A | ✅ old `feature` removed, `material` set |
| `test_same_attribute_override_replaces_value` | B | ✅ `color` black→white, no residue |
| `test_unrelated_constraints_survive_override` | C | ✅ unrelated `material`/`budget` survive unchanged |
| `test_override_does_not_delete_slot_if_source_no_longer_matches` | D | ✅ stale provenance does not delete a slot value that changed since |
| `test_normal_buying_flow_unaffected` | E | ✅ unaffected |
| `test_normal_browsing_flow_unaffected` | E | ✅ unaffected |
| `test_normal_boundary_flow_unaffected` | E | ✅ unaffected |

```
Ran 7 tests in 0.007s — OK
```

---

## 5. 30-session Intent Override probe (real data, before/after)

Ran `markdowns/probes/probe_override_batch.py` unchanged, against both the restored
baseline and the patched agent.

| | Before (restored baseline) | After (patched) |
|---|---:|---:|
| Sessions checked | 30 | 30 |
| Cross-bucket cases (old/new classify differently) | 24 | 24 |
| Stale old value still present after override | **24/24** | **0/24** |

No anomalies: every one of the 24 applicable sessions now shows the old value correctly
removed. The 6 same-bucket sessions were already correct before and remain correct (the
new value overwrites the same key either way).

---

## 6. Full 200-session benchmark

Two independent runs each, before and after; both deterministic (session UUIDs excluded
from diff).

| Metric | Before (restored baseline) | After (patched) | Delta |
|---|---:|---:|---:|
| HR@10 | 0.730000 | 0.730000 | 0 |
| MRR | 0.465458 | 0.455637 | **−0.009821** |
| MTTC | 6.345000 | 6.360000 | **+0.015000** |
| Efficiency | 0.465500 | 0.464000 | −0.001500 |
| TechnicalScore | 0.597737 | 0.594491 | **−0.003246** |

Overall hit rate is unchanged (no session flipped in or out of the scored Top 10). The
regression is entirely in ranking quality (MRR) and turn count (MTTC) among sessions that
still hit.

---

## 7. Scenario benchmark

| Scenario | Metric | Before | After | Delta |
|---|---|---:|---:|---:|
| Buying | HR@10 | 0.7875 | 0.7875 | 0 |
| Buying | MRR | 0.436796 | 0.436796 | 0 |
| Buying | MTTC | 6.2875 | 6.2875 | 0 |
| Browsing | HR@10 | 0.7125 | 0.7125 | 0 |
| Browsing | MRR | 0.470184 | 0.470184 | 0 |
| Browsing | MTTC | 6.025 | 6.025 | 0 |
| Intent Override | HR@10 | 0.633333 | 0.633333 | 0 |
| Intent Override | MRR | 0.520556 | 0.455079 | **−0.065477** |
| Intent Override | MTTC | 7.233333 | 7.333333 | **+0.1** |
| Boundary | HR@10 | 0.7 | 0.7 | 0 |
| Boundary | MRR | 0.491667 | 0.491667 | 0 |
| Boundary | MTTC | 6.7 | 6.7 | 0 |

Buying, Browsing, and Boundary are **byte-identical** before/after — confirms the patch's
blast radius is exactly the Intent Override scenario, nothing else, as intended. All of
the measured regression is concentrated in Intent Override's MRR (−12.6% relative) and
MTTC (+1.4% relative).

---

## 8. Session-level changes

7 of 200 sessions changed outcome, all Intent Override, all sample_ids independently
diffed from the two runs' `sessions` arrays (not sampled — full 200-session comparison):

| sample_id | Before (hit/rank/turn) | After (hit/rank/turn) | Classification |
|---|---|---|---|
| public_0004 | True / 1 / 3 | True / 1 / 5 | changed-neutral-on-rank, **worse on turn** |
| public_0013 | True / 1 / 4 | True / 1 / 5 | changed-neutral-on-rank, **worse on turn** |
| public_0084 | True / 3 / 4 | True / 7 / 4 | **worsened (rank)** |
| public_0089 | True / 1 / 3 | True / 4 / 3 | **worsened (rank)** |
| public_0103 | True / 5 / 4 | True / 7 / 4 | **worsened (rank)** |
| public_0123 | True / 1 / 3 | True / 3 / 3 | **worsened (rank)** |
| public_0130 | True / 2 / 3 | True / 5 / 3 | **worsened (rank)** |

**Zero sessions improved.** Zero new hits, zero new misses, zero improved ranks, zero
earlier hits. All 7 changes are either a worse rank at the same turn, or the same rank
reached at a later turn (which itself is an MTTC cost, not a neutral outcome despite the
rank staying at 1). This directly explains the aggregate MRR/MTTC regression in §6–§7 —
it is not noise or an aggregation artifact, it is fully accounted for by these 7 sessions.

---

## 9. Regression testing

```bash
python3 -m unittest tests.test_evaluator      # 3/3 pass, unchanged
python3 -m unittest tests.test_intent_override_fix01   # 7/7 pass (new)
python3 -m evaluator.local_evaluator          # run twice, byte-identical results
```

No other regression suite exists in the repo beyond these two files.

---

## 10. Unexpected findings (negative evidence)

**The fix is semantically correct but measurably costs score, and the cause is now
understood, not mysterious.** Tracing why: `evaluator/local_evaluator.py`'s
`intent_card()` derives every constraint — both `hard_constraints` (source of
`new_value`) and `soft_preferences` (source of `old_value`) — from the **same real
target product's own `features`/`details` fields**. This means the "stale" old preference
was never noise from an unrelated angle; it was always a verbatim substring of the true
target's own listing text, exactly like the new value. Under this benchmark's own scripted
BM25 retrieval, keeping the "superseded" lexical terms in the query was accidentally
supplying genuine, correct retrieval signal for the same target — deleting them (correctly,
per the conversational spec) removes that accidental signal with nothing to replace it,
worsening rank/turns in the sessions it touches.

This is a structural property of how `intent_card()` builds synthetic constraints (same
target product for both old and new value), not a public-set-only quirk — the private
800-session set is generated by the same code path (`materialize_hidden_fields` →
`intent_card`), so this effect is expected to recur there too, not just be public-set
noise. This is **inference**, not directly measured (the private set is inaccessible),
labeled as such.

---

## 11. Claims established (directly supported by evidence in this pass)

- The pre-patch stale-state defect is real, reproduces deterministically, and is now
  fixed: 24/24 → 0/24 on the real 30-session override set.
- The fix is scoped exactly as required: zero change to Buying/Browsing/Boundary sessions,
  zero change to BM25/FTS/`ASK_ORDER`/budget/clarification logic (all confirmed via diff
  and byte-identical scenario metrics).
- The fix introduces a real, measured, deterministic regression: TechnicalScore
  0.597737 → 0.594491, entirely concentrated in and explained by 7 Intent Override
  sessions, none of which improved.
- All 7 changed sessions were already hits before the patch; the patch did not create or
  remove any hit — it only degraded rank/turn among sessions already succeeding.
- Targeted unit tests (cases A–E) all pass, confirming the provenance logic behaves as
  specified, including the defensive case D (source slot changed before override arrives).

## 12. Claims NOT established (explicit uncertainty)

- Whether this regression would also appear on the private 800-session set — not testable
  from this repo; the structural argument in §10 is an inference, not a direct
  measurement.
- Whether a more sophisticated fix (e.g., down-weighting rather than fully deleting the
  superseded lexical terms) would recover the lost signal while keeping correct
  conversational semantics — not attempted; would be a second conceptual change, out of
  FIX-01's scope lock.
- Whether the organizers' actual (unpublished) judging process rewards conversational
  correctness independent of the local TechnicalScore — not knowable from this repo.

## 13. Recommendation (advisory only)

This is directive Case C: override correctness improved, but the benchmark score
decreased materially (TechnicalScore −0.54% relative, Intent Override MRR −12.6%
relative), and the root cause (accidental lexical signal from the benchmark's own
construction) is understood, not a mystery to investigate further.

Given the explicit instruction not to auto-keep in this case, and that a real trade-off
exists between spec-mandated conversational correctness and current lexical-retrieval
score: **advisory recommendation is INVESTIGATE / team decision, not an automatic KEEP or
REVERT.** Both positions are defensible on the evidence gathered here:

- *For keeping*: the spec explicitly defines "replace, not append" as the correct
  behavior (Slide 9's own weak-vs-strong-agent framing) — the regression reflects a
  crude, purely-lexical retrieval mechanism being unable to recover signal a smarter
  retriever (e.g. one that separately weights conversational-recency vs. all-time lexical
  match) would not have needed the stale term for in the first place.
- *For reverting*: measured on the actual scored benchmark, right now, this patch makes
  the number that matters strictly worse in every session it touches, with zero
  offsetting improvements — Case C's own text says this is not sufficient to keep on
  logic alone.

No commit has been made. Working tree left as-is (`M starter/agent.py`, new
`tests/test_intent_override_fix01.py`) for review before any further action.
