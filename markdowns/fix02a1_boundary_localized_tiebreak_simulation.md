# FIX-02A1 — Top10-Boundary-Localized Active-Only BM25 Tie-Break Simulation

Written 2026-08-31. **Offline/external simulation only. No production code touched,
nothing staged, nothing committed.** All numbers come from executable scripts run
against the live `Agent`/FTS5/BM25 machinery. Scripts and full session-level output
live in scratch files (paths in §0), never staged.

---

## 0. Artifacts produced (all outside the repo)

```
/private/tmp/.../scratchpad/fix02a1_simulate.py      -- simulator + experiment harness
/private/tmp/.../scratchpad/fix02a1_output.json       -- full session-level output, both variants
/private/tmp/.../scratchpad/fix02a1_analyze.py        -- delta/safety/regression analysis
/private/tmp/.../scratchpad/fix02a1_analyze_output.txt
/private/tmp/.../scratchpad/check_group_spans.py      -- direct mechanism check (§8)
```

`starter/agent.py` and `tests/` byte-identical to `c30c712` throughout.

---

## 1. Frozen B2 baseline verification

```bash
git rev-parse HEAD                 # c30c712348aa94e42d932ebe49bee7cc966f9fe1
git status --short                 # only untracked markdown/research artifacts
shasum -a 256 starter/agent.py     # e3f324caf8e6c940d44293beffd6a71df489f56564639c5af800d70d2975b9b5
python3 -m unittest discover -s tests -p 'test*.py'   # Ran 22 tests — OK
```

Simulator's own B2-equivalence run (step 2 of governance): reproduced exactly —
HR@10 0.805000, MRR 0.499431, MTTC 5.910000, TechnicalScore 0.654129, all 4
scenario breakdowns match. **Proceeding.**

---

## 2. Fixed mechanism (as implemented)

Candidate generation and primary coverage ranking identical to B2 (reused via
`_build_query`/`_active_terms`, not reimplemented). B2's own tie-broken order is
computed first (`b2_order`), then partitioned into contiguous equal-coverage
groups. The **single group whose position range straddles the Top-10 boundary**
(contains both a position ≤10 and a position ≥11) gets active-only BM25
re-ordering internally; every other group is left as an untouched slice of
`b2_order`:

```python
final_order = b2_order[:start] + reordered(straddling_members) + b2_order[end:]
```

If no group straddles the boundary (e.g., fewer than 10 candidates, or the
boundary falls exactly on a group edge), `final_order == b2_order` — reduces to
B2 exactly for that turn. Same production BM25 weights, same tokenizer, no
depth change, no scenario routing — one frozen mechanism, run once.

---

## 3. Safety checks (§10 of the authorization)

```
boundary_violations = 0   -- every candidate outside the straddling group verified,
                             per turn, to retain its exact B2 relative-order slice
coverage_violations = 0   -- no lower-coverage candidate ever placed above a
                             higher-coverage one, anywhere in the output
```

Both required at 0; both measured at 0, mechanically checked every turn, not
asserted from the construction alone.

---

## 4. FIX-02A1 overall results — all 200 sessions

| Metric | B2 (frozen) | FIX-02A1 | Δ |
|---|---:|---:|---:|
| HR@10 | 0.805000 | 0.800000 | **−0.005** |
| MRR | 0.499431 | 0.501232 | **+0.001801** |
| MTTC | 5.910000 | 6.205000 | **+0.295** |
| Efficiency | 0.509000 | 0.479500 | **−0.0295** |
| TechnicalScore | 0.654129 | 0.646270 | **−0.007859** |

Scenario breakdown:

| Scenario | B2 HR@10 | A1 HR@10 | B2 MRR | A1 MRR |
|---|---:|---:|---:|---:|
| Boundary | 0.800 | 0.700 | 0.501667 | 0.491667 |
| Browsing | 0.800 | 0.8375 | 0.509142 | 0.513626 |
| Buying | 0.850 | 0.825 | 0.478378 | 0.513814 |
| Intent Override | 0.700 | 0.666667 | 0.528929 | 0.437817 |

