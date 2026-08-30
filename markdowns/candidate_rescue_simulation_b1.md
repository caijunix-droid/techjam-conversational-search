# Candidate Rescue Simulation — Frozen FIX-01B1 Rule Over Enlarged Pools

Produced per `TECHJAM — CANDIDATE RESCUE SIMULATION AUDIT.md`. Scope: simulate the
already-frozen FIX-01B1 active-intent stable-partition rule applied to baseline BM25
candidate pools of size N=20/50/100 (instead of the production N=10), truncated back to
a final top-10, entirely outside `starter/agent.py`. **Measurement/simulation only — no
code edit, no B1 modification, no tuning, nothing committed.**

---

## 0. Confirmation production code untouched

```bash
git rev-parse HEAD
  # 500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647
shasum -a 256 starter/agent.py
  # 0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
git status --short -- starter/agent.py
  # (no output -- clean)
```

Matches the committed B0 baseline exactly, both before and after this audit. No file
under `starter/` was written to at any point in this session.

---

## 1. Frozen rule used (verified against the preserved patch, not recollection)

Re-read `markdowns/patches/fix01b1_active_intent_ranking.patch` directly before writing
any simulation code, rather than relying on memory of the earlier B1 work. The simulation
reimplements exactly two things from that patch, verbatim:

```python
# _active_expression() -- patch lines 16-18
combined = " ".join(state.active_slots.values())
unique_terms = list(dict.fromkeys(_terms(combined)))[:40]
active_expression = " OR ".join(f'"{term}"' for term in unique_terms)

# reorder step -- patch lines 38-49
if active_expression and candidates:
    active_matches = { ... FTS MATCH ... AND parent_asin IN (candidates) ... }
    if active_matches:
        candidates.sort(key=lambda asin: asin not in active_matches)
```

`_terms()` (tokenizer/stopword logic) was imported directly from `starter.agent` — the
real, unmodified B0 module — not reimplemented, so tokenization is guaranteed identical
to production. `state.active_slots` is read from the live `SessionState` the real,
unmodified B0 `Agent.respond()` populates each turn (B0 tracks `active_slots` for its own
dialog-question logic; B1 only ever added a consumer of it, never a producer) — so the
active-intent content being simulated is exactly what B0 itself computes, not a
reconstruction.

**Candidate generation was never touched.** Baseline candidates came from a single real
`agent.respond(session_id, user_message, turn, top_k=100)` call per turn — the actual
committed B0 code path, using its actual `_build_query()`/`ORDER BY bm25(...)`/`LIMIT`
SQL, unmodified. N=20 and N=50 pools were taken as the first 20/50 entries of that same
top-100 result (a strict prefix of one deterministic BM25-ordered stream — validated
identical to a fresh independent `top_k=N` query in the prior candidate-recall audit),
so no separate query was needed per N. This is a read-only, external harness — the
committed `respond()` return value was consumed as-is and reordered only in the harness
script, never inside `starter/agent.py`.

Intent Override eligibility (`override_applied`) was reproduced exactly from
`evaluator/local_evaluator.py`'s own gating logic, matching the correction already
established in `markdowns/candidate_recall_audit_b0.md` §E: a pre-override turn's
recommendations are never counted as an eligible hit for Intent Override sessions,
for the real B0 conversation *or* for any simulated N.

---

## 2. Reference metrics

**Reference A — committed B0** (`starter/agent.py` at `500fe7b`, N=10, no reranking):

```
HR@10          0.730000
MRR            0.465458
MTTC           6.345000
Efficiency     0.465500
TechnicalScore 0.597737
```

**Reference B — historical FIX-01B1 experiment** (N=10, frozen active-intent partition,
from `markdowns/fix01b1_active_intent_ranking_handover.md` §6 — uncommitted, historical
evidence only, not a production baseline):

```
HR@10          0.730000
MRR            0.474675
MTTC           6.345000
TechnicalScore 0.600502
```

---

## 3. Simulated metrics — N=20, N=50, N=100

| Metric | Ref A (B0, N=10) | Ref B (B1, N=10) | N=20 | N=50 | N=100 |
|---|---|---|---|---|---|
| HR@10 | 0.730000 | 0.730000 | 0.730000 | **0.735000** | **0.735000** |
| MRR | 0.465458 | 0.474675 | 0.469550 | 0.470264 | 0.470264 |
| MTTC | 6.345000 | 6.345000 | 6.295000 | 6.260000 | 6.260000 |
| Efficiency | 0.465500 | — | 0.470500 | 0.474000 | 0.474000 |
| TechnicalScore | 0.597737 | 0.600502 | 0.599965 | 0.603379 | 0.603379 |

**N=50 and N=100 produced byte-identical results in every metric.** The single session
rescued by pool enlargement (see §5) already surfaces within the top 50; going to 100
gained nothing further on this 200-session set.

Determinism: the full simulation was run twice, independently, start to finish (fresh
`Agent` instance, fresh session UUIDs both times); the two runs' complete per-session,
per-N raw result sets compared programmatically as `identical: True`.

