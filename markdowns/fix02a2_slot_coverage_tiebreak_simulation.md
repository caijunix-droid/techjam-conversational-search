# FIX-02A2 — Active-Slot Coverage as Secondary Tie-Break Simulation

Written 2026-08-31. **Offline/external simulation only. No production code touched,
nothing staged, nothing committed.** All numbers come from executable scripts run
against the live `Agent`/FTS5/BM25 machinery. Scripts and full session-level output
live in scratch files (paths in §0), never staged.

---

## 0. Artifacts produced (all outside the repo)

```
/private/tmp/.../scratchpad/agent_b0.py                       -- git show 500fe7b:starter/agent.py, SHA-verified
/private/tmp/.../scratchpad/get_b0_split.py                    -- recovers exact B0 54-miss/146-hit split
/private/tmp/.../scratchpad/b0_split.json
/private/tmp/.../scratchpad/reproduce_slot_coverage_audit.py   -- validates recovered Diagnostic-C definition
/private/tmp/.../scratchpad/reproduce_slot_coverage_output.txt
/private/tmp/.../scratchpad/fix02a2_simulate.py                -- FIX-02A2 simulator + experiment
/private/tmp/.../scratchpad/fix02a2_output.json
/private/tmp/.../scratchpad/fix02a2_analyze.py
/private/tmp/.../scratchpad/fix02a2_analyze_output.txt
/private/tmp/.../scratchpad/inspect_0149.py                    -- mechanism-level trace of the one rescue
```

`starter/agent.py` and `tests/` byte-identical to `c30c712` throughout.

---

## 1. Historical slot-coverage mechanism recovery (§3 of the authorization)

Recovered from `markdowns/second_stage_ranking_separability_audit.md` §2,
**Diagnostic C — Active-slot coverage** (verbatim):

> for each `active_slots` key with ≥1 usable tokenized term ("matchable slot"),
> whether the candidate matches ≥1 of that slot's terms; `(slots satisfied) /
> (matchable slots)`, ordered descending, baseline-order tiebreak. No slot
> weights.

This is **not** the same computation as B2's own active-term coverage: term
coverage flattens every active-slot value into one combined term list; slot
coverage groups terms by their originating `active_slots` **key** and only
requires **one** term-per-slot to match for that whole slot to count as
satisfied — a materially different, coarser-grained signal.

**Reproduction, not just quotation, before trusting this definition**: recovered
the exact B0 code (`git show 500fe7b:starter/agent.py`, SHA
`0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354`, matches
exactly), replayed all 200 sessions to recover the exact original 54-miss/146-hit
split (HR@10 0.730, matches every prior handover's cited B0 number), then
implemented Diagnostic C exactly as quoted above and ran it at N=50 using the
historical audit's own stated methodology (best-across-eligible-turns for
misses, single real-hit-turn for hits):

```
rescued:   9 / 54   -- public_0015, 0035, 0040, 0064, 0078, 0127, 0149, 0171, 0184
regressed: 0 / 146
```

**Matches the historical audit's cited numbers exactly (9/54, 0/146).** The
recovered mechanism is confirmed correct — proceeding to FIX-02A2 on this basis,
not a re-derived or reinvented definition.

---

## 2. Frozen B2 baseline verification

```bash
git rev-parse HEAD                 # c30c712348aa94e42d932ebe49bee7cc966f9fe1
git status --short                 # only untracked markdown/research artifacts
shasum -a 256 starter/agent.py     # e3f324caf8e6c940d44293beffd6a71df489f56564639c5af800d70d2975b9b5
python3 -m unittest discover -s tests -p 'test*.py'   # Ran 22 tests — OK
```

Simulator's own B2-equivalence run reproduced exactly: HR@10 0.805000, MRR
0.499431, MTTC 5.910000, TechnicalScore 0.654129, all 4 scenario breakdowns
match. **Proceeding.**

---

## 3. FIX-02A2 exact mechanism (as implemented)

Candidate generation and primary active-term-coverage ranking identical to B2
(reused via `_build_query`/`_active_terms`, unchanged). Sort key applied to the
Top-50 candidate pool:

```python
key = (-term_coverage(asin), -slot_coverage(asin), baseline_bm25_index(asin))
```

`slot_coverage` is computed exactly per §1's recovered definition, scoped to
the same Top-50 pool B2 already restricts to. No active-only BM25 anywhere in
this mechanism (distinct from the rejected `FIX-02A0`/`FIX-02A1` family). If
there are no matchable slots at a given turn, `slot_coverage` is 0.0 for every
candidate — a no-op tier that falls through to the unchanged baseline-order
tie-break, identical to B2 for that turn.

---

## 4. Safety invariants (§5 of the authorization)

```
term_coverage_violations = 0   -- no candidate with lower active-term coverage
                                   ever ranked above one with higher coverage
