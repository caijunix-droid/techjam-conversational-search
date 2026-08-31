# FIX-05P0 — EXACT-PHRASE TIE-BREAK SIMULATION

Written 2026-08-31. Executes `FIX-05P0 — FINAL NARROW PUSH: EXACT-PHRASE
TIE-BREAK SIMULATION.md`. **SIMULATION ONLY — no production edit, no
parameter search, no stage, no commit, no push.** A methodology bug was
found and fixed mid-pass, disclosed in full in §0 rather than silently
corrected, because it directly contradicted an earlier committed handover's
own characterization data.

```text
PRODUCTION CHANGE: NONE
COMMIT:            NONE
PUSH:              NONE
CLASSIFICATION:    RETURN IMMEDIATELY FOR IMPLEMENTATION REVIEW
```

---

## 0. Methodology correction (disclosed, not buried)

The precheck harness initially reused `evaluator.local_evaluator.normalize_
recommendations()` to read the full 50-candidate pool out of a
`respond(..., top_k=50)` call. That function has a **hardcoded
module-level `TOP_K = 10`** baked into its own dedup loop
(`if len(result) >= TOP_K: break`) — independent of whatever `top_k` the
caller passed to `respond()`. This silently truncated every "full pool" to
10 items, making it look as though most Bucket-A targets were entirely
absent from the retrieval pool (a first run of the precheck found **0**
Bucket-A misses, contradicting `fix04a_implementation_handover.md`'s own
direct count of 14).

Traced to ground truth via three independent checks before trusting
anything further:
1. Running the current, unmodified `starter.agent.Agent` directly (not via
   `git show`) on `public_0011` — confirmed the bug's symptom.
2. Re-running the prior pass's *own* collection script against the
   *current* code — reproduced the correct rank-20 result, proving the bug
   was in the new harness, not a real behavior change.
3. A side-by-side pinpoint script comparing `respond(top_k=10)` vs
   `respond(top_k=50)` trajectories for the same session — confirmed
   messages, `_build_query()` expressions, and final `state.slots` were
   byte-identical between the two; only the pool-extraction step differed.

Fixed by writing a local `full_pool_from_response()` that mirrors
`normalize_recommendations()`'s dedup/clean/catalog-membership logic
**without** the hardcoded cap. Re-validated:

```bash
# Part 0 -- harness vs real evaluator sanity check (hit/rank/turn, all 200)
mismatches: 0
harness hit count: 166 / 200

# Part 0b -- full-pool order reproduction (recomputed coverage/slot_coverage/
# baseline_index vs the pool respond() actually returned)
sessions checked: 200   order mismatches: 0
```

Both hold after the fix — the harness's candidate-generation and first-two-
key ranking are now provably byte-identical to production across every one
of the 200 sessions before any new key is added.

---

## 1. Baseline reproduction

```bash
python3 -m evaluator.local_evaluator
```
```text
HR@10          0.830000
MRR            0.512694
MTTC           5.645000
Efficiency     0.535500
TechnicalScore 0.675908

Hits           166 / 200
```

Exact match to the accepted `cd03f19` checkpoint. Per-session results saved
for diffing (`fix05p0_baseline_cd03f19_results.json`, scratch).

---

## 2. Frozen mechanism (exactly as specified, nothing else)

Candidate generation: unmodified. Primary key: active-term coverage DESC
(unmodified). Secondary key: active-slot coverage DESC (unmodified). New
tertiary key, **only applied when both above are already tied**: exact
contiguous active multi-token slot phrase coverage DESC. Final: original
BM25 rank ASC (`baseline_index`, recovered independently via the identical
raw SQL already in `starter/agent.py`).

Phrase coverage, exactly per the authorization's §4: only active slot
values with ≥2 usable normalized tokens; a slot is satisfied if its complete
normalized phrase occurs contiguously in ANY of title/features/details/
description (no field weights); score = satisfied / matchable multi-token
slots; 0 if no multi-token slot exists (falls through to unmodified
behavior — a provable no-op, not just an assumed one, see §5). No IDF, no
rarity weight, no phrase-length weight, no fuzzy/stemming/synonym matching.

