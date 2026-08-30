# FIX-01B2 — Active-Term Coverage End-to-End Simulation

Produced per the `FIX-01B2 — ACTIVE-TERM COVERAGE END-TO-END SIMULATION` directive
embedded in `SECOND-STAGE RANKING SEPARABILITY AUDIT — INDEPENDENT REVIEW.md`. Scope:
simulate the frozen active-term-coverage ranking mechanism (BM25 top-50 → sort by
descending term-coverage fraction, baseline tiebreak → top 10) under the **real
evaluator stopping protocol** — not the offline oracle used in the prior separability
audit — to check whether the offline "15/54 separability opportunities" survive contact
with the actual session-termination rule. **Simulation only — no `starter/agent.py`
edit, no B2 implementation in production code, no tuning, nothing committed.**

---

## 0. Production state confirmation

```bash
git rev-parse HEAD
  # 500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647
shasum -a 256 starter/agent.py
  # 0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
git status --short -- starter/agent.py
  # (no output -- clean)
```

---

## 1. Frozen mechanism simulated (exactly as specified, N=50 only)

```
1. Real, unmodified B0 candidate query (agent.respond(..., top_k=50)) — no change.
2. active_expression / active_terms built from state.active_slots only (same
   tokenization as production's _terms(), same as the prior separability audit).
3. Per-candidate coverage = (distinct active terms matched) / (distinct active terms).
4. Sort candidates descending by coverage, ties broken by original baseline BM25 order.
5. Take first 10.
```

No other pool depth was tested. Tokenizer, stopwords, BM25 field weights,
`_build_query()`, `active_slots` semantics, `ASK_ORDER`, and conversation flow were never
touched — the mechanism above runs entirely in an external harness script that only ever
calls the real `Agent.respond()` and reads `connection`/`state`, exactly as the two prior
simulation audits (`candidate_rescue_simulation_b1.md`,
`second_stage_ranking_separability_audit.md`) did.

**Crucial methodological point, per the directive's own requirement**: unlike the prior
separability audit's *oracle* diagnostic (best rank across all eligible turns), this
simulation follows the **real stopping protocol** — the simulated B2 trajectory is
scored at the **first eligible turn** where its own top-10 contains the target, exactly
mirroring `evaluator.local_evaluator.evaluate()`'s own `if override_applied and target in
ranked: ... break` logic, and Intent Override sessions are never credited before their
override turn. This was implemented by replaying the real conversation once (dialogue
content is driven entirely by the real, unmodified B0 agent's own `ask_attribute` logic
via `customer_reply()`, which does not depend on which candidate reordering rule is being
scored) and tracking each of the two trajectories — real B0 and simulated B2 — to their
own independent first-hit point, closing the loop only once *both* have reached a stop
condition or turn 10. This is a measurement technique, not a change to how either
trajectory's dialogue is generated.

---

## 2. Determinism

Run twice, independently, start to finish (fresh `Agent` instance, fresh session UUIDs
both times). Full 200-session output compared programmatically: `identical: True`.

---

## 3. Overall metrics

All metrics recomputed with the exact rounding order `evaluator.local_evaluator` uses
(round HR/MRR/MTTC to 6 decimals first, derive Efficiency from the *rounded* MTTC, then
compute TechnicalScore from the rounded components) — verified by reproducing the
canonical B0 TechnicalScore (0.597737) exactly from this same run's official-trajectory
data before trusting the B2 numbers.

| Metric | B0 (`500fe7b`) | Historical B1 (N=10) | **FIX-01B2 (N=50, term coverage)** |
|---|---|---|---|
| HR@10 | 0.730000 | 0.730000 | **0.805000** |
| MRR | 0.465458 | 0.474675 | **0.499431** |
| MTTC | 6.345000 | 6.345000 | **5.910000** |
| Efficiency | 0.465500 | — | **0.509000** |
| TechnicalScore | 0.597737 | 0.600502 | **0.654129** |

**161/200 sessions hit** — HR@10 moved from 0.730 to 0.805, a +0.075 absolute gain.
TechnicalScore moved from 0.597737 to 0.654129 (+0.056392).

---

## 4. The critical verification: does the offline 15/54 survive the real protocol?

**Yes, exactly, with zero exceptions in either direction.**

```
Original 146 B0 hits, checked against B2 under the real stopping protocol:
  preserved as B2 hits: 146 / 146
  lost (became a B2 miss):  0 / 146

