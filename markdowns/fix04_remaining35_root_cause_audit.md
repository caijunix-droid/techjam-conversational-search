# FIX-04 — Remaining-35 Root-Cause Audit

Written 2026-08-31. Executes `FIX-03A — COMMIT AUTHORIZATION + NEXT ROOT-CAUSE
AUDIT.md`. Part 1 (commit) is complete and reported first. Part 2 (the
root-cause audit) is **read-only** — no production edits, no staging, no new
commit, no push beyond the FIX-03A commit.

---

## Part 1 — FIX-03A commit

```bash
git rev-parse HEAD                 # c642094... (before)
shasum -a 256 starter/agent.py     # c839811... (before)
python3 -m unittest discover -s tests -p 'test*.py'   # 36/36 PASS
python3 -m evaluator.local_evaluator                  # matched required numbers exactly
git add starter/agent.py tests/test_fix03a_override_correction.py
git commit -m "FIX-03A: preserve unrelated active intent on override"
```

```
[main 1e2848e] FIX-03A: preserve unrelated active intent on override
 2 files changed, 191 insertions(+), 2 deletions(-)
```

`git rev-parse HEAD` → `1e2848eae6ca05f6c2d5707c796276a2d7de1a1e`. `git status
--short` shows only pre-existing untracked markdown/research files. **Not
pushed.**

```
HR@10            0.825000
MRR              0.510105
MTTC             5.680000
Efficiency       0.532000
TechnicalScore   0.671932
Hits             165 / 200
Misses            35 / 200
```

---

## Part 2 — Root-cause audit (read-only)

### §4. Recomputed miss population (not assumed from subtraction)

All 35 misses re-traced turn-by-turn against the actually-committed FIX-03A
agent (`1e2848e`), not inferred from the prior 38-miss table:

```
Browsing          16
Buying            11
Intent Override    6
Boundary           2
Total              35
```

Rebucketed (A/B/C/D, countable turns only, exactly as `FIX-02-P0`'s
methodology):

| Bucket | Definition | Sessions |
|---|---|---:|
| A | best countable rank ≤ 50 | 15 |
| B | best countable rank 51–100 | 13 |
| C | best countable rank 101–500 | 6 |
| D | not found ≤ 500 | 1 |
| **Total** | | **35** |

By scenario × bucket:

```
boundary/A: 1     boundary/B: 1
browsing/A: 11    browsing/B: 3    browsing/C: 1   browsing/D: 1
buying/A: 3       buying/B: 6      buying/C: 2
intent_override/B: 3              intent_override/C: 3
```

**Intent Override now has zero Bucket-A sessions** — exactly the 3 sessions
FIX-03A rescued (`public_0052, 0071, 0183`) were the only Intent Override
Bucket-A cases in the prior audit; none remain. All 6 remaining Intent
Override misses are Bucket B or C.

**All 15 Bucket-A misses (across all scenarios) now show `term_coverage =
1.0` in every case but one, and `slot_coverage = 1.0` in every case** —
`public_0178` is the sole exception (term_coverage 0.833, slot_coverage
1.0). This means A2's two coverage signals are now **both** saturated for
14/15 of these sessions simultaneously — a doubly-saturated tie, one level
deeper than the single-signal saturation `FIX-02-P0` originally documented.

---

### §5. Deep audit — six remaining Intent Override misses

Full turn-by-turn trace (all 6 sessions, `active_slots`/`slots` before+after,
term/slot coverage, rank at depth 50/100/500) — full data in
`fix04_trace_output.json` (scratch). **The single most important measured
fact**: in every countable turn of all 6 sessions, `term_coverage = 1.0` and
`slot_coverage = 1.0` — both of A2's discrimination signals are maximally
saturated. Neither signal has any room left to help; the reranker has
nothing left to discriminate with **even after FIX-03A**. The bottleneck for
all 6 sessions is now entirely in **candidate generation** (whether the
target enters the Top50 pool at all), not in reranking.

Best countable rank per session, at every depth tested:

| Session | Best countable rank (top 500 depth) | Ever in Top50 (countable)? |
|---|---:|---|
| `public_0002` | 78 | No |
| `public_0038` | 142 | No |
| `public_0096` | 199 | No |
| `public_0144` | 98 | No |
| `public_0177` | 156 | No |
| `public_0198` | 92 | No |

**Classification** (evidence-backed, not forced into a predefined category):