---

## 3. Part 5 — Bucket-A misses precheck (full tied groups, not just 1–3 competitors)

14 Bucket-A misses found (target present in the retrieval pool, term
coverage = 1.0, slot coverage = 1.0) — same count as the prior
characterization, now correctly located after the §0 fix.

```text
sample_id      cur_rank  tie_group  target_phrase_cov  competitors[hi/eq/lo]  cf_rank
public_0011      13         20            1.000              0/1/18            2
public_0012      17         28            1.000              0/4/23            4
public_0019      24         48            1.000              0/3/44            2
public_0041      11         36            1.000              0/35/0            11  (unchanged)
public_0054      22         28            1.000              0/6/21            6
public_0055      15         27            1.000              0/3/23            2
public_0057      16         23            1.000              0/1/21            1
public_0081      13         32            1.000              0/27/4            13  (unchanged)
public_0096      20         39            0.500              0/38/0            20  (unchanged)
public_0115      11         12            1.000              0/10/1            10
public_0137      19         25            1.000              0/22/2            18  (still miss)
public_0151      15         27            1.000              0/3/23            1
public_0159      11         16            1.000              0/8/7             6
public_0170      13         24            1.000              0/11/12           7
```

```text
predicted rescued into Top10:  10
improved but still >10:         1
unchanged:                      3
worsened:                       0
```

**Structural observation, measured directly, not inferred**: `competitors_
higher_phrase` is 0 in every single row. The target's active phrase is
never beaten by a competitor's — consistent with (and explains) the
disclosed-text-provenance caveat already on record in
`fix04a_implementation_handover.md` §Finding 3 (`intent_card()` builds
constraint text verbatim from the target's own catalog fields). The 3
"unchanged" sessions (`public_0041`, `public_0081`, `public_0096`) are
exactly the ones where nearly the *entire* tied group shares the same
phrase (boilerplate, e.g. "Pull On closure") — the tier correctly
recognizes this as non-discriminating and falls through to the unchanged
baseline order, exactly as designed.

---

## 4. Part 6 — existing-hit safety precheck (ALL 166 hits, not a sample)

**Invariant established and used throughout, not just claimed**: the sort
is lexicographic. A candidate can only be reordered by the new key *within*
a group already tied on both prior keys — it can never cross a
(coverage, slot_coverage) group boundary. So a hit whose group has exactly
1 member (itself) is *provably* unaffected, with no need to even compute
its phrase coverage. This was used to skip unnecessary work, not assumed
without basis — the same invariant is what makes the Part 8 full-simulation
regression count (§6) fully attributable to real ties.

```text
hits with a tied group (size>1) affecting target:              115
hits with NO tie affecting target (provably unaffected):        51

promoted:                  35
unchanged (tied, same rank): 77
demoted but still Top10:      3
REMOVED FROM TOP10 (new miss): 0
```

Zero hits would be lost. Three hits show mild demotion, still comfortably
inside Top10 — the same "boilerplate-phrase-tied, reshuffled by BM25
baseline order" mechanism as the 3 unchanged Bucket-A misses above. (These
turn out to be the exact same 3 sessions the full simulation later
confirms as rank regressions — see §6.)

---

## 5. Part 7 — fast gate

```text
Bucket-A rescue:        10/14 into Top10, 1 further improved, 0 worsened
Existing-hit damage:    0 removed from Top10, only mild in-Top10 reshuffling
```

Credible net upside on both sides of the required check (§6/§7's own
"do not optimize against only misses" instruction). **Gate: PROCEED to the
full 200-session simulation.**

---

## 6. Part 8 — full 200-session simulation

Re-sorts the pool at **every turn** (not just the turn each session
happened to hit at under the current ranking) — necessary because the new
tier can shift which turn produces a hit, not only the final rank; see the
`public_0117` case below, which the static precheck could not have caught.