Original 54 B0 misses, checked against B2 under the real stopping protocol:
  became genuine new B2 hits: 15 / 54
  still miss under B2:        39 / 54

Total B2 hits = 146 + 15 = 161  (matches the topline HR@10 = 0.805 exactly)
```

Cross-referenced against the specific 15 `sample_id`s flagged by the prior offline
diagnostic (`public_0015, 0016, 0017, 0035, 0040, 0058, 0064, 0078, 0095, 0097, 0120,
0127, 0171, 0172, 0184`): **all 15 of the offline-flagged sessions are exactly the 15
that became real end-to-end hits — no substitutions, no dropouts, no session outside
that list was rescued instead.**

This is a genuinely notable result given the specific concern raised in the independent
review (§5–§6 of `SECOND-STAGE RANKING SEPARABILITY AUDIT — INDEPENDENT REVIEW.md`):
that early-stop timing effects (documented as real, in
`markdowns/candidate_rescue_simulation_b1.md` §4, for the binary B1 mechanism at larger
N) could cause the offline oracle count to overstate the real end-to-end gain. **For this
specific mechanism (term coverage @ N=50), that slippage did not occur** — the offline
diagnostic's answer for "which misses are separable" turned out to be identical to the
real protocol's answer for "which misses become genuine new hits." This is reported as
an observed result for this one configuration, not evidence that oracle-diagnostic
counts can be trusted to transfer to real protocol results in general — the countervailing
evidence already exists (§5 below) that real-protocol effects the offline diagnostic
cannot see (in-bounds rank degradation) are still present here.

---

## 5. Full session-level delta accounting (all 200 sessions)

```
new hits:                    15
new misses:                   0
net HR change:               +15

rank improvements (both hit, B2 rank better):    30
rank regressions  (both hit, B2 rank worse):       6
first-hit-turn improvements:                       7
first-hit-turn regressions:                        0
unchanged (identical outcome, or both miss):     149
```

`15 + 0 + 30 + 6 + 149 = 200` ✓.

**All 15 new hits:**

| sample_id | scenario | B2 turn | B2 rank |
|---|---|---|---|
| public_0015 | browsing | 8 | 1 |
| public_0016 | browsing | 10 | 8 |
| public_0017 | buying | 2 | 8 |
| public_0035 | boundary | 10 | 10 |
| public_0040 | browsing | 3 | 8 |
| public_0058 | buying | 9 | 9 |
| public_0064 | intent_override | 4 | 7 |
| public_0078 | intent_override | 8 | 4 |
| public_0095 | buying | 9 | 5 |
| public_0097 | buying | 9 | 10 |
| public_0120 | browsing | 8 | 4 |
| public_0127 | browsing | 3 | 6 |
| public_0171 | buying | 9 | 4 |
| public_0172 | browsing | 8 | 5 |
| public_0184 | browsing | 8 | 6 |

**A finding the offline oracle diagnostic could not see — 6 rank regressions among
sessions that hit under both B0 and B2** (the prior separability audit's regression
definition only counted a target crossing *out* of the top 10, so these in-bounds
degradations were invisible to it):

| sample_id | scenario | B0 rank / turn | B2 rank / turn |
|---|---|---|---|
| public_0023 | intent_override | 1 / 9 | 10 / 5 |
| public_0093 | buying | 1 / 9 | 4 / 7 |
| public_0103 | intent_override | 5 / 4 | 8 / 4 |
| public_0116 | buying | 2 / 9 | 6 / 1 |
| public_0148 | buying | 5 / 7 | 10 / 1 |
| public_0190 | buying | 2 / 9 | 4 / 7 |

**`public_0148` is the same session, with the identical exact rank/turn change (5/7 →
10/1), as the rank regression found independently in
`markdowns/candidate_rescue_simulation_b1.md` §4** for the binary B1 mechanism at
N=20/50/100 — the same early-stop-timing mechanism (an earlier, marginal-rank appearance
inside a larger pool closes the session before a later, better rank is reached) is very
likely responsible here too, given the identical numbers and identical direction, though
this simulation did not re-derive that mechanism independently for B2 — it is noted as a
consistent cross-audit observation, not re-proven from first principles in this pass.

No first-hit-turn regressions occurred at all (0/200) — every session that hit under
both systems did so no later, in turns, under B2 than under B0. **5 of the 6 rank
regressions show the earlier-but-worse pattern explicitly** (turn strictly earlier *and*
rank strictly worse: `public_0023`, `public_0093`, `public_0116`, `public_0148`,
`public_0190`) — the same dynamic already documented in
`candidate_rescue_simulation_b1.md` §4, where a larger pool lets the session close on an
earlier, weaker match before a later, stronger one would have been reached. The sixth,
`public_0103`, is the only regression at an *unchanged* turn (4 → 4, rank 5 → 8) — a pure
ranking-quality loss with no timing component, and the one case in this table not
explained by the early-stop mechanism.

---

## 6. Scenario metrics

| Scenario | B0 HR@10 | B2 HR@10 | B0 MRR | B2 MRR | B0 MTTC | B2 MTTC |
|---|---|---|---|---|---|---|
| Boundary | 0.700000 | 0.800000 | 0.491667 | 0.501667 | 6.700000 | 6.600000 |
| Browsing | 0.712500 | 0.800000 | 0.470184 | 0.509142 | 6.025000 | 5.662500 |
| Buying | 0.787500 | 0.850000 | 0.436796 | 0.478378 | 6.287500 | 5.750000 |
| Intent Override | 0.633333 | 0.700000 | 0.520556 | 0.528929 | 7.233333 | 6.766667 |

**New hits by scenario**: Browsing 7, Buying 5, Intent Override 2, Boundary 1 — sums to
15. **Rank regressions by scenario**: Buying 4, Intent Override 2, Browsing 0, Boundary 0.

### Browsing detail (directive's specific point of attention)

Re-derived the offline N=50 (not N=100) Browsing-specific rescue list directly from the
prior separability audit's raw data, since that report's §6 only published the N=100
Browsing breakdown (8/23) — the N=50 figure was folded into the 15/54 aggregate without
being broken out by scenario there.

```
Browsing misses (original, from candidate_recall_audit_b0.md): 23
Offline separability opportunities, diagnostic B @ N=50:         7 / 23
  -> public_0015, 0016, 0040, 0120, 0127, 0172, 0184