| Session | Classification | Evidence |
|---|---|---|
| `public_0198` | **RETRIEVAL DEPTH** — pure, unrelated to override mechanics | `state.slots["material"]` = `"leather"` both before and after override (identical value, nothing lost); rank stays exactly 92 across every countable turn. The override changes nothing measurable for this session. |
| `public_0002` | **RETRIEVAL DEPTH**, with minor retrieval-evidence structural loss compounding it | `state.slots["material"]`: `"100% Leather"` → `"leather"` (qualifier lost, substance kept); rank 68→78. Already far outside Top50 either way — the loss makes an already-deep miss slightly deeper, not the primary cause. |
| `public_0144` | **RETRIEVAL DEPTH**, with negligible retrieval-evidence loss | Same "100%"-qualifier-loss pattern as `public_0002`; rank 97→98, effectively unchanged — already deep regardless. |
| `public_0038` | **RETRIEVAL DEPTH**, caused by legitimate supersession (not a defect) | The override's new value ("Textile") lands in the *same* bucket as the tracked source ("Lace Slip On Sneaker") — a clean, correct replacement, not a bucket collision. Rank was 27 (inside Top50!) pre-override, falls to not-found post-override — the new 1-word query is simply lexically weaker for this specific target than the old 4-word one. This is a real regression but not the same defect class as the other sessions below. |
| **`public_0096`** | **RETRIEVAL-EVIDENCE STRUCTURAL LOSS** (§6 — see detailed trace) | `state.slots["material"]`: `"95% Polyester, 5% Spandex"` → `"polyester"` at the override turn. Rank 23 (inside Top50!) pre-override → 199 post-override. |
| **`public_0177`** | **RETRIEVAL-EVIDENCE STRUCTURAL LOSS** (§6 — see detailed trace) | `state.slots["material"]`: `"Cotton, Rayon"` → `"cotton"` at the override turn. Rank 8 (inside Top50!) pre-override → 156 post-override. |

No `AMBIGUOUS`, `PARSER LOSS`, `STATE LOSS`, or `EVALUATOR GATING` cases —
`active_slots` (state) is now provably intact for all 6 (both coverage
signals saturated at 1.0), and none of these 6 show a target reaching the
reranked Top10 on any uncountable pre-override turn (checked directly — no
phantom-hit pattern recurs in this specific 6-session set, unlike the
original 9).

---

### §6. Why public_0096 and public_0177 are still insufficient — the exact mechanism