```bash
python3 fix05p0_full_simulation.py   # scratch, reuses real respond()
```
```json
{
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

| Metric | cd03f19 (current) | FIX-05P0 (simulated) | Δ |
|---|---:|---:|---:|
| HR@10 | 0.830000 | **0.880000** | **+0.050000 (+10 hits, 176/200)** |
| MRR | 0.512694 | **0.567583** | **+0.054889** |
| MTTC | 5.645000 | **5.495000** | **−0.150000 (faster)** |
| Efficiency | 0.535500 | **0.550500** | **+0.015000** |
| TechnicalScore | 0.675908 | **0.720375** | **+0.044467** |

### Session deltas

```text
new hits:            10   public_0011(r2,t8) public_0012(r4,t8) public_0019(r6,t8)
                           public_0054(r6,t9) public_0055(r2,t10) public_0057(r1,t10)
                           public_0115(r10,t8) public_0151(r1,t10) public_0159(r6,t9)
                           public_0170(r7,t8)
new misses:            0

rank improvements:    35   (stayed hit, better rank -- e.g. public_0016 8->1,
                             public_0108 10->2, public_0118 9->2, public_0021 6->1)
rank regressions:      4   public_0103  6->8
                            public_0117  1->6   (see mechanism below)
                            public_0130  2->4
                            public_0189  2->4
rank unchanged (hit):  127

