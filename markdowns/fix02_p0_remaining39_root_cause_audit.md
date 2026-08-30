# FIX-02-P0 — Remaining-39 Miss Root-Cause Audit

Written 2026-08-31. **Diagnostic pass only. No production code touched, nothing
staged, nothing committed.** All commands were run for real against the frozen B2
baseline; every count below comes from executable scripts, not from reading the code
and guessing. Scripts and full per-turn JSON evidence live in scratch files (paths in
§0) for independent re-verification — they are **not** part of this repo and were never
staged.

---

## 0. Artifacts produced (all outside the repo, per governance)

```
/private/tmp/.../scratchpad/trace_misses.py            -- turn-by-turn tracer for the 39 misses
/private/tmp/.../scratchpad/trace_misses_output.json    -- full per-turn trace, all 39 sessions
/private/tmp/.../scratchpad/classify_misses.py           -- primary/secondary bucket classifier
/private/tmp/.../scratchpad/classified_misses.json       -- one row per miss, all fields below
/private/tmp/.../scratchpad/counterfactual_depth.py       -- frozen-mechanism depth sweep (50/100/500)
/private/tmp/.../scratchpad/counterfactual_depth_output.json
/private/tmp/.../scratchpad/diff_depth.py                 -- rescue/regression diff across depths
/private/tmp/.../scratchpad/section8_quality.py           -- active-term coverage quality audit
/private/tmp/.../scratchpad/section8_detail.json
/private/tmp/.../scratchpad/term_doc_freq.py               -- catalog document-frequency of active terms
```

None of these were staged or committed. `starter/agent.py`, `tests/`, ranking logic,
query construction, candidate depth, and BM25 weights are byte-identical to `c30c712`
throughout this entire pass.

---

## 1. Frozen baseline verification

```bash
git rev-parse HEAD                 # c30c712348aa94e42d932ebe49bee7cc966f9fe1
git log -1 --oneline               # c30c712 FIX-01B2: rerank candidates by active-term coverage
git status --short                 # only untracked markdown/research artifacts
shasum -a 256 starter/agent.py     # e3f324caf8e6c940d44293beffd6a71df489f56564639c5af800d70d2975b9b5
python3 -m unittest discover -s tests -p 'test*.py'   # Ran 22 tests — OK
python3 -m evaluator.local_evaluator
```

Reproduced exactly:

```
hit_rate_at_10              = 0.805000
mrr                         = 0.499431
mttc                        = 5.910000
efficiency                  = 0.509000
recommended_technical_score = 0.654129
sample_count                = 200
```

**B2 reproduced exactly. Proceeding to audit this exact baseline — no substitution.**

---

## 2. The exact 39 misses

From `results.json`'s per-session `hit` field (real evaluator output, not simulated):

```
total sessions = 200
misses         = 39   (confirmed by direct count, matches audit's expected 39)
```

Scenario breakdown:

| Scenario | Misses |
|---|---:|
| Browsing | 16 |
| Buying | 12 |
| Intent Override | 9 |
| Boundary | 2 |
| **Total** | **39** |

All 39 sample IDs, target ASINs, and full conversations were re-run turn-by-turn
against the live `Agent` instance (real FTS5 index, real BM25, real
`_active_terms`/`_build_query`/coverage sort) — not approximated in Python. The
tracer asserts each of the 39 remains a miss under re-simulation; all 39 assertions
passed, confirming the trace faithfully reproduces production behavior session-for-session.

---

## 3. Methodology note — the "countable turn" correction

Section 1's baseline classification initially (first pass) considered every turn's
best BM25 rank, including turns where `override_applied == False`. Re-inspection of
`evaluator/local_evaluator.py`'s hit check —

```python
if override_applied and target in ranked:
    hit_turn = turn
```