This is the central finding of this audit. **FIX-03A's correction only
modifies `state.active_slots` (the signal A2's reranker uses to reorder an
already-fixed Top50 pool). It deliberately does not touch `state.slots` (the
signal `_build_query()` uses to decide which 50 candidates enter the pool in
the first place) — this separation was explicit, tested (`test_e` in
`FIX-03A`'s own test suite), and intentional.**

Direct trace, `public_0096`, turn-by-turn `state.slots`:

```
turn2 (pre-override, uncountable): slots["material"] = "95% Polyester, 5% Spandex"
                                    -> baseline rank 23 (comfortably in Top50)
turn3 (override fires, countable): slots["material"] = "polyester"
                                    -> baseline rank 199 (nowhere near Top50)
```

Direct trace, `public_0177`, turn-by-turn `state.slots`:

```
turn2 (pre-override, uncountable): slots["material"] = "Cotton, Rayon"
                                    -> baseline rank 8 (comfortably in Top50)
turn4 (override fires, countable): slots["material"] = "cotton"
                                    -> baseline rank 156 (nowhere near Top50)
```

**This is the exact same defect class FIX-03A already fixed — an
unconditional overwrite that destroys previously-disclosed, never-contradicted
evidence when the override's new value lands in an already-populated bucket —
but it exists in `state.slots`, not `state.active_slots`.** FIX-03A's own
`slots[attr] = new_value` line (unchanged, by design — "Retrieval evidence:
unchanged baseline behaviour") still does exactly what `active_slots` used to
do before FIX-03A. Preserving the richer *active-intent* evidence was
necessary but not sufficient: the target never gets a chance to be *reranked*
well if it's never *retrieved* into the pool in the first place, and
retrieval is driven by `state.slots`, which FIX-03A never touched.

**This is not a new hypothesis — it is measured directly**, using the same
before/after state capture methodology `FIX-03A`'s own audit used, applied
this time to `state.slots` instead of `state.active_slots`.

---

### §7. Two known depth-limited override misses — reverified

`public_0002` and `public_0144`, reverified under the committed FIX-03A
agent:

| Session | Top50 | Top100 | Top500 | Best countable rank |
|---|---|---|---|---:|
| `public_0002` | Never | Turns 3–10: rank 78 | same | 78 |
| `public_0144` | Never | Turns 4–10: rank 98 | same | 98 |

**Confirmed retrieval-depth-limited, not state-limited** — both show only
minor retrieval-evidence loss (the "100%" qualifier, substance retained) and
their rank barely moves regardless (68→78, 97→98) — these sessions were
already too deep before the override fired. Reclassifying them as pure
retrieval failures is supported directly by measurement, not assumption.

---

### §8. Non-override misses (29 sessions) — current failure families

Recomputed from §4's rebucketing (35 total − 6 Intent Override = 29):

| Family | Sessions | % of 29 |
|---|---:|---:|
| Bucket A — Top50, doubly-saturated tie (term+slot coverage both 1.0) | 15 | 51.7% |
| Bucket B — rank 51–100 | 10 | 34.5% |
| Bucket C — rank 101–500 | 3 | 10.3% |
| Bucket D — not found ≤ 500 | 1 | 3.4% |

**No parser/query-evidence-weakness or state-related family appears among the
non-override misses** — this was checked directly (term_coverage and
slot_coverage were computed for every Bucket-A session; all but one show
perfect 1.0/1.0). The dominant remaining non-override problem is the same one
`FIX-02-P0`/`FIX-02A0`/`FIX-02A1`/`FIX-02A2` already extensively
characterized and partially addressed: large, doubly-saturated coverage ties
in Bucket A, and raw retrieval depth in B/C/D.

---

### §9. Cross-scenario mechanisms

One clear, general, cross-cutting mechanism was found, already detailed in
§6: **the unconditional-overwrite defect FIX-03A fixed in `active_slots`
has a structurally identical twin in `state.slots`.** This is not a new
signal type or heuristic — it is the *same* code pattern (`dict[key] = value`
with no check for pre-existing, non-contradicted evidence) appearing in two
places, one of which was fixed and one of which was not, because the fixed
one was explicitly scoped to "active intent used for reranking" and the
other was explicitly scoped to "retrieval evidence, unchanged baseline
behaviour" in every prior handover back to B0.

No other recurring structural pattern (same-slot multi-value evidence
*outside* the override path, phrase fragmentation, generic-token domination,
numeric-token dilution, catalog-field placement mismatch) was found with
comparable direct evidence in this pass — the Bucket-A saturation pattern is
already fully characterized by prior work (`FIX-02-P0` §8's document-frequency
findings) and is not re-litigated here.

---

### §10. Rejected families — not retried

Consistent with prior findings, none of the following were revisited:
active-only BM25 blanket tie-break (`FIX-02A0`, REJECTED), boundary-localized
active BM25 (`FIX-02A1`, REJECTED), TF-IDF semantic retrieval (`fix03`,
measured LOW opportunity), plain lexical depth widening (`FIX-02-P0` §7,
weak/unsafe — rescues few, damages existing hits at Top500). No materially
different mechanism was identified in this pass that would justify
reopening any of them.

---

### §11. Best +5 path — estimate from measured evidence only

**Candidate: extend FIX-03A's merge correction to `state.slots`.**

Directly addressable misses, from measured evidence only (not inferred):
`public_0096` (pre-override rank 23, inside Top50) and `public_0177`
(pre-override rank 8, inside Top50) — **2 sessions** where the target was
already comfortably retrievable before the override collapsed the retrieval
query. This is the maximum directly-addressable count from this specific
mechanism in the Intent Override population — `public_0002`/`public_0144`
are too deep even with full evidence retained (rank 68–98, still nowhere
near Top50 even at their *best*, pre-override rank), and `public_0038`'s
weakness is legitimate supersession, not a preservable-evidence case.

**This is explicitly NOT a guarantee of +2 hits.** Preserving the retrieval
evidence would very plausibly restore something close to the pre-override
ranks (23 and 8) for these two sessions' candidate pools, but the actual
post-restoration rank — and whether reranking then lands the target inside
the *scored* Top10 — has not been simulated in this pass. Per governance,
"addressable" is not translated into "guaranteed."

**Whether this mechanism extends beyond these 2 sessions is unknown** —
this pass only traced the 6 Intent Override misses in this depth; whether
the *same* `state.slots` overwrite pattern also silently costs rank on
sessions that are *currently hits* (i.e., whether any of the 165 hits are
riding a lucky retrieval-evidence collapse that happens not to matter) was
not checked in this pass and would need its own safety audit before
implementation, mirroring the rigor `FIX-03A`'s own Part A received.

---

## §12. Parallel MRR-prep dataset (collected, no rerank performed)

For all 165 current hits, at each session's real first countable hit turn
(`mrr_prep_output.json`, scratch, not part of the repo):

```
sessions in Top10 (by construction, since these are hits): 165 / 165
rank == 1:      80 / 165  (48.5%)
rank <= 3:     104 / 165  (63.0%)
rank 8-10:      15 / 165  (9.1%, near the Top10 boundary -- fragile)
average term_coverage (where computable): 0.980
average slot_coverage (where computable): 1.000
perfect term_coverage:                    140 / 159 computable cases
```

This is read-only preparatory data only — no MRR-targeted reranking was
designed, simulated, or implemented in this pass. Reported for a future
Top10-membership-frozen MRR pass to use as a starting dataset, per the
audit's own instruction.

---

## §13. Decision output — ranked opportunity table

| Candidate family | Directly addressable misses (measured) | Evidence strength | Regression risk | Complexity | Recommendation |
|---|---:|---|---|---|---|
| Extend override-correction merge to `state.slots` | 2 (`public_0096`, `public_0177`), unsimulated beyond that | High — exact same defect class already proven safe/effective in `active_slots`; direct before/after trace shows precisely where evidence is lost | Unknown until simulated — must check all 30 Intent Override sessions (not just the 6 misses) for retrieval-pool changes, since this alters candidate generation, not just reranking | Low — same code pattern, one more conditional branch, but touches retrieval (higher-consequence surface than reranking) | **Recommended next simulation** (not implementation) |
| Bucket-A doubly-saturated ties (15 sessions, term+slot coverage both maxed) | Unknown — no new signal identified this pass beyond what `FIX-02-P0`'s IDF hypothesis already proposed and was never simulated | Medium — mechanism well-understood, but no experiment built or tested since that original recommendation | Unknown | Medium | Still open; not re-audited in this pass beyond reconfirming saturation is now double (term+slot) |
| Bucket B/C/D depth (20 sessions total) | 0 rescuable without candidate-pool changes | High (measured repeatedly — `FIX-02-P0` §7's Top100/Top500 counterfactual already showed minimal, regression-prone rescue) | Established unsafe/weak | N/A | Not recommended, per §10 |
| TF-IDF / semantic | 0 (measured) | High | N/A — rejected | N/A | Not recommended, per §10 |

### Recommended next step: simulate (do not implement) extending FIX-03A's merge correction to `state.slots`

**Why this mechanism is next**: it is the most direct, mechanistically-proven
extension of a correction already validated safe and effective — the exact
same defect pattern, now measured in the sibling data structure.

**Why it is general**: it depends only on bucket identity and tracked-source
comparison, applied uniformly to `state.slots` the same way FIX-03A applied
it to `state.active_slots` — no session, ASIN, or scenario-specific logic.

**Why it is more promising than the alternatives measured in this pass**: the
Bucket-A/B/C/D families have no new evidence-backed lever identified this
pass (§10, §11); this one has a direct, quantified, before/after trace
showing exactly where and how much rank is recoverable for at least 2
sessions.

**What could falsify it**: if simulating the extension shows regressions
among the 30 total Intent Override sessions (not just the 6 remaining
misses) — since this changes *candidate generation*, a currently-hit session
could plausibly lose its target from the pool if its own override turn
happens to benefit from the current collapsed-query behavior in some
non-obvious way. This must be checked with the same full-200-session,
zero-regression rigor `FIX-03A`'s own Part A used before any implementation
authorization.

---

## §14. STOP

No production code was edited in Part 2. No experiment was implemented
beyond the already-authorized Part 1 (FIX-03A) commit. Nothing new was
staged or committed. Nothing was pushed. This report, including the exact
`state.slots` collapse trace for `public_0096`/`public_0177` (§6) and the
full 35-session rebucketing (§4/§8), is ready for independent review.