first-hit-turn improvements:  2   public_0117 turn 3->1   public_0153 turn 8->2
first-hit-turn regressions:   0
```

**Exact match to the precheck's own prediction**: the 10 new hits are
sample-ID-for-sample-ID identical to the precheck's 10 "rescued into
Top10" Bucket-A sessions (§3). `public_0041`/`public_0081`/`public_0096`
(precheck: "unchanged") remain misses in the full simulation, also exactly
as predicted. 3 of the 4 rank regressions (`public_0103`, `public_0130`,
`public_0189`) are the exact 3 sessions the Part 6 hit-safety precheck
already flagged as "demoted but still Top10," with matching deltas.

### `public_0117` — the one regression the precheck could not predict, traced directly

Not a demotion of an existing rank at the *same* turn — a genuine
turn/rank trade-off. Traced turn-by-turn:

```text
turn 1 (buying opener, hard requirement disclosed):
  active_slots = {'feature': 'Synthetic Rubber sole'}
  target: coverage=1.0 slot_cov=1.0 phrase_cov=1.0 baseline_idx=36
  old (current) rank in pool: 27  -- NOT a hit this turn under current ranking
  new (phrase-tier) rank: 6      -- IS a hit this turn under the new ranking

  5 candidates rank above target under the new order, ALL with
  coverage=1.0/slot=1.0/phrase=1.0 (they also contain the exact phrase
  "synthetic rubber sole" -- evidently common wording across this
  product category) and better baseline BM25 rank (9, 16, 19, 28, 31 vs
  target's 36).
```

Under the **current** ranking, without the phrase discriminator, the tied
group at turn 1 was ordered purely by `baseline_index` among a much larger
set of coverage/slot-tied candidates (not just the 6 that share the exact
phrase) — target landed at raw rank 27, not a turn-1 hit. The conversation
continued to turn 3, where additional disclosed detail narrowed the field
enough for target to reach rank 1 under the *current* ranking.

Under the **new** ranking, the phrase tier immediately isolates target into
a much smaller, already-highly-relevant group at turn 1 — producing a hit
three turns earlier, but `evaluate()`'s loop stops at the *first* hit turn
by design (unrelated to this experiment), so it never reaches turn 3's
eventual rank-1 result. Net effect for this one session: MTTC improves
dramatically (turn 3→1) at the cost of MRR (rank 1→6, RR 1.0→0.1667).

This is a genuine, mechanistically-understood trade-off inherent to any
change that can make a hit happen *earlier* — not a defect in the phrase
logic itself, and not hidden: it is the single largest RR loss in the
regression set (−0.8333, see §7) and is reported as such.

---

## 7. Part 9 — HR-changing vs Top10-membership-preserving movements

```text
A. HR-changing (new hits + new misses):              10 + 0 = 10
B. Top10-membership-preserving rank movements:        35 + 4 = 39
```

Category B, full reciprocal-rank accounting (rank before/after, RR
before/after) — 39 rows, scratch file `fix05p0_diff_output.json` has the
complete list; regressions shown in full, improvements summarized:

```text
4 regressions (full):
  public_0103  rank 6->8   RR 0.1667->0.1250  (-0.0417)
  public_0117  rank 1->6   RR 1.0000->0.1667  (-0.8333)
  public_0130  rank 2->4   RR 0.5000->0.2500  (-0.2500)
  public_0189  rank 2->4   RR 0.5000->0.2500  (-0.2500)

35 improvements: RR deltas from +0.0111 (public_0035, 10->9) to +0.8750
(public_0016, 8->1); largest cluster is rank-2-to-1 promotions (6 sessions,
each +0.5000 RR).

Category B total RR: before=10.2929  after=17.2778  delta=+6.9849
Category A (new hits) RR added: +3.9929
Category A (new misses) RR removed: 0.0000
```

**Cross-check, not just claimed**: `(+3.9929 + 6.9849) / 200 = 0.054889`,
which matches the aggregate ΔMRR (0.567583 − 0.512694 = 0.054889) to the
full precision reported by the evaluator's own `metric_summary()`. The
session-level accounting and the aggregate metric agree exactly.

Both HR and MRR improve substantially and independently of each other —
this is not a case of one metric moving at the other's expense.

---

## 8. Part 10 — MTTC

No independent MTTC optimization or turn-dependent routing was added, per
the authorization's own instruction. Naturally occurring effect of the
frozen mechanism:

```text
first-hit-turn improvements: 2  (public_0117 turn 3->1, public_0153 turn 8->2)
first-hit-turn regressions:  0
```

Plus the aggregate MTTC improvement (5.645→5.495) driven mostly by the 10
new hits themselves (a session that was previously a miss — effectively an
MTTC penalty — now counts at its actual hit turn).

---

## 9. Part 11 — decision

```text
net HR positive:              YES  (+10 hits, +0.050000)
meaningful MRR improvement:   YES  (+0.054889, ~10.7% relative)
TechnicalScore improves:      YES  (+0.044467, ~6.6% relative)
regression surface explainable: YES  (4 rank regressions, all traced to one
                                       of two understood mechanisms; 0 new
                                       misses; 0 turn regressions)
mechanism remains general:    YES  (single frozen formula, no session-
                                     specific rules, no scenario routing)
```

All five conditions for a "strong result" (§11) hold.

```text
CLASSIFICATION: RETURN IMMEDIATELY FOR IMPLEMENTATION REVIEW
```

---

## 10. Time discipline (§12) — respected

No runtime profiling, no neural embeddings, no IDF tuning, no BM25/phrase/
slot weight search, no threshold optimization, no new state logic. One
frozen formulation, tested once, reported as found.

---

## §STOP

No production file was edited. No file was staged, committed, or pushed.
Everything in this report is derived from scratch-directory simulation
scripts (session-local, not part of git history):
`fix05p0_harness.py`, `fix05p0_collect.py`, `fix05p0_precheck.py`,
`fix05p0_full_simulation.py`, `fix05p0_diff.py`, plus the diagnostic
scripts that traced and fixed the §0 methodology bug
(`trace_divergence.py`, `pinpoint_bug.py`, `trace_0117.py`). Full raw
outputs: `fix05p0_raw_collection.json`, `fix05p0_precheck_output.json`,
`fix05p0_full_simulation_results.json`, `fix05p0_diff_output.json` (all
scratch, session-local, not guaranteed to persist).

Ready for independent implementation-review authorization, per this
project's own established evidence-first gate.