Actual end-to-end B2 rescues (this simulation):                  7 / 23
  -> public_0015, 0016, 0040, 0120, 0127, 0172, 0184
```

**Exact match, same 7 sessions in both lists** — consistent with, and part of, the
overall 15/15 exact match already reported in §4 (the Browsing subset was not a special
case; it simply makes up 7 of the 15).

---

## 7. Governance confirmation

```
NO PRODUCTION EDIT.  -- starter/agent.py byte-identical to HEAD throughout.
NO B2 IMPLEMENTATION. -- the mechanism was run only inside a disposable external
                          harness script; nothing was written into starter/agent.py.
NO TUNING.            -- exactly the one frozen mechanism (term coverage, N=50, no
                          weights, baseline tiebreak) was simulated; no variant,
                          threshold, or alternative pool depth was tried.
NO COMMIT.            -- nothing staged or committed; HEAD unchanged at 500fe7b.
```

---

## 8. Git status

```
 (starter/agent.py: no modification, byte-identical to HEAD)
?? markdowns/fix01b2_term_coverage_end_to_end_simulation.md
(plus the pre-existing untracked markdowns/ files from prior FIX-01/FIX-01B0/FIX-01B1
 work and the two prior separability/rescue audits, unrelated to this pass)
```

---

## Summary for the next decision

Under the real evaluator stopping protocol — not the offline oracle — the frozen
active-term-coverage mechanism at BM25 top-50 produces **HR@10 0.730 → 0.805, MRR 0.465
→ 0.499, TechnicalScore 0.598 → 0.654**, with all 146 original hits preserved and exactly
the 15 sessions the offline diagnostic flagged becoming genuine new hits — a clean,
verified confirmation that this specific mechanism's offline separability signal
translated to the real protocol without the slippage the independent review specifically
warned could occur. That said, the real protocol also surfaced something the offline
diagnostic structurally could not see: **6 sessions that remain hits under both systems
had their rank quality degrade** (one, `public_0148`, matching a previously-documented
early-stop-timing pattern exactly), which is why MRR's gain (+0.033973) is smaller than
what a naive "146 unchanged + 15 perfect rescues" accounting would suggest. Per the
directive, no production edit, no B2 implementation, and no tuning were performed —
these are simulation results only. Stopping for independent review.
