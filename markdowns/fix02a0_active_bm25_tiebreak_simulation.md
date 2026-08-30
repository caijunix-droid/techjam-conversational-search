# FIX-02A0 — Active-Only BM25 Tie-Break Simulation

Written 2026-08-31. **Offline/external simulation only. No production code touched,
nothing staged, nothing committed.** All numbers below come from executable scripts
run against the live `Agent`/FTS5/BM25 machinery, not estimated. Scripts and full
per-session JSON output live in scratch files (paths in §0), never staged.

---

## 0. Artifacts produced (all outside the repo)

```
/private/tmp/.../scratchpad/fix02a0_simulate.py     -- simulator + experiment + runtime harness
/private/tmp/.../scratchpad/fix02a0_output.json      -- full session-level output, both variants
/private/tmp/.../scratchpad/fix02a0_analyze.py       -- delta/safety/regression analysis
/private/tmp/.../scratchpad/fix02a0_analyze_output.txt
```

`starter/agent.py` and `tests/` are byte-identical to `c30c712` throughout. Nothing
staged or committed at any point in this pass.

---

## 1. Frozen B2 baseline verification

```bash
git rev-parse HEAD                 # c30c712348aa94e42d932ebe49bee7cc966f9fe1
git log -1 --oneline               # c30c712 FIX-01B2: rerank candidates by active-term coverage
git status --short                 # only untracked markdown/research artifacts
shasum -a 256 starter/agent.py     # e3f324caf8e6c940d44293beffd6a71df489f56564639c5af800d70d2975b9b5
python3 -m unittest discover -s tests -p 'test*.py'   # Ran 22 tests — OK
python3 -m evaluator.local_evaluator
```

Reproduced exactly: HR@10 0.805000, MRR 0.499431, MTTC 5.910000, TechnicalScore
0.654129. **B2 reproduced exactly — proceeding.**

---

## 2. Fixed experimental mechanism (as implemented)

Candidate generation, BM25 field weights (`0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0`), and
primary coverage ranking are byte-for-byte identical to production B2 — reused via
the agent's own `_build_query`/`_active_terms` methods, not reimplemented by hand.
Sort key applied to the Top-50 candidate pool:

```python
key = (-coverage(asin), active_only_bm25(asin, default=+inf), baseline_bm25_index(asin))
```

- Tier 1: coverage DESC (identical to B2, unchanged).
- Tier 2 (**new**): active-only BM25 ASC (stronger match first), computed by
  running `products MATCH <active-terms-only OR expression>` with the *same*
  production field weights, restricted to the Top-50 candidate pool. Candidates
  that don't match the active-only expression at all (only possible within a
  0-coverage tied group) get `+inf` and fall through to Tier 3, unchanged from B2.
- Tier 3: original B0/B2 baseline BM25 rank ASC — same as B2's only tie-break.

No candidate depth change, no weight changes, no new tokenizer, no synonyms, no
scenario routing. Exactly one frozen mechanism, run once.

---

## 3. Simulator B2-equivalence check (tiebreak disabled)

Ran the harness with the new tier disabled — must reduce to exactly B2:

```
hit_rate_at_10 = 0.805000   mrr = 0.499431   mttc = 5.910000
efficiency = 0.509000       recommended_technical_score = 0.654129
```

**Matches production exactly, including all 4 scenario breakdowns.** The
simulator is verified equivalent to real B2 before trusting any FIX-02A0 result.

---

## 4. Exact-equivalence check outside ties (§6 of the authorization)

Counted every adjacent pair in every session's reranked output where a
strictly-lower-coverage candidate was placed ahead of a strictly-higher-coverage
one:

```
violations = 0
```

**No violations.** The new tier never reorders across coverage groups — confirmed
mechanically, not merely asserted.

---

## 5. FIX-02A0 overall results — all 200 sessions

| Metric | B2 (frozen) | FIX-02A0 | Δ |
|---|---:|---:|---:|
| HR@10 | 0.805000 | 0.800000 | **−0.005** |
| MRR | 0.499431 | 0.452986 | **−0.046445** |
| MTTC | 5.910000 | 6.205000 | **+0.295** |
| Efficiency | 0.509000 | 0.479500 | **−0.0295** |
| TechnicalScore | 0.654129 | 0.631796 | **−0.022333** |

Scenario breakdown:

| Scenario | B2 HR@10 | A0 HR@10 | B2 MRR | A0 MRR |
|---|---:|---:|---:|---:|
| Boundary | 0.800 | 0.700 | 0.501667 | 0.516667 |
| Browsing | 0.800 | 0.8375 | 0.509142 | 0.451126 |
| Buying | 0.850 | 0.825 | 0.478378 | 0.465997 |
| Intent Override | 0.700 | 0.666667 | 0.528929 | 0.402024 |

