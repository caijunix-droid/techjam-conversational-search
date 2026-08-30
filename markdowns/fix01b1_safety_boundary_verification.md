# FIX-01B1 — Safety Boundary Verification

Produced per `FIX-01B1 — Independent Verification Findings.md` §10–§12 governance
instruction. Scope of this document: verify the reviewer's mathematical correction,
run the adversarial S1/S2 probes, run the public-set exposure audit, and correct one
reporting error. **No change was made to the B1 algorithm, no tuning was performed, no
commit or revert was made.**

---

## 0. Current candidate state (unchanged since the original handover)

```bash
shasum -a 256 starter/agent.py
  # a8ed56bd218682807192035c3178e217f05f7851d2164fccba69c064b2f02231
git diff --stat -- starter/agent.py
  # starter/agent.py | 36 +++++++++++++++++++++++++++++++++++-
  # 1 file changed, 35 insertions(+), 1 deletion(-)
```

The diff is byte-identical to the one recorded in
`markdowns/fix01b1_active_intent_ranking_handover.md` §4 — confirmed by re-running
`git diff` and comparing line counts and the exact patch text. No edit was made to
`starter/agent.py` during this verification pass.

```bash
python3 -m unittest discover -s tests -p 'test*.py'
# Ran 19 tests in 0.024s — OK   (13 pre-existing + 6 FIX-01B1 targeted, unchanged)
```

---

## 1. The reviewer's correction: verified TRUE

The original handover's §8 claim —

> the mechanism never demotes anything below its baseline position — it only promotes
> active-intent matches ahead of the point they'd otherwise sit at

— is **incorrect**, and is retracted. This was checked two ways.

### 1.1 Minimal mechanical check (the sort primitive alone)

```python
baseline_order = ['TARGET', 'B', 'C', 'DECOY']
active_matches = {'DECOY'}
result = list(baseline_order)
result.sort(key=lambda asin: asin not in active_matches)
# baseline:      ['TARGET', 'B', 'C', 'DECOY']
# after reorder: ['DECOY', 'TARGET', 'B', 'C']
# TARGET baseline rank: 1 -> post-reorder rank: 2
```

A stable partition that pulls one group in front of another necessarily pushes every
member of the *other* group back by however many items were promoted past it. If the
target is in the "no match" group and at least one "match" item sits below it in
baseline order, that item moves in front of the target — a real demotion. This is a
property of stable partitioning in general, independent of FTS5/BM25/this codebase.

### 1.2 Reproduced through the real `Agent` code path (not just the abstract sort)

Two synthetic-catalog probes, run against the actual `Agent` class and the actual FTS5
pipeline (`starter/agent.py`, uncommitted B1 patch in place):

