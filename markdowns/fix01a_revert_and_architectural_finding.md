# FIX-01A — Revert + Architectural Finding

Status: `starter/agent.py` restored to the accepted `037b52d` baseline. **No commit made.**
FIX-01A's evidence is preserved, not deleted. FIX-01B is **not** implemented in this pass —
architecture/hypothesis only, per directive.

---

## A. Working-tree restoration

**Pre-revert status:**
```
 M starter/agent.py
?? markdowns/fix01_cleanup_inspection.md
?? markdowns/fix01_intent_override_handover.md
?? markdowns/fix01_prepatch_verification.md
?? markdowns/fix01_restored_baseline.md
?? tests/test_intent_override_fix01.py
```

**Preserved artifacts** (created before touching `starter/agent.py`):
- `markdowns/patches/fix01a_intent_override.patch` — the exact FIX-01A diff, captured via
  `git diff -- starter/agent.py > markdowns/patches/fix01a_intent_override.patch`
  (63 lines) before any restoration step.
- `markdowns/fix01_intent_override_handover.md` — the full FIX-01A implementation +
  benchmark handover (untouched).
- `tests/test_intent_override_fix01.py` — the 7 targeted tests (untouched, still present
  and still passing against the patch artifact, though no longer against production code).
- `markdowns/probes/*.py` — the override probes (untouched).
- `markdowns/fix01_cleanup_inspection.md`, `markdowns/fix01_prepatch_verification.md`,
  `markdowns/fix01_restored_baseline.md` — untouched.

**Exact restoration method:**
```bash
git checkout HEAD -- starter/agent.py
```
`HEAD` at the time of this operation was `037b52d` (the accepted, previously-proven clean
baseline) — no intervening commit existed, so `HEAD` and the target restoration point are
the same commit. This restores only `starter/agent.py`; no other file was touched by this
command.

**Post-revert SHA256:**
```
5b1d38d99fd49d8ba61e5f2ea278e8acfd665f8dfc50aa69f130e20415313544
```
Matches the directive's expected value exactly.

**Confirmation `starter/agent.py` diff is empty:**
```bash
git diff -- starter/agent.py
# (no output)
```

**Post-restoration git status:**
```
?? markdowns/fix01_cleanup_inspection.md
?? markdowns/fix01_intent_override_handover.md
?? markdowns/fix01_prepatch_verification.md
?? markdowns/fix01_restored_baseline.md
?? markdowns/patches/
?? tests/test_intent_override_fix01.py
```
`starter/agent.py` no longer appears as modified — it is byte-identical to `HEAD`. All
preserved evidence remains present and untracked (nothing was committed, nothing was
deleted).

---

## B. Restored benchmark (proven, not assumed)

**Unit tests:**
```
python3 -m unittest tests.test_evaluator
Ran 3 tests in 0.001s — OK
```

**Evaluator run 1:**
```
HR@10 = 0.73
MRR = 0.465458
MTTC = 6.345
Efficiency = 0.4655
TechnicalScore = 0.597737
```

**Evaluator run 2:** identical to run 1 in every field.

**Deterministic comparison:** `diff` of the two run outputs (session UUIDs excluded) is
empty.

**Scenario metrics** (both runs identical):

| Scenario | HR@10 | MRR | MTTC |
|---|---:|---:|---:|
| Buying | 0.7875 | 0.436796 | 6.2875 |
| Browsing | 0.7125 | 0.470184 | 6.025 |
| Intent Override | 0.633333 | 0.520556 | 7.233333 |
| Boundary | 0.7 | 0.491667 | 6.7 |

All values match the directive's expected historical reference exactly — no STOP
condition triggered.

---

## C. FIX-01A experiment classification

```
Defect status:        CONFIRMED (24/30 real override sessions cross-bucket,
                       24/24 of those retained stale state pre-patch)
Semantic status:       PASS (provenance-aware replacement worked exactly as
                       specified — 0/24 stale after patch, all 7 targeted
                       tests A–E passed)
Isolation status:      PASS (zero change to Buying/Browsing/Boundary metrics;
                       zero change to BM25/FTS/ASK_ORDER/budget/clarification
                       logic — confirmed via diff)
Benchmark status:      FAIL (TechnicalScore 0.597737 → 0.594491; Intent
                       Override MRR 0.520556 → 0.455079; 7 sessions changed,
                       0 improved, 7 worsened or later-turn)
Production decision:   REJECTED / REVERTED (this document)
```

---

## D. Evidence preserved (not deleted, listed explicitly)

- `markdowns/fix01_intent_override_handover.md` — full implementation + benchmark handover
- `tests/test_intent_override_fix01.py` — 7 targeted tests (A–E), still present
- `markdowns/probes/probe_override_batch.py`, `probe_override_single.py`,
  `probe_compound.py` — unchanged