**MRR improved slightly overall** (unlike A0's collapse), and Buying/Browsing MRR
both improved meaningfully. But HR@10 and MTTC show the **exact same regression**
as A0, and TechnicalScore is still net negative.

---

## 5. Session-level delta analysis (B2 vs FIX-02A1)

```
new hits (miss -> hit):     9
new misses (hit -> miss):  10
rank improvements:         26   (vs A0's 29)
rank regressions:          30   (vs A0's 49)
first-hit-turn improvements: 10   (identical list to A0)
first-hit-turn regressions:  20   (identical list to A0)
fully unchanged sessions:  120   (vs A0's 99)
```

Localization meaningfully **reduced total reordering churn** — 56 sessions
touched by rank change vs. A0's 78 — and reduced regression severity:

```
sum of regression rank deltas: 122   (avg 4.07, max 9)   -- A0 was 173 (avg 3.53, max 9)
sum of improvement rank deltas: 98   (avg 3.77, max 8)   -- A0 was 89 (avg 3.07, max 8)
```

Regression-to-improvement severity ratio improved from ~1.94x (A0) to ~1.24x
(A1) — a real, measured reduction in collateral damage, not just fewer sessions
touched.

**The new-hits and new-misses sets are identical, session-for-session, to A0's**
(§7-8) — the localization did not change which sessions win or lose, only how
much unrelated collateral churn happens elsewhere. This is explained mechanically
in §8, not left as an unexplained coincidence.

---

## 6. A1-targeted analysis (19 original coverage-tie misses)

```
rescued into Top10:  9 / 19   -- identical session set to A0
still misses:        10 / 19  -- identical session set to A0
```

Same 9 sessions rescued at the same final ranks as A0 (`public_0011`→8,
`public_0012`→8, `public_0019`→8, `public_0054`→9, `public_0081`→2,
`public_0115`→2, `public_0149`→2, `public_0170`→8, `public_0178`→9). The
boundary-localized mechanism captures 100% of A0's rescue benefit for this
target family while, per §5, causing measurably less collateral damage elsewhere.

---

## 7. Existing-hit safety analysis (161 B2 hits)

```
hits preserved: 151
hits LOST:       10   -- public_0016, public_0026, public_0035, public_0058,
                          public_0065, public_0074, public_0080, public_0088,
                          public_0100, public_0145
```

**Identical loss set to A0, exactly 10/10 the same sessions.** Boundary
localization provides **zero** protection for these specific losses — explained
mechanically in §8, not merely observed as a coincidence.

---

## 8. Why localization didn't save the 10 lost hits (mechanism check, not inference)

Directly traced, for each of the 10 lost sessions, the equal-coverage group
containing the target at its B2-winning turn:

```
public_0016: B2_rank=8   group=[1,11]  size=11  coverage=1.000
public_0026: B2_rank=4   group=[1,38]  size=38  coverage=1.000
public_0035: B2_rank=10  group=[1,24]  size=24  coverage=1.000
public_0058: B2_rank=9   group=[1,15]  size=15  coverage=1.000
public_0065: B2_rank=6   group=[1,30]  size=30  coverage=1.000
public_0074: B2_rank=6   group=[1,50]  size=50  coverage=1.000
public_0080: B2_rank=7   group=[1,49]  size=49  coverage=1.000
public_0088: B2_rank=1   group=[1,37]  size=37  coverage=1.000
public_0100: B2_rank=8   group=[1,26]  size=26  coverage=1.000
public_0145: B2_rank=7   group=[7,15]  size=9   coverage=0.667
```

**9 of the 10 losses have a tied group starting at position 1 and running well
past position 10 — up to the entire 50-candidate pool** (`public_0074`). By the
mechanism's own definition (§2), any group that starts at or before position 10
and ends at or after position 11 **is** the straddling group — so these massive,
near-catalog-wide coverage-1.000 ties get reordered by active-only BM25 in their
entirety, identically to A0's blanket policy. Localization only helps when the
useful tied group is small and positioned away from position 1; it provides
**no** protection when the tie itself already spans the boundary from the top,
which is exactly the degenerate case §8 of the prior `FIX-02-P0` audit
identified as the catalog's dominant failure mode (near-universal boilerplate
terms causing huge coverage-1.000 ties). This is the same underlying mechanism
driving both experiments' hit losses — boundary localization narrows collateral
damage on the margins but does not touch the core problem.