### Scenario breakdown

| Scenario | N | HR@10 | MRR | MTTC |
|---|---|---|---|---|
| Boundary | 20/50/100 (identical) | 0.700000 | 0.491667 | 6.700000 |
| Browsing | 20/50/100 (identical) | 0.712500 | 0.459246 | 5.975000 |
| Buying | 20/50/100 (identical) | 0.787500 | 0.449628 | 6.212500 |
| Intent Override | 20 | 0.633333 | 0.542778 | 7.233333 |
| Intent Override | 50/100 | **0.666667** | 0.547540 | 7.000000 |

**Boundary, Browsing, and Buying show zero HR@10 movement at any tested pool size** —
identical to Reference A on every scenario metric. **All net HR@10 movement is confined
to Intent Override**, and only between N=20 and N=50 (one session).

---

## 4. Rescue accounting vs. Reference A (all 200 sessions)

| | N=20 | N=50 | N=100 |
|---|---|---|---|
| New hits | 0 | 1 | 1 |
| New misses | 0 | 0 | 0 |
| Net HR change | 0 | +1 | +1 |
| Rank improvements | 8 | 8 | 8 |
| Rank regressions | **2** | **2** | **2** |
| First-hit-turn improvements | 2 | 2 | 2 |
| First-hit-turn regressions | 0 | 0 | 0 |

**New hit** (N=50, N=100 only):

| sample_id | scenario | turn rescued | final simulated rank | baseline rank in pool |
|---|---|---|---|---|
| public_0064 | intent_override | 4 | 7 | 22 |

**Rank regressions** (present at all three N — flagged in detail, see §7 for why these
occur and why they are not the same failure mode as the earlier-established
"dangerous configuration"):

| sample_id | scenario | official rank / turn | simulated rank / turn (N=20/50/100, identical) |
|---|---|---|---|
| public_0141 | browsing | rank 1, turn 7 | rank 8, turn 3 |
| public_0148 | buying | rank 5, turn 7 | rank 10, turn 1 |