tie_order_violations     = 0   -- candidates equal on BOTH term coverage and
                                   slot coverage always retain exact B2/BM25
                                   relative order
```

Both required at 0; both measured at 0, checked mechanically on every turn of
every session, not asserted from the construction alone.

---

## 5. FIX-02A2 overall results — all 200 sessions

| Metric | B2 (frozen) | FIX-02A2 | Δ |
|---|---:|---:|---:|
| HR@10 | 0.805000 | **0.810000** | **+0.005** |
| MRR | 0.499431 | 0.496028 | −0.003403 |
| MTTC | 5.910000 | **5.815000** | **−0.095** |
| Efficiency | 0.509000 | **0.518500** | **+0.0095** |
| TechnicalScore | 0.654129 | **0.657508** | **+0.003379** |

Scenario breakdown:

| Scenario | B2 HR@10 | A2 HR@10 | B2 MRR | A2 MRR | B2 MTTC | A2 MTTC |
|---|---:|---:|---:|---:|---:|---:|
| Boundary | 0.800 | 0.800 | 0.501667 | 0.501667 | 6.600 | 6.600 |
| Browsing | 0.800 | 0.800 | 0.509142 | 0.509142 | 5.6625 | 5.600 |
| Buying | 0.850 | **0.8625** | 0.478378 | 0.469871 | 5.750 | **5.575** |
| Intent Override | 0.700 | 0.700 | 0.528929 | 0.528929 | 6.766667 | 6.766667 |

**Every change is confined to the Buying scenario** (plus one Browsing-turn
improvement, §6). Boundary and Intent Override are completely untouched —
byte-for-byte identical metrics, not merely close.

---

## 6. Session-level delta analysis (B2 vs FIX-02A2)

```
new hits (miss -> hit):     1   -- public_0149 (rank 8, turn 2)
new misses (hit -> miss):   0
rank improvements:          1   -- public_0042 (6 -> 4, same turn 3)
rank regressions:           1   -- public_0154 (1 -> 9)
first-hit-turn improvements: 2  -- public_0154 (turn 7 -> 2), public_0184 (turn 8 -> 3)
first-hit-turn regressions:  0
fully unchanged sessions: 196
```

**Only 4 sessions touched at all, out of 200.** `public_0154` needs explicit
note: it trades a *later-but-perfect* hit (B2: turn 7, rank 1) for an
*earlier-but-weaker* hit (A2: turn 2, rank 9) — both are still hits (session
stays in the 161), MTTC improves for this session, but its reciprocal-rank
contribution to MRR drops from 1.0 to 0.111, which is the entire explanation
for MRR's small net decline (0.499431 → 0.496028) despite HR@10 and MTTC both
improving. This is reported plainly, not smoothed over by the aggregate
numbers.

---

## 7. Remaining-39 breakdown by bucket (per `FIX-02-P0`'s classification)

| Bucket | Sessions | Rescued | Still miss |
|---|---:|---:|---:|
| A (coverage-tie, all A1) | 19 | **1** (`public_0149`) | 18 |
| B (rank 51–100) | 13 | 0 | 13 |
| C (rank 101–500) | 6 | 0 | 6 |
| D (>500/absent) | 1 | 0 | 1 |

Consistent with the mechanism's scope: slot coverage only reorders *within*
B2's existing Top-50 candidate pool, so it can only ever help Bucket-A misses
(the only bucket where the target is already inside that pool) — never Bucket
B/C/D, where the target isn't retrieved into the pool at all. This matches
expectations exactly; no surprise here.

### The one rescued A1 session, in full (§8 of the authorization)

`public_0149` (buying), turn 2, direct trace:

```
state.active_slots = {'material': 'leather', 'color': 'color: black'}
active_terms        = [leather, color, black]
matchable_slots      = [('material', [leather]), ('color', [color, black])]

target term_coverage:  0.667   (matched 2 of 3 flat active terms)
target slot_coverage:  1.000   (satisfied BOTH matchable slots -- material
                                 and color -- since a slot only needs 1 of its
                                 terms matched, not all)