---

## 9. The six previously-known B2 regression sessions

| Session | B2 rank/turn | FIX-02A1 rank/turn | vs. A0 |
|---|---|---|---|
| public_0023 | 10 / 5 | 5 / 4 | same as A0 |
| public_0093 | 4 / 7 | 4 / 7 (**unchanged**) | A0 regressed this to 6/7 — A1 protects it |
| public_0103 | 8 / 4 | 7 / 8 | same as A0 |
| public_0116 | 6 / 1 | 10 / 1 | same as A0 — still on the Top10 edge |
| public_0148 | 10 / 1 | 2 / 7 | better rank than A0's 6/7 |
| public_0190 | 4 / 7 | 1 / 9 | better rank than A0's 2/9 |

Localization measurably helps here too: `public_0093` is fully protected (A0
regressed it, A1 doesn't touch it), and `public_0148`/`public_0190` land at
better ranks than under A0. `public_0116` remains exactly as concerning as
before — consistent with §8's finding, since this session's group likely also
spans from near position 1.

---

## 10. Acceptance logic (per the authorization's dynamic framework, §11)

The required conjunction for a strong result:

```
meaningful net HR improvement        -- FAILS: HR@10 fell (0.805 -> 0.800, net -1 hit)
AND MRR stable or improved           -- PASSES: +0.0018
AND MTTC stable or improved          -- FAILS: +0.295, same regression as A0
AND far fewer regressions than A0    -- PASSES: 30 vs 49, severity ratio 1.24x vs 1.94x
AND little/no existing-hit destruction -- FAILS: identical 10/161 hits lost, same as rejected A0
```

3 of 5 conditions fail, including the two most consequential ones (HR and
existing-hit destruction — both identical in magnitude to the already-rejected
A0). TechnicalScore is still net negative (0.654129 → 0.646270). The
improvement over A0 is real and worth recording (§5, §9), but it is an
improvement in *collateral damage reduction*, not a fix for the *core* hit-loss
mechanism, which §8 shows is architecturally untouched by boundary localization.

## CLASSIFICATION: REJECT

Weaker rejection than A0 (smaller regression surface, MRR now improves, two of
the six known regression sessions are protected or improved), but still a
rejection on the framework's own terms: HR@10 and existing-hit destruction are
byte-for-byte as bad as the mechanism already rejected in `FIX-02A0`, and §8
shows mechanically why localization cannot fix that specific part of the
problem. Per the authorization's own branch instructions for a weak/harmful
result: **not tuned further** (no threshold/coefficient search performed), and
the active-BM25 tie-break family is not pursued past this point in this pass.

---

## 11. Runtime

Not measured, per the authorization's "fast-governed mode": profiling is
reserved for a result that survives independent review first. This result did
not clear that bar, so no runtime comparison was run — consistent with "if A1
is bad, reject immediately, do not waste time profiling it."

---

## 12. Anti-overfitting note

The mechanism is one frozen, general rule (boundary position is fixed by the
evaluator's own Top-10 scoring contract, not fitted to public-set results) run
identically across all 200 sessions. No session-specific or ASIN-specific logic
was introduced.

---

## STOP

FIX-02A1 was **not** implemented in `starter/agent.py`. Nothing staged,
committed, or pushed. This report is ready for independent review. Per the
authorization's own branch-after-A1 guidance for a weak/harmful result, the
next candidates it names — (A) Intent Override collapse recoverability, or (B)
semantic/hybrid retrieval feasibility for the B/C/D misses — are noted here as
the prescribed next options, not selected or authorized by this pass.