**S1 — target is itself an active-intent match** (catalog: TARGET's title contains
"leather", D/B/C don't; active intent set to "leather" via a clarification answer):

```
S1 PURE BASELINE ORDER: ['D', 'TARGET', 'B', 'C']   TARGET baseline rank: 2
S1 (active intent = leather) ORDER: ['TARGET', 'D', 'B', 'C']   TARGET rank: 1
```

Rank improved (2 → 1). Matches the "improvement is possible" claim.

**S2 — target is NOT an active-intent match; a lower-ranked decoy is** (catalog:
TARGET/B/C generic, DECOY's title contains "leather"; active intent set to "leather"):

```
PURE BASELINE ORDER (no active constraint): ['TARGET', 'B', 'C', 'DECOY']
TARGET baseline rank: 1   DECOY baseline rank: 4

S2 (active intent = leather) ORDER: ['DECOY', 'TARGET', 'B', 'C']
TARGET rank after B1 reorder: 2   DECOY rank after B1 reorder: 1
```

Rank worsened (1 → 2). **This confirms the reviewer's finding is real, not merely
theoretical**: it reproduces through the actual `_active_expression()` /
`MATCH ... AND parent_asin IN (...)` / stable-sort code path exactly as shipped in the
uncommitted patch, not just in an isolated sort example.

---

## 2. Corrected invariant

Replacing the original handover's §3.1/§8 claim with the version verified above:

```
GUARANTEED (proven from evaluator + candidate-generation code, §3.1 of the original
handover — this half was correct and remains correct):
  candidate SET unchanged (pure reorder, no add/remove)
    => HitRate@10 unchanged
    => first-hit turn unchanged
    => MTTC / Efficiency unchanged

NOT GUARANTEED (the original handover's error):
  target rank cannot worsen
  MRR cannot worsen
  TechnicalScore cannot worsen

CONDITION under which a demotion occurs (derived and confirmed by S2 above):
  target is NOT itself an active-intent match at the hit turn
  AND at least one other candidate that IS an active-intent match
      is ranked below the target in the pre-reorder (baseline BM25) order
  => target's rank worsens by exactly the number of such candidates
     (each one moves from below the target to above it)

CONDITION under which the target cannot be harmed:
  target IS itself an active-intent match at the hit turn
      (target can only move toward rank 1, never worse than its baseline rank,
       since it is already in the promoted group)
  OR no active-intent expression exists at that turn
      (no reorder happens at all — output is the untouched baseline order)
  OR an active-intent expression exists but no other candidate matches it
      (active_matches is empty or contains only the target — no reorder / no-op)
```

The zero-regression result on the public 200-session set is therefore an **empirical
finding about this dataset**, not a mathematical property of the algorithm. §3 below
establishes why it held here.

---

## 3. Public benchmark exposure audit (directive §11)

Every one of the 200 public sessions was replayed through the real `Agent` (same
uncommitted B1 patch). At the exact turn each session's target first entered the
top-10 (the only turn that determines `best_rank`/MRR), the pre-reorder baseline order
and the active-match set were reconstructed by calling the same internal methods
(`_build_query`, `_active_expression`) and the same SQL pattern `respond()` itself uses,
read-only, immediately after the real `respond()` call for that turn — no algorithm
change, just recomputing values `respond()` already computed internally but didn't
expose. This is safe because state is not mutated between `respond()` returning and the
recomputation (verified earlier: the pipeline is fully deterministic — see original
handover §10).

```
Sessions with a hit (target reached top-10 within 10 turns): 146 / 200   (= HR@10 0.73)
Sessions with no hit (excluded — no rank exists to demote):    54 / 200

Of the 146 hit sessions, classified at their hit turn:

  target_is_active_match             140   (95.9%)  -- structurally cannot be demoted
  no_active_constraint                  6   ( 4.1%)  -- no reorder occurs, output untouched
  active_constraint_no_competitor_below  0   ( 0.0%)
  dangerous_configuration                0   ( 0.0%)  -- the exposed case from §2
```

**Zero of the 146 hit sessions were ever in the dangerous configuration** (target not
an active match, with a competing active match ranked below it). This directly answers
the reviewer's §11 question:

> was the zero-regression result because (A) targets almost always match active intent,
> or (B) the dangerous configuration just happened not to occur?

**Answer: (A).** 140/146 hit sessions had the target itself lexically matching the
active-intent expression at the hit turn — the dangerous configuration (B) never arose
in this dataset, not because it was narrowly avoided, but because the population of
"target is an active match" essentially crowded it out.

### 3.1 Why (A) holds — a structural cause, not a coincidence

Checked `data/public_set.jsonl` directly: none of the 200 samples carry a pre-embedded
`intent_card`/`behavior` field (`has_intent_card_and_behavior: 0/200`). Every sample's
customer-facing constraints are therefore derived at evaluation time by
`evaluator.local_evaluator.materialize_hidden_fields()` → `intent_card(product)`, where
`product` is looked up as `products[target]` — **the target's own catalog row**. That
function pulls its candidate constraint strings directly from the target's own
`features`/`details`/title/price fields (`evaluator/local_evaluator.py:52-71`). This was
already noted for a related reason in `MASTER_HANDOVER.md` §3.3 (FIX-01A's rejection),
which independently found the same root property from a different angle.

Consequence: whatever the simulated customer says as "active intent" is, by
construction, lexically drawn from the target's own listing text for essentially every
public sample. That is precisely why `target_is_active_match` dominates (140/146) — it
is close to a byte-level artifact of how the public evaluator constructs its
conversations, not evidence that a real customer's phrasing would coincidentally match
the target's catalog text at similar rates.

**This is confirmed for the public evaluator only.** Whether the private/held-out
evaluator constructs its `intent_card`/`behavior` the same way is not verified here —
`evaluator/local_evaluator.py` is the public evaluator's own code, and nothing in this
repository confirms the private harness reuses the identical `intent_card()` function.
Treat generalization to the private set as **unverified, not established, and not
ruled out** — this audit only establishes the mechanism behind the public-set result,
not a guarantee that it transfers.

---

## 4. Reporting correction (directive §6 of the review)

The original handover's §7 stated "Buying (7 of 9 changed sessions)" and "Intent
Override (1 of 9)", which sums to 8, not 9. Recounting the §8 session table directly:

```
Buying:            public_0042, 0053, 0065, 0101, 0107, 0132, 0135, 0148   = 8 sessions
Intent Override:   public_0084                                              = 1 session
Total:                                                                      = 9 sessions
```

**Corrected**: Buying — 8 of 9 changed sessions; Intent Override — 1 of 9. This was a
counting/documentation error in prose only; the underlying session table, the scenario
MRR deltas, and all benchmark numbers in the original handover were already correct and
require no further change (the reported Buying MRR delta of +0.014707 is consistent
with 8 Buying rank improvements, not 7, which is itself evidence the error was in the
prose summary, not the computation).

---

## 5. Test status (unchanged)

```bash
python3 -m unittest discover -s tests -p 'test*.py'
# Ran 19 tests in 0.024s — OK
```

19/19 — 13 pre-existing + 6 FIX-01B1 targeted tests from
`tests/test_fix01b1_active_intent_ranking.py`. No test was added, removed, or modified
during this verification pass; the S1/S2 adversarial probes above were run as standalone
scratch scripts (not added to the test suite), since the directive scoped this pass to
verification/reporting, not implementation changes.

---

## 6. Git status

```
 M starter/agent.py
?? markdowns/fix01b1_safety_boundary_verification.md
?? tests/test_fix01b1_active_intent_ranking.py
(plus the pre-existing untracked markdowns/ files from prior FIX-01/FIX-01B0/FIX-01B1
 work, unrelated to this verification pass)
```

`starter/agent.py`'s working-tree diff is unchanged from the original handover (§0
above). No `git add`, `git commit`, or `git push` was run. HEAD remains at `500fe7b`.

---

## 7. Status

```
DO NOT COMMIT.     -- honored, nothing committed.
DO NOT REVERT.      -- honored, agent.py unchanged from the B1 patch.
DO NOT MODIFY B1.   -- honored, zero edits to starter/agent.py this pass.
DO NOT TUNE.        -- honored, no parameters exist to tune and none were introduced.
```

Findings for the reviewer's KEEP / REJECT / INVESTIGATE decision:

- The reviewer's mathematical correction is **confirmed true**, reproduced both as a
  minimal abstract case and through the real `Agent` code path (S1/S2).
- The corrected invariant (§2) replaces the false one from the original handover.
- The public zero-regression result is explained, not just observed: 140/146 hit
  sessions had the target as its own active-intent match (structurally un-demotable),
  6/146 had no active constraint at the hit turn (no reorder occurs), and the dangerous
  configuration occurred in **0/146** sessions.
- That 140/146 figure is traced to a specific, cited mechanism in the public evaluator
  (`intent_card()` deriving customer constraints from the target's own listing text) —
  not asserted as a general property of the ranking rule, and explicitly **not**
  extended as a claim about the private set.
- The Buying/Intent-Override session count in the original handover's prose is
  corrected (8/9, not 7/9); no benchmark number changes as a result.

This document does not issue a KEEP/REJECT/INVESTIGATE classification — per the
governance instruction, that decision is left to independent review. Stopping here.