B2 rank (term coverage only):        13
FIX-02A2 rank (term + slot coverage): 8

candidates tied with target on term coverage: 10
  of those: 0 have higher slot coverage than target
            4 have equal slot coverage (tied with target, further resolved by baseline BM25)
            6 have LOWER slot coverage than target -- correctly demoted below it
```

This is exactly the mechanism §1 of the FIX-02A2 authorization predicted: the
target's partial term-level miss (missed one raw token) doesn't cost it at the
slot level, because the token it missed shares a slot ("color") with a token it
did match — slot coverage credits the whole slot as satisfied. 6 of its 10
term-coverage-tied competitors lack that same slot-level completeness and are
correctly pushed below it, landing the target at rank 8.

---

## 8. Existing-hit safety analysis (161 B2 hits)

```
hits preserved: 161
hits LOST:        0
```

**Zero existing hits destroyed.** This matches the historical Diagnostic C
audit's own 0/146 regression finding (§1) and extends it: even integrated into
the live conversational loop (not just a static oracle re-rank), across all
161 real B2 hits, slot coverage introduces no losses. Substantial hit
destruction did **not** appear, consistent with — not contradicting — the
historical safety signal this experiment was authorized on the strength of.

---

## 9. The six previously-known B2 regression sessions

| Session | B2 rank/turn | FIX-02A2 rank/turn |
|---|---|---|
| public_0023 | 10 / 5 | 10 / 5 (unchanged) |
| public_0093 | 4 / 7 | 4 / 7 (unchanged) |
| public_0103 | 8 / 4 | 8 / 4 (unchanged) |
| public_0116 | 6 / 1 | 6 / 1 (unchanged) |
| public_0148 | 10 / 1 | 10 / 1 (unchanged) |
| public_0190 | 4 / 7 | 4 / 7 (unchanged) |

**All six completely untouched** — this experiment does not interact with any
of B2's own previously-known regression sessions at all, for better or worse.

---

## 10. Override safety (§10 of the authorization)

`matchable_slots` is built directly from `state.active_slots.items()` — the
exact same dict B2's own `_active_terms()` already restricts itself to (never
`state.slots`), so superseded/historical terms structurally cannot enter slot
coverage, by construction. Concrete trace, reusing the same `public_0071`
`intent_override` session traced in `FIX-02A0`'s report (§10 there) since it
demonstrates the same underlying `state.active_slots` dict this mechanism reads
directly:

```
turn 3 (pre-override): state.active_slots = {'feature': 'Pull On', 'material': '90% Cotton, 10% Others'}
turn 4 (override fires): state.active_slots = {'material': 'cotton'}
```

At turn 4, `matchable_slots` is built from `{'material': 'cotton'}` only — the
superseded `'feature'` key and the richer pre-override `'material'` value are
both gone, confirming slot coverage (like term coverage) only ever sees the
live post-override state, never historical evidence.

---

## 11. Fast quality gate classification (§11 of the authorization)

```
TechnicalScore:        IMPROVED   (0.654129 -> 0.657508)
meaningful hit destruction: NONE  (0/161 lost)
signal separation:      REAL, mechanistically explained (§7)
```

None of the "reject immediately" conditions are met. This is a **credible
positive result** — small in absolute magnitude (net +1 hit, 4 sessions
touched out of 200) but clean: every top-line metric except MRR improves or is
unchanged, MRR's small decline is fully explained by a single non-loss
session's rank trade-off (§6), safety invariants are mechanically verified at
0/0, and zero existing hits are destroyed.

## CLASSIFICATION: POSITIVE — RETURN FOR INDEPENDENT REVIEW

Per the authorization's own branch instruction ("If A2 produces a credible
positive result: THEN return for independent review before
implementation/performance work"), this result is reported for review now.
**No runtime profiling and no implementation were performed in this pass** —
both are explicitly reserved for after independent review, per governance.

---

## 12. Anti-overfitting note

The mechanism is one frozen, general rule (the exact historically-audited
Diagnostic C definition, not re-derived or tuned for this specific run) applied
identically across all 200 sessions. No session-specific or ASIN-specific logic
was introduced or considered.

---

## STOP

FIX-02A2 was **not** implemented in `starter/agent.py`. Tests were not
modified. Nothing was staged, committed, or pushed. Runtime was not profiled.
This report, including the one rescued session's full mechanism-level trace
(§7) and the confirmed 0/161 hit-loss and 0/0 safety-invariant results, is
ready for independent review and a decision on whether to proceed to
implementation.