— shows that for `intent_override` sessions, **no turn before the scripted override
(turn 3 or 4) can ever register as a hit, regardless of rank.** A target ranked #1
on turn 2 of an `intent_override` session does not count. This is a real mechanism in
the evaluator's protocol, verified directly in its source, not assumed. All
classification below uses **only turns where `override_applied == True`** ("countable
turns") to determine each session's best achievable rank and reranked position — this
changed 3 sessions' bucket assignment from the naive (all-turns) version. The naive
version is preserved as a cross-check but not used as the reported classification.

Separately, and orthogonally, **4 of the 9 `intent_override` misses did reach the
reranked Top 10 on an uncountable pre-override turn** — see §9.

---

## 4. Primary structural classification (A/B/C/D)

Definitions applied exactly as specified, using **countable turns only**:

| Primary bucket | Definition | Sessions | % of 39 |
|---|---|---:|---:|
| **A** — Top50 baseline, reranker can't lift into Top10 | best countable BM25 rank ≤ 50 | **19** | 48.7% |
| **B** — never Top50, reaches 51–100 | best countable BM25 rank 51–100 | **13** | 33.3% |
| **C** — best rank 101–500 | best countable BM25 rank 101–500 | **6** | 15.4% |
| **D** — never in Top500 | not found within Top500 on any countable turn | **1** | 2.6% |
| **Total** | | **39** | 100% |

`A + B + C + D = 19 + 13 + 6 + 1 = 39` — reconciles exactly.

### A subtypes (all 19 A-bucket misses)

At each session's best countable in-pool turn:

| Subtype | Rule applied | Sessions |
|---|---|---:|
| **A1 — coverage tie** | equal-coverage candidates ahead (`equal_ahead`) exceed strictly-higher-coverage candidates ahead (`higher_ahead`) | **19** |
| **A2 — coverage deficit** | `higher_ahead ≥ 10` alone would exceed Top10, OR `higher_ahead > equal_ahead` and `higher_ahead > 0` | **0** |
| **A3 — no active signal** | zero active terms at the relevant turn | **0** |

**All 19 A-bucket misses are A1.** Zero are A2, zero are A3. This is a real,
measured result, not a default — see the per-session table in §11: `higher_ahead`
is 0 in 17/19 cases and only 3 or 7 (never ≥10) in the remaining 2. Coverage
*deficit* essentially never explains a miss on its own in this dataset; when a
target has any deficit at all, it's always small and it's the **tie-break among
equal-coverage competitors** that dominates.

Tie-break rule used to split A1 vs A2 when both `higher_ahead>0` and
`equal_ahead>0` (occurred twice, public_0149 and public_0178): whichever count is
larger is the dominant driver; both are still tagged with secondary T1+T2 so the
partial-deficit evidence isn't hidden. Full counts are in §6 and §11 — nothing here
depends on the tie-break rule changing the primary distribution meaningfully (worst
case, both would still classify as A1 by rank-order comparison; see §6 detail).

---

## 5. Secondary diagnostic tags

| Tag | Meaning | Count |
|---|---|---:|
| T1 — coverage tie | target coverage == many competitors' coverage | 19 |
| T2 — coverage deficit (co-occurring) | target has *some* strictly-higher-coverage competitors ahead, even where tie dominates | 2 |
| T3 — active-term extraction weakness | not observed as a distinct driver in this batch (see §9 — parsing correctly captured evidence in the overwhelming majority) | 0 |
| T4 — superseded/historical query noise | not the mechanism found — see §9's distinct override finding, which is the *opposite* effect | 0 |
| T5 — category/profile noise | not evidenced as a distinct driver | 0 |
| T6 — literal vocabulary mismatch (hypothesis) | plausible contributor for the 3 partial-coverage cases (public_0020, public_0149, public_0178) but not quantitatively demonstrated beyond the coverage fraction itself; flagged as hypothesis only, not claimed | 3 (hypothesis) |
| T7 — hard/numeric constraint not represented | not observed in this batch | 0 |
| T8 — other (precisely explained) | **override-driven active-term collapse** (§9) + **override-gate phantom hits** (§9) | 4 sessions |

---

## 6. Coverage-tie audit (all 19 A-bucket misses)

| Session | Scenario | Baseline rank | B2 pool rank | Target coverage | Higher-coverage ahead | Equal-coverage ahead |
|---|---|---:|---:|---:|---:|---:|
| public_0011 | browsing | 20 | 13 | 1.000 | 0 | 12 |
| public_0012 | browsing | 21 | 17 | 1.000 | 0 | 16 |
| public_0019 | browsing | 23 | 23 | 1.000 | 0 | 22 |
| public_0041 | boundary | 14 | 11 | 1.000 | 0 | 10 |
| public_0052 | intent_override | 40 | 34 | 1.000 | 0 | 33 |
| public_0054 | buying | 38 | 22 | 1.000 | 0 | 21 |
| public_0055 | browsing | 15 | 15 | 1.000 | 0 | 14 |
| public_0057 | browsing | 20 | 16 | 1.000 | 0 | 15 |
| public_0071 | intent_override | 44 | 33 | 1.000 | 0 | 32 |
| public_0076 | browsing | 17 | 17 | 1.000 | 0 | 16 |
| public_0081 | browsing | 15 | 13 | 1.000 | 0 | 12 |
| public_0115 | browsing | 18 | 11 | 1.000 | 0 | 10 |
| public_0137 | browsing | 27 | 19 | 1.000 | 0 | 18 |
| public_0149 | buying | 44 | 13 | 0.667 | 3 | 9 |
| public_0151 | browsing | 31 | 15 | 1.000 | 0 | 14 |
| public_0159 | buying | 15 | 11 | 1.000 | 0 | 10 |
| public_0170 | browsing | 17 | 13 | 1.000 | 0 | 12 |
| public_0178 | buying | 15 | 16 | 0.833 | 7 | 8 |
| public_0183 | intent_override | 15 | 14 | 1.000 | 0 | 13 |

**Aggregate: 19/39 (48.7%) of all remaining misses are primarily blocked by
equal-coverage ties**, not by a lack of coverage. In 17/19 cases the target has
**zero** higher-coverage competitors ahead of it — the entire blockage is the
BM25 tie-break ordering among a large group that all scored the maximum
possible coverage. This tells us directly: B2's next weakness is **what happens
after coverage ties**, not coverage itself as a signal (coverage is doing its job —
the problem is it saturates at 1.0 too often to still discriminate; quantified in §8).

---

## 7. Fixed counterfactual depth audit (Top100 / Top500)

Simulated the **exact frozen B2 mechanism** (same query, same BM25 weights, same
coverage formula, same tie-break — verified identical to production by first
reproducing depth=50's 0.805/161-hits exactly) with only `internal_depth` swept
externally. Production `starter/agent.py` was never modified; this used a
standalone script that calls the agent's own `_build_query`/`_active_terms`
methods, not a hand reimplementation.

**Against the 39 misses:**

| Depth | Rescued (miss→hit) | Still failing |
|---|---:|---:|
| Top100 | 3 / 39 | 36 / 39 |
| Top500 | 3 / 39 (same 3 — zero incremental over Top100) | 36 / 39 |

All 3 rescues (public_0028, public_0092, public_0198) are Bucket-B sessions whose
raw baseline rank was 87–92 — i.e. just barely inside a widened pool. **10 of the
13 Bucket-B misses (raw rank 51–100) were *not* rescued even once their raw rank
was well inside the Top100 pool.** This means candidate-pool depth is not merely
insufficient for these — even after entering the pool, the same
coverage-saturation tie problem from §6/§8 reproduces at the wider scale. This
was not separately re-traced turn-by-turn at depth 100/500 for those 10 sessions
(scope discipline — flagged here as a real, acknowledged gap rather than silently
assumed away). The counterfactual result is enough to rule out "depth alone" as
the dominant lever; it is not enough to fully characterize the wider-pool tie
mechanism for those specific 10 sessions.

**Against the 161 existing hits:**

| Depth | Rank regressions | Hits lost | Rank improvements |
|---|---:|---:|---:|
| Top100 | 4 | 0 | 0 |
| Top500 | 2 (different sessions) | **3** | 1 |

At Top500, the 3 sessions that regressed at Top100 (public_0040, public_0103,
public_0145, ranks 8→9, 8→9, 7→9 at Top100) degrade far enough to **fall out of
the Top10 entirely** (become misses) at Top500. Net hit count at Top500 is 161 —
identical to the Top50 baseline — but this is **not a wash**: it is 3 *different*
sessions lost for 3 *different* sessions gained, i.e. real churn hidden behind an
unchanged aggregate number. Per the audit's own instruction, this regression is
reported plainly rather than hidden behind the flat topline count.

**Conclusion: increasing candidate-pool depth is not a safe or effective lever on
its own.** It rescues a small, near-boundary subset (3/39) at Top100 with modest,
contained regression (4 rank drops, 0 losses), and produces zero *additional*
benefit at Top500 while introducing real hit losses. This directly narrows the next
experiment away from "just widen the pool."

---

## 8. Active-term quality audit — the central finding

For each of the 39 misses, at its most relevant countable turn:

```
target perfect coverage (== 1.000):  36 / 39
target partial coverage (0 < x < 1): 3 / 39   (public_0020: 0.889, public_0149: 0.667, public_0178: 0.833)
target zero coverage:                0 / 39

average target coverage:                          0.984
average Top10-after-rerank competitor coverage:    0.978   (pooled across all 390 Top10 slots, 39 sessions x 10)
```

**36 of 39 misses (92%) have a target that perfectly matches every one of its own
active terms, and its Top10 competitors average within 0.006 of the same score.**
This directly answers the audit's central diagnostic question from §8's framing:
the failure is **not** "the target doesn't contain the current terms" — it
overwhelmingly does. The failure is **"too many other products contain the same
terms."**

### Why: the active terms are catalog-wide boilerplate, not discriminating attributes

Document frequency of the terms actually driving these ties, measured directly
against the 50,000-item catalog (not estimated):

| Term | Used in N misses | Catalog doc frequency | % of catalog |
|---|---:|---:|---:|
| closure | 15 | 19,303 | 38.6% |
| 100 (as in "100%") | 9 | 17,396 | 34.8% |
| wash | 6 | 16,133 | 32.3% |
| machine | 4 | 10,952 | 21.9% |
| polyester | 16 | 10,884 | 21.8% |
| cotton | 12 | 9,775 | 19.6% |
| color | 5 | 9,366 | 18.7% |
| hand | 2 | 9,285 | 18.6% |
| pull | 5 | 8,321 | 16.6% |
| black | 3 | 8,222 | 16.4% |
| leather | 6 | 7,503 | 15.0% |
| spandex | 6 | 5,615 | 11.2% |
| measures | 4 | 5,191 | 10.4% |
| button | 3 | 4,149 | 8.3% |
| approximately | 4 | 4,804 | 9.6% |
| arch | 4 | 2,530 | 5.1% |
| shaft | 4 | 2,055 | 4.1% |
| rayon | 2 | 1,264 | 2.5% |
| undershirts | 1 | 80 | 0.2% |

**The unweighted coverage formula treats "closure" (38.6% of the entire catalog)
identically to "undershirts" (0.2% of the catalog) — a single boolean
match/no-match with no frequency weighting.** Fabric composition words
("cotton"/"polyester"/"spandex"/"rayon"), care instructions
("wash"/"hand"/"machine"), and generic construction words ("closure"/"pull"/
"button") dominate the active-term sets extracted from this clothing catalog's
own boilerplate product text (features/details fields), and because they're near-
universal, coverage saturates at or near 1.0 for large numbers of unrelated
products, leaving the rarer, genuinely discriminating terms ("arch", "shaft",
"undershirts", "heathers") diluted into an unweighted average alongside them.
This is the single quantified mechanism behind §4's A1-dominant result and §7's
"depth doesn't help" result — widening the pool just pulls in more products that
also score high on the same boilerplate terms.

---

## 9. State/query findings

**Parsing correctly represents customer evidence in the overwhelming majority of
misses** — 36/39 show perfect target coverage, meaning `active_slots` accurately
captured what the customer said and the target's own catalog text was correctly
matched against it. This rules out "parser/state failure" as a driver for
`this batch of 39`; the problem is architecturally in ranking/discrimination, not
evidence capture. (Section 3.2's prior audit already established, on the *hit* side,
that targets structurally tend to match their own active intent — this batch shows
the parsing side of that same mechanism holding for misses too.)

Two distinct, code-traced findings that don't fit any T1–T7 tag, reported under T8:

### 9.1 — Override-driven active-term collapse (real mechanism, traced to exact code)

Example: **public_0071** (`intent_override`), traced turn-by-turn:

```
turn 2: active_terms = [pull, closure, 90, cotton, 10, others]   pool_rank = 1  (in-pool, but pre-override -- uncountable)
turn 3: active_terms = [pull, closure, 90, cotton, 10, others]   pool_rank = 1  (same, still uncountable)
turn 4: OVERRIDE FIRES.  active_terms = [cotton]                  pool_rank = 38 (countable -- and this is now a miss)
```

Traced to `starter/agent.py`'s override-handling block (lines ~188-210): the
initial turn-1 remainder ("Pull On") gets filed under `override_source_attr =
"feature"`. The override then (a) deletes `active_slots["feature"]` because it's
still unchanged, **and** (b) the new override value re-classifies into the
**same** `"material"` bucket that already held the richer `"90% Cotton, 10%
Others"` string, **overwriting** it with just `"cotton"`. Net effect: active terms
drop from 6 to 1 in a single turn, and the one surviving term ("cotton") is the
single highest-document-frequency fabric word in the whole audit (19.6% of the
catalog, §8) — a coverage signal with almost no remaining discriminating power.
This is not "stale terms hurting retrieval" (T4); it's the opposite —
**terms disappearing on override**, verified by direct code trace, not inferred
from statistics alone. This mechanism plausibly generalizes to other
`intent_override` misses (public_0052 and public_0183 show the identical
6-or-more-terms → 1-term collapse pattern at their override turn) but was traced
exactly for public_0071 only; the other two are pattern-matched, not
independently code-traced line-by-line in this pass.

### 9.2 — Override-gate phantom hits (evaluator protocol characteristic, not an agent bug)

4 of the 9 `intent_override` misses reached the reranked **Top 10** on an
uncountable pre-override turn — a real rank achieved by the real reranker, that
can never register as a hit under the evaluator's `override_applied` gate:

| Session | Phantom-hit turns | Ranks achieved | Final bucket |
|---|---|---|---|
| public_0052 | 2 | 3 | A |
| public_0071 | 2, 3 | 1, 1 | A |
| public_0177 | 2, 3 | 7, 7 | C |
| public_0183 | 2, 3 | 8, 8 | A |

This is **44% of all `intent_override` misses**. It is not a ranking defect (the
reranker is doing exactly what it should — the target scores well pre-override) —
it's a structural characteristic of how the evaluator scripts and scores intent
override scenarios. Reported here because it materially explains why
`intent_override` shows the lowest scenario HR@10 (0.70, per `MASTER_HANDOVER_ROUND2.md`
§1) despite the target often being trivially findable moments before the override.
Any future work on `intent_override` specifically should account for both 9.1 (the
real collapse that hurts the post-override turns) and 9.2 (the gate itself, which
no ranking change can address).

---

## 10. Required summary table

| Primary failure | Sessions | % of 39 | Potential next direction |
|---|---:|---:|---|
| A1 Coverage tie | 19 | 48.7% | IDF/information-aware coverage weighting (§8 provides direct doc-frequency evidence) |
| A2 Coverage deficit | 0 | 0% | n/a — not observed as a standalone driver in this batch |
| A3 No active signal | 0 | 0% | n/a — not observed in this batch |
| B Rank 51–100 | 13 | 33.3% | Not simply candidate depth (§7: only 3/13 rescued at Top100, 0 more at Top500); likely same coverage-saturation mechanism at wider scale — not yet independently confirmed for the other 10 |
| C Rank 101–500 | 6 | 15.4% | Deeper retrieval improvement; not evidenced as coverage-tie-driven the same way (raw BM25 rank itself is the limiter here) |
| D >500 / absent | 1 | 2.6% | Semantic/hybrid retrieval; single session, low priority by volume |

---

## 11. Full 39-session table

`Baseline rank` = best countable-turn BM25 rank (extended to depth 500).
`B2 pool rank` = target's position in the reranked Top50 pool at that turn (blank
if target never entered the Top50 baseline pool on any countable turn).
`Coverage` = target's active-term coverage fraction at that turn.

| Session | Scenario | Baseline Rank | B2 Pool Rank | Coverage | Primary Bucket | Secondary Tags |
|---|---|---:|---:|---:|---|---|
| public_0002 | intent_override | 78 | — | 1.000 | B | — |
| public_0011 | browsing | 20 | 13 | 1.000 | A1 | T1 |
| public_0012 | browsing | 21 | 17 | 1.000 | A1 | T1 |
| public_0019 | browsing | 23 | 23 | 1.000 | A1 | T1 |
| public_0020 | buying | 278 | — | 0.889 | C | T6 (hypothesis) |
| public_0028 | buying | 92 | — | 1.000 | B | — |
| public_0038 | intent_override | 142 | — | 1.000 | C | — |
| public_0041 | boundary | 14 | 11 | 1.000 | A1 | T1 |
| public_0052 | intent_override | 40 | 34 | 1.000 | A1 | T1, T8 (phantom hit + collapse pattern) |
| public_0054 | buying | 38 | 22 | 1.000 | A1 | T1 |
| public_0055 | browsing | 15 | 15 | 1.000 | A1 | T1 |
| public_0057 | browsing | 20 | 16 | 1.000 | A1 | T1 |
| public_0071 | intent_override | 44 | 33 | 1.000 | A1 | T1, T8 (phantom hit + collapse, code-traced) |
| public_0073 | browsing | — (>500) | — | 1.000 | D | — |
| public_0076 | browsing | 17 | 17 | 1.000 | A1 | T1 |
| public_0081 | browsing | 15 | 13 | 1.000 | A1 | T1 |
| public_0083 | buying | 73 | — | 1.000 | B | — |
| public_0087 | browsing | 98 | — | 1.000 | B | — |
| public_0092 | browsing | 87 | — | 1.000 | B | — |
| public_0096 | intent_override | 199 | — | 1.000 | C | — |
| public_0109 | buying | 415 | — | 1.000 | C | — |
| public_0115 | browsing | 18 | 11 | 1.000 | A1 | T1 |
| public_0126 | browsing | 51 | — | 1.000 | B | — |
| public_0137 | browsing | 27 | 19 | 1.000 | A1 | T1 |
| public_0144 | intent_override | 98 | — | 1.000 | B | — |
| public_0149 | buying | 44 | 13 | 0.667 | A1 | T1, T2 |
| public_0151 | browsing | 31 | 15 | 1.000 | A1 | T1 |
| public_0159 | buying | 15 | 11 | 1.000 | A1 | T1 |
| public_0161 | buying | 56 | — | 1.000 | B | — |
| public_0170 | browsing | 17 | 13 | 1.000 | A1 | T1 |
| public_0174 | buying | 87 | — | 1.000 | B | — |
| public_0175 | browsing | 130 | — | 1.000 | C | — |
| public_0177 | intent_override | 156 | — | 1.000 | C | T8 (phantom hit) |
| public_0178 | buying | 15 | 16 | 0.833 | A1 | T1, T2 |
| public_0179 | buying | 51 | — | 1.000 | B | — |
| public_0183 | intent_override | 15 | 14 | 1.000 | A1 | T1, T8 (phantom hit + collapse pattern) |
| public_0187 | boundary | 63 | — | 1.000 | B | — |
| public_0194 | buying | 66 | — | 1.000 | B | — |
| public_0198 | intent_override | 92 | — | 1.000 | B | — |

---

## 12. Next-experiment selection

**Largest recoverable, evidence-supported failure family: A1 coverage ties (19/39,
48.7% of all remaining misses), directly caused by unweighted active-term coverage
saturating on catalog-wide boilerplate vocabulary (§8, with measured document
frequencies).**

### Recommended experiment: IDF/information-aware active-term coverage

**Hypothesis:** replacing the unweighted `matched/total` coverage fraction with an
IDF-weighted (or simple inverse-document-frequency-thresholded) coverage score
would let genuinely rare, discriminating active terms (e.g. "undershirts" at
0.2% catalog frequency, "arch"/"shaft" at ~4-5%) outweigh universal boilerplate
terms (e.g. "closure" at 38.6%, "100"/"wash" at 32-35%) that currently contribute
equally to every candidate's score.

**Exact sessions/failure family targeted:** the 19 A1 sessions in §6/§11, and
plausibly a meaningful fraction of the 10 not-yet-independently-confirmed Bucket-B
sessions from §7 that share the same near-1.0 coverage pattern (not proven, flagged
as upside uncertain until traced).

**Fixed mechanism (proposed, NOT implemented):** weight each active term's
contribution to coverage by its inverse document frequency in the catalog (already
computable — `agent.connection` can answer per-term `MATCH` counts as done in
§8's `term_doc_freq.py`), instead of counting every matched term equally.

**Expected upside ceiling from audit evidence:** up to 19/39 sessions (the full A1
set) *could* plausibly be affected, since all 19 currently tie at maximum coverage
with large groups of competitors who would very likely differentiate under an
IDF-aware score — but the audit did not simulate this mechanism, so this is a
ceiling from the failure-family size, not a measured rescue count.

**Known regression risk:** genuinely uncertain without implementation — this
audit did **not** simulate an IDF-weighted variant, per its diagnostic-only
scope. §3.4 of `MASTER_HANDOVER_ROUND2.md` already shows this project's
established discipline of proving safety empirically before adoption (raw
active-only BM25 was rejected for destroying 28-42/146 existing hits despite
looking promising on paper) — the same rigor must apply here before any
IDF-weighted variant is adopted.

**What metrics must remain protected:** all 161 existing hits (per this project's
own established regression bar), and the 6 already-known rank-regression sessions
from B2's original implementation (`MASTER_HANDOVER_ROUND2.md` §3.4) should not
silently worsen further.

**DO NOT IMPLEMENT. This audit recommends only; it authorizes nothing.**

---

## 13. Anti-overfitting note

All counts above are aggregate statistics and quantified mechanisms (document
frequency, coverage fractions, ahead-counts), not session-specific or
ASIN-specific rules. The recommended experiment (IDF weighting) is a general
catalog-wide reweighting, not tuned to these 39 sessions' specific wording or
targets — it would apply identically to any session regardless of which product
or customer language appears, which is the intended generality bar per this
section's requirement.

---

## 14. Final classification

```
B2 baseline reproduced:            YES, exactly
exact miss count:                  39 / 200, confirmed
scenario breakdown:                Browsing 16, Buying 12, Intent Override 9, Boundary 2
primary failure distribution:      A1=19, A2=0, A3=0, B=13, C=6, D=1  (reconciles to 39)
secondary-tag distribution:        T1=19, T2=2, T8=4 (override-related, code-traced)
full 39-session table:             §11, complete, no cherry-picking
coverage-tie analysis:             §6 -- 19/39 primarily blocked by ties, 17/19 with zero deficit contribution
Top100/Top500 counterfactual:      §7 -- only 3/39 rescued at either depth, 0 incremental at 500,
                                    3 existing hits actively lost at 500 (real churn behind flat count)
active-term quality analysis:      §8 -- 36/39 perfect target coverage, competitors average 0.978;
                                    boilerplate terms measured at 15-39% catalog document frequency
state/query findings:              §9 -- parsing correct in the overwhelming majority; two distinct,
                                    code-traced override-related mechanisms found and separated from
                                    the T1-T7 taxonomy
largest recoverable failure family: A1 coverage ties, 19/39 (48.7%)
recommended next experiment:        IDF/information-aware active-term coverage (§12) -- NOT implemented
```

## SUFFICIENT TO AUTHORIZE NEXT EXPERIMENT

The evidence is quantitative, code-traced (not merely statistical) for the central
mechanism (§8's document-frequency measurement directly explains §4/§6's tie-
dominant result), and the counterfactual in §7 independently rules out the most
obvious alternative lever (candidate depth) with real numbers rather than
assumption. The two override-specific findings in §9 are flagged as real but
architecturally separate from the ranking-mechanism question this audit was
scoped to, and should not be conflated with the IDF-coverage recommendation when
that next experiment is scoped.

---

## STOP

No production code was edited. No experiment was implemented. Nothing was staged
or committed. This report is ready for independent review.