- `markdowns/patches/fix01a_intent_override.patch` — exact diff artifact, newly created in
  this pass, captured before reverting production code
- `markdowns/fix01_cleanup_inspection.md`, `markdowns/fix01_prepatch_verification.md`,
  `markdowns/fix01_restored_baseline.md` — the full investigation trail preceding FIX-01A

None of the above were modified or deleted in this pass. Only `starter/agent.py` was
changed (restored).

---

## E. Architectural finding

**The coupling**: `SessionState.slots` is used for two distinct purposes at once —

```
state.slots
    │
    ├── represents CURRENT ACTIVE customer intent
    │   (what _next_ask_attribute reads to decide what's still unknown,
    │    what the customer would recognize as "what I told you")
    │
    └── supplies the literal search terms
        (what _build_query flattens into the FTS5 OR-query)
```

**Why this caused the FIX-01A regression**: the evaluator's synthetic `intent_card()`
derives both `old_value` (the superseded preference) and `new_value` (the override) from
the *same real target product's* own `features`/`details` text (established directly by
reading `evaluator/local_evaluator.py`'s `intent_card()` — not inferred). So the "stale"
old preference was, lexically, never noise — it was a verbatim substring of the true
target's own listing, exactly as valid a BM25 match as the new value. FIX-01A correctly
removed it from the *active intent* representation (semantically required — the customer
said to ignore it), but because that same structure also feeds the *retrieval query*,
removing it also removed a working lexical match with nothing to replace it. That is
precisely why HR@10 stayed flat (removal didn't cause new misses — the target was
generally still reachable) while MRR/MTTC in the Intent Override subset got worse (the
rank/speed of reaching it, specifically in the 7 affected sessions, depended partly on
that now-removed term).

This is a structural finding about the current `SessionState` design, not specific to the
FIX-01A patch's code — any future fix that correctly removes a superseded value from
`state.slots` will hit the same coupling, unless the two roles (active-intent semantics
vs. retrieval evidence) are separated.

**Scope note on the private set** (inference, labeled as such): the private 800-session
set is generated by the same `materialize_hidden_fields` → `intent_card()` code path as
the public 200, so the same old/new-value-share-a-target property should hold there too.
This is *not* independently measured (the private set is inaccessible from this repo) —
it is a structural inference from reading the shared code path, not a benchmark result.

---

## F. FIX-01B research hypothesis (not implemented)

**Direction**: separate the two roles currently fused in `state.slots`.

```
USER CONVERSATION
       │
       ▼
┌───────────────────────┐
│ ACTIVE INTENT STATE   │   governs: what to ask next, what the
│ current preferences   │   customer would recognize as active,
│ current constraints   │   final-ranking emphasis
└───────────┬───────────┘
            │
            ▼
       FINAL RANKING

USER CONVERSATION
       │
       ▼
┌───────────────────────┐
│ RETRIEVAL EVIDENCE    │   governs: broad candidate generation —
│ active terms          │   may retain historically-mentioned,
│ historical terms      │   now-superseded terms if they still
│ possibly superseded   │   help recall
└───────────┬───────────┘
            │
            ▼
   BROAD CANDIDATE SEARCH
```

Conceptual pipeline:
```
conversation + profile
        │
parse / update active intent   (semantically correct — supersession removes
        │                        the old value from "active", per FIX-01A's
        │                        already-proven-correct logic)
        ▼
broad candidate generation using useful conversational evidence
        │                       (may still draw on now-inactive terms for recall)
        ▼
candidate pool
        ▼
rerank using current active intent
        ▼
Top 10
```

**Semantic invariant to preserve**: a superseded preference must not be represented as
currently active intent (this is what FIX-01A already achieves and is not in question).

**Retrieval invariant to add**: useful historical lexical evidence should not necessarily
be destroyed merely because it became conversationally inactive.

**Not decided in this pass**: how candidate generation would actually use "historical but
inactive" terms (e.g., a separate query pass, a term weighting scheme, or something else),
what the rerank stage looks like concretely, or any weights/constants. Per the directive,
no implementation, no weight tuning, no public-set-tuned constants — hypothesis only.

---

## Final classification (per directive)

```
FIX-01 defect finding:              CONFIRMED
FIX-01A provenance patch:           SEMANTIC PASS, BENCHMARK FAIL, PRODUCTION REJECTED
CURRENT PRODUCTION STATE:           037b52d baseline, restored and re-proven
COMMIT:                             NO
NEXT RESEARCH DIRECTION:            FIX-01B — decouple active intent from retrieval evidence (hypothesis only, not implemented)
```

STOP. Awaiting review and explicit authorization before any FIX-01B implementation.