**Neither regression is a same-turn demotion.** In both cases the simulated system finds
the target inside the *enlarged* pool at an earlier turn than the real B0 top-10 ever
did (turn 3 vs. 7, and turn 1 vs. 7) — the session protocol's own "session ends after a
valid hit" rule (per `docs/competition_specification.md`) means an early, mediocre-rank
appearance closes the session before the real system's later, better rank is ever
reached. This is a genuine trade-off exposed by pool enlargement, not a bug in the
simulation: an earlier but worse rank (MTTC improves, MRR worsens) is scored differently
from a later but better one, and the two sessions above land on the worse side of that
trade-off. Confirmed both targets *were* active-intent matches at the earlier turn (so
this is not the previously-established "non-active-match demoted by a competing match"
failure mode — see §7's 100% active-match-rate finding); it is a pure timing effect of
declaring a hit against a bigger candidate pool.

---

## 5. The 54 original B0 misses — rescue table

| Original bucket | Total | Rescued @20 | Rescued @50 | Rescued @100 |
|---|---:|---:|---:|---:|
| 11–20 | 18 | 0 | 0 | 0 |
| 21–50 | 16 | 0 | 1 | 1 |
| 51–100 | 13 | 0 | 0 | 0 |
| 101–500 | 6 | 0 | 0 | 0 |
| >500/absent | 1 | 0 | 0 | 0 |
| **Total** | **54** | **0** | **1** | **1** |

**Zero of the 18 misses whose target sat at baseline rank 11–20 were rescued even at
N=20** — the exact pool depth that should have made them visible. This is not a
candidate-recall failure (see §6: all 18 targets *did* enter the N=20 pool) — it is a
ranking failure, explained in §6.

The single rescue, `public_0064`, came from the 21–50 bucket, and only appeared once N
reached 50 (its baseline rank of 22 falls inside a 50-deep pool but outside a 20-deep
one).

---

## 6. Active-match diagnostic — why enlargement mostly failed to rescue

For every original miss whose target entered the tested pool, at N=20/50/100:

```
target entered pool (N=20):   18 / 54
target entered pool (N=50):   33 / 54
target entered pool (N=100):  46 / 54

Of those that entered the pool, target itself matched the active-intent
expression at that turn:      18/18 (N=20), 33/33 (N=50), 46/46 (N=100)  --  100%
```

**Every single miss target that entered any tested pool was itself an active-intent
match — 0% were the "target is not an active match" configuration** that the earlier
safety-boundary verification (`markdowns/fix01b1_safety_boundary_verification.md`)
identified as the only way B1's stable partition can demote a target. This directly
answers the directive's §7 concern: **candidate-pool enlargement did not introduce
meaningful new exposure to that specific dangerous configuration** among these 54
originally-missed targets — though see §4's two regressions, a different mechanism
(early-stop timing, not non-match demotion).

But being an active match did not translate into rescue, for a specific, measurable
reason: in nearly every case, the number of *other* active-matching candidates ranked
**ahead** of the target inside the pool already meets or exceeds the target's own
baseline rank, so the stable partition leaves the target's position **completely
unchanged** (`post_partition_rank == baseline_rank_in_N`) in the large majority of rows.
Representative examples at N=100:

```
public_0035: baseline_rank_in_N=14  post_partition_rank=14  (unchanged; ahead=14, behind=85)
public_0011: baseline_rank_in_N=20  post_partition_rank=20  (unchanged; ahead=20, behind=67)
public_0028: baseline_rank_in_N=92  post_partition_rank=92  (unchanged; ahead=92, behind=7)
```

The mechanism: with up to 40 OR-joined active-intent terms, a large fraction of any
50,000-product FTS index tends to match *something* in the expression, so most of the
candidates already ranked ahead of the target are themselves also active matches — there
is nothing non-matching between them and the target's original position to demote out of
the way. The rule promotes matches as a block, but a target buried at rank 14–90 *within*
a block of 14–92 other matches stays exactly where it started. A handful of sessions did
see the target move by a few positions (e.g. `public_0144`: 98 → 47 at N=100;
`public_0071`: 44 → 38 at N=50), but never close to enough to cross the top-10 line
except the single `public_0064` case.

**Conclusion for the directive's §10 interpretation options**: this matches **Result C**
("targets enter candidate pool but B1 fails to promote them — candidate recall is
available, but B1 is not strong enough as second-stage ranking") most closely, and
partially **Result E** for the deeper buckets. It does not match Result A or B (no
"small pool, little damage, promising" story — the pool being enlarged barely moved
anything), and while §4 shows some rank damage exists, it is not the "widespread
regression" of Result D — it is two sessions out of 200, from a timing effect, not from
non-match demotion.

---

## 7. Browsing-specific detail (largest miss category, 23/54)

| N | Browsing targets entering pool | Browsing misses rescued |
|---|---|---|
| 20 | 8 / 23 | 0 |
| 50 | 18 / 23 | 0 |
| 100 | 21 / 23 | 0 |

**At N=100, 21 of 23 (91.3%) Browsing miss targets are physically present in the
candidate pool, and every single one of them is still unrescued.** This is the same
promotion-power limitation from §6, concentrated in the scenario with the most misses:
Browsing's vaguer opening query produces broader, more diffuse active-intent expressions
over the course of the conversation, which — per §6's mechanism — means more candidates
qualify as active matches and the partition has correspondingly less power to move any
one of them, including the target.

---

## 8. vs. Reference B (historical B1, N=10) — session-level comparison

| N | Sessions better than Ref B | Sessions worse than Ref B | Sessions same as Ref B |
|---|---|---|---|
| 20 | 0 | 2 | 198 |
| 50 | 1 | 2 | 197 |
| 100 | 1 | 2 | 197 |

The 2 "worse" sessions in every column are the same `public_0141`/`public_0148` pair
from §4 (their reciprocal rank is lower under the enlarged-pool simulation than it was
under the original N=10 B1 experiment, for the same early-stop reason). The 1 "better"
session at N=50/100 is `public_0064`. Pool enlargement, on top of the already-frozen B1
rule, therefore produced a **net negative** trade relative to Reference B on a per-session
basis (2 worse vs. 1 better) despite a net positive aggregate TechnicalScore move
(0.600502 → 0.603379) — the aggregate improvement is not evenly distributed and conceals
two individual session regressions.

---

## 9. Git status

```
 (starter/agent.py: no modification, byte-identical to HEAD)
?? markdowns/candidate_rescue_simulation_b1.md
(plus the pre-existing untracked markdowns/ files from prior FIX-01/FIX-01B0/FIX-01B1
 work and the previously-produced candidate_recall_audit_b0.md, unrelated to this pass)
```

HEAD remains `500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647`. No `git add`, `git commit`, or
`git push` was run.

---

## 10. Confirmation

```
NO CODE EDIT.  -- starter/agent.py untouched throughout; all reordering happened in an
                   external, disposable harness script that only ever called the
                   public respond() method and read connection/state, never wrote them.
NO COMMIT.     -- nothing staged or committed; HEAD unchanged.
NO TUNING.     -- only the three directive-specified pool sizes (20/50/100) were run;
                   no other value was tested, before or after seeing results.
```

## Summary for the next decision

Candidate-pool enlargement, combined with the exact frozen FIX-01B1 rule and nothing
else, rescued **1 of 54** original misses (net), while surfacing **2 session-level rank
regressions** relative to both B0 and the historical B1 N=10 experiment — not from the
previously-identified "non-active-match demotion" failure mode (100% of entering targets
were active matches), but from an early-stop timing effect once the pool is large enough
to surface a mediocre-rank match before a later, better one would have appeared. The
dominant finding is that most miss targets that *do* enter a larger pool (46/54 at
N=100, including 21/23 of the largest category, Browsing) are not promotable by this
specific binary partition rule, because too many competing active matches already sit
ahead of them. Per the directive, no fix is proposed, no pool size is recommended, and
B1 was not modified. Stopping for independent review.