**Every top-line metric moves in the wrong direction except Browsing HR@10.**
Intent Override is hit hardest (MRR −24% relative).

---

## 6. Session-level delta analysis (B2 vs FIX-02A0)

```
new hits (miss -> hit):     9
new misses (hit -> miss):  10
rank improvements:         29   (among 151 sessions that stayed hits)
rank regressions:          49   (among 151 sessions that stayed hits)
first-hit-turn improvements: 10
first-hit-turn regressions:  20
fully unchanged sessions:    99
```

**Regressions outnumber improvements on every axis** (rank 49 vs 29, turn 20 vs
10), and the severity is lopsided too — not just the counts:

```
sum of all regression-rank deltas:   173   (avg 3.53 positions worse, max 9)
sum of all improvement-rank deltas:   89   (avg 3.07 positions better, max 8)
```

Total rank degradation is **~2x** total rank improvement. Most strikingly, **9
sessions that were clean rank-1 hits under B2 get thrown to rank 7–10 under
FIX-02A0** (`public_0015`, `public_0033`, `public_0039`, `public_0046`,
`public_0067`, `public_0084`, `public_0123`, `public_0138`, `public_0181` — the
last landing exactly on rank 10, the edge of falling out of the recommendation
list entirely). New hits and new misses are reported in full in §0's output file;
not cherry-picked.

---

## 7. A1-targeted analysis (the 19 sessions this experiment was built for)

```
rescued into Top10:  9 / 19
still misses:        10 / 19
```

| Session | Original A1 pool rank | FIX-02A0 final rank |
|---|---:|---:|
| public_0011 | 10 | 8 |
| public_0012 | 10 | 8 |
| public_0019 | 1 | 8 |
| public_0054 | 3 | 9 |
| public_0081 | 3 | 2 |
| public_0115 | 10 | 2 |
| public_0149 | 5 | 2 |
| public_0170 | 9 | 8 |
| public_0178 | 10 | 9 |

Still-miss: `public_0041`, `public_0052`, `public_0055`, `public_0057`,
`public_0071`, `public_0076`, `public_0137`, `public_0151`, `public_0159`,
`public_0183`.

The hypothesis (active-only BM25 provides real discrimination inside saturated
coverage ties) is **partially confirmed** — the mechanism did rescue roughly half
its target family, and did so without a single coverage-ordering violation. But
6 of the 9 rescues land at rank 8–9, right at the edge of the Top10 boundary —
fragile wins, not comfortable margins. This partial, fragile rescue has to be
weighed against §6's damage to the other 151 previously-hit sessions.

---

## 8. Existing-hit safety analysis (161 B2 hits)

```
hits preserved:  151
hits LOST:        10   -- public_0016, public_0026, public_0035, public_0058,
                          public_0065, public_0074, public_0080, public_0088,
                          public_0100, public_0145
rank improvements among preserved hits: 29
rank regressions among preserved hits:  49   (see §6 for full list and severity)
first-hit-turn improvements: 10
first-hit-turn regressions:  20
```

**10 sessions that were reliable B2 hits become outright misses under
FIX-02A0** — a real, explicit loss, not hidden behind the aggregate HR@10 number
(which itself already shows the net effect: 9 gained − 10 lost = −1 net hit).
Per the acceptance framework's own instruction, this is reported plainly: FIX-02A0
does **not** qualify as successful merely because a handful of A1 sessions were
rescued.

---

## 9. The six previously-known B2 regression sessions

(From `markdowns/fix01b2_term_coverage_end_to_end_simulation.md` §169-192, cross-
verified against that file before use — not taken on faith from the authorization
doc alone.)

| Session | B2 rank/turn | FIX-02A0 rank/turn | Outcome |
|---|---|---|---|
| public_0023 | 10 / turn 5 | 5 / turn 4 | improved |
| public_0093 | 4 / turn 7 | 6 / turn 7 | **further regressed** |
| public_0103 | 8 / turn 4 | 7 / turn 8 | rank improved, but turn regressed (4→8) |
| public_0116 | 6 / turn 1 | 10 / turn 1 | **further regressed — now sits exactly on the Top10 edge** |
| public_0148 | 10 / turn 1 | 6 / turn 7 | rank improved, but turn regressed (1→7) |
| public_0190 | 4 / turn 7 | 2 / turn 9 | rank improved, but turn regressed (7→9) |

Mixed: rank improves in 4/6, but **every single one of the 6 has its first-hit
turn get worse or stay the same, and none improve on both axes simultaneously**
except public_0023. `public_0116`'s regression is the most concerning — it now
sits at rank exactly 10, one BM25 tie away from becoming a new miss.

---

## 10. Intent-override safety — active-only query sourcing

**Code-level guarantee (primary evidence):** `active_terms = agent._active_terms(state)`
is computed **once** per turn and used for **both** the coverage tier **and** the
new active-only BM25 tier (`active_only_expr = " OR ".join(f'"{t}"' for t in active_terms)`
in `fix02a0_simulate.py`) — the exact same list object, not independently re-derived.
Since `_active_terms()` is defined in production `starter/agent.py` to source
*only* `state.active_slots.values()` (never `state.slots`), superseded/historical
terms structurally cannot enter the active-only tie-break query, by construction,
not by runtime luck.

**Concrete runtime trace** (from the prior `FIX-02-P0` audit's `public_0071`
`intent_override` session, reused here as direct evidence since it traces the
exact same `active_terms` variable this experiment consumes):

```
turn 3 (pre-override): active_terms = [pull, closure, 90, cotton, 10, others]
turn 4 (override fires): active_terms = [cotton]   -- superseded terms gone
```

The active-only query at turn 4 is built from `[cotton]` only — the stale
6-term set from turn 3 is absent, confirming superseded historical terms never
leak into the active-only tie-break, consistent with B2's own established
behavior (this experiment changes nothing about *what* counts as active — only
how ties among equally-covering candidates are broken).

---

## 11. Computational cost

3 runs each, full 200-session evaluation, median reported:

| Variant | Run 1 | Run 2 | Run 3 | Median |
|---|---:|---:|---:|---:|
| B2 (simulator) | 76.70s | 82.15s | 79.15s | **79.15s** |
| FIX-02A0 | 112.72s | 111.05s | 107.63s | **111.05s** |

**FIX-02A0 is ~1.40x slower than B2** (which is itself already ~1.6-1.9x slower
than B0 per `MASTER_HANDOVER_ROUND2.md` §3.4/§4). This experiment was not
optimized and no optimization was attempted, per governance — reported as
measurement only. Compounded with B2's existing overhead, this would push total
runtime further from B0's baseline, adding to the already-open, unresolved
runtime concern from prior handovers.

---

## 12. Acceptance classification

Per the authorization's own framework:

**REJECT**, on multiple independent grounds, any one of which is sufficient:

- **Score worsens**: TechnicalScore 0.654129 → 0.631796 (−0.0223), MRR falls
  ~9.3% relative (0.499 → 0.453), HR@10 falls (0.805 → 0.800).
- **Hit losses outweigh benefit**: 10 existing hits lost vs. 9 misses rescued —
  a net loss, not a net gain, and this shows up directly in the aggregate HR@10
  drop.
- **Large regression profile reappears**: 49 rank regressions vs. 29
  improvements, with regression severity (173 total rank-positions lost) nearly
  double improvement severity (89 total rank-positions gained); 9 previously
  clean rank-1 sessions pushed to rank 7-10; the runtime cost grows a further
  ~1.40x on top of B2's already-flagged overhead.

The rescue of 9/19 targeted A1 sessions (§7) is real and mechanistically
consistent with the FIX-02-P0 hypothesis — active-only BM25 does contain some
genuine discriminating signal inside saturated coverage ties, and 0 coverage-
ordering violations confirms the implementation itself is correct, not buggy.
But the same undifferentiated BM25 signal that helps some ties also reorders
many *other* already-correct rankings for the worse, because it's applied
uniformly to every tie group regardless of whether that group actually needs
rescuing. **The mechanism as specified (raw active-only BM25, no threshold, no
selectivity awareness) is not safe to adopt.**

---

## 13. Anti-overfitting note

All numbers reported are aggregate, catalog-wide statistics from one frozen,
general mechanism run identically across all 200 sessions — no session-specific
or ASIN-specific logic was introduced or considered.

---

## STOP

FIX-02A0 was **not** implemented in `starter/agent.py`. Tests were not modified.
Nothing was staged, committed, or pushed. This report is ready for independent
review. Given the REJECT classification, the natural next step (not authorized by
this pass) would be revisiting `FIX-02-P0`'s original IDF/information-aware
coverage recommendation instead — a mechanism that discriminates *before*
scoring based on term rarity, rather than this experiment's approach of applying
undifferentiated BM25 uniformly across every tie group regardless of need.
