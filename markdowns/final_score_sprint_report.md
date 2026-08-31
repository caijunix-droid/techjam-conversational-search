# FINAL SCORE SPRINT REPORT

Written 2026-08-31. Executes `FINAL SCORE SPRINT — LAST EVIDENCE-CONTROLLED
EXPERIMENT.md` exactly. **Read-only audit only — no production edit, no
stage, no commit, no push, at any point in this pass.**

```text
CLASSIFICATION: NO SAFE EXPERIMENT FOUND
```

Per the authorization's own §2/§7/§16: this is a valid, successful
outcome, not a failure to complete the sprint. The audit did not surface a
recurring structural property that the existing signal hierarchy (term
coverage → slot coverage → phrase coverage → BM25) doesn't already
capture — and inventing one anyway, absent that evidence, is exactly the
overfitting risk the authorization warns against in its own §5/§6.

---

## A. BASELINE

```bash
git status --short
git rev-parse HEAD
git rev-parse origin/main
```
```text
HEAD:        ce7114904b8cb97f6223e7419ef3923cce178a90
origin/main:  ce7114904b8cb97f6223e7419ef3923cce178a90   (match)

git status --short:
?? markdowns/MASTER_HANDOVER_ROUND3.md
?? markdowns/fix04a_commit_and_merge_reconciliation.md
?? markdowns/fix04a_implementation_handover.md
?? markdowns/fix05_commit_push_report.md
?? markdowns/fix05_implementation_handover.md
?? markdowns/fix05p0_exact_phrase_tiebreak_simulation.md
```

Only known untracked documentation — acceptable per the authorization's
own §3. `python3 -m unittest discover -s tests -p 'test*.py'` re-run: 54/54
pass. The previously saved, SHA-verified FIX-05 production `results.json`
(captured immediately after the FIX-05 implementation was verified; its
`starter/agent.py` SHA — `ab99c72e...` — matches the current working
tree exactly) was reused as ground truth for the session-level audit below,
per the authorization's own instruction not to burn time re-running the
full evaluator unnecessarily.

```text
FIX-05 (ce71149): HR@10 0.880000, MRR 0.567583, MTTC 5.495000,
TechnicalScore 0.720375, 176/200 hits, 24/200 misses.
```

---

## B. RESIDUAL AUDIT

Method: replayed all 200 sessions through the real, unmodified production
`Agent` (`starter.agent.Agent`, imported directly — not reconstructed),
reusing the evaluator's own turn-generation helpers verbatim
(`materialize_hidden_fields`, `initial_message`, `customer_reply`). For
each miss, captured the target's final-turn (turn 10) retrieval depth,
term/slot/phrase coverage, and the Top10-boundary candidate's
corresponding values, using production's own installed methods
(`_active_terms`, `_matchable_slots`) plus the identical ranking SQL
already in `starter/agent.py` for independent recomputation. Same
methodology previously validated with 0 mismatches against production in
the FIX-05P0 pass.

### B1. HR@10 headroom — 24 remaining misses

```text
depth bucket distribution (target's rank if retrieved, widest available):
  <=10:            0
  11-20:           6
  21-50:           0
  51-100:         13
  101-500:         4
  >500/absent:      1
  ------------------
  entirely outside internal Top-50 pool:  20 / 24  (83%)
```

```text
scenario distribution: buying=9, browsing=8, intent_override=5, boundary=2
```

**The dominant residual failure mode (20/24, 83%) is candidate-generation
depth, not ranking.** These targets never enter the Top-50 pool the
reranking tiers operate on at all — no amount of reordering within that
pool can reach them. This is the exact mechanism, and the exact
already-measured conclusion, of the closed `FIX-02-P0` branch: *"A
counterfactual depth sweep (Top100/Top500) showed only 3/39 rescuable and
real regression risk at Top500 — ruled out 'just widen the pool.'"* No new
evidence was found in this pass that changes that conclusion — if
anything, the proportion of depth-blocked misses is now even higher (83%
vs. the prior pass's roughly one-third), since term/slot/phrase reranking
has already cleared out the misses that *were* reachable. Widening depth
remains a closed branch per the authorization's own §6 (a parameter
variation on an already-rejected mechanism, not a materially different
one).

Of the remaining **4 misses whose target is inside the Top-50 pool**
(`public_0041`, `public_0081`, `public_0096`, `public_0137`) — all 4 have
`term_coverage = 1.0` and `slot_coverage = 1.0`, and **all 4 are tied with
the Top10-boundary competitor on every single existing signal, including
phrase coverage**:

```text
public_0041  rank=11  target=(1.0, 1.0, 1.0)  boundary=(1.0, 1.0, 1.0)
public_0081  rank=13  target=(1.0, 1.0, 1.0)  boundary=(1.0, 1.0, 1.0)
public_0096  rank=20  target=(1.0, 1.0, 0.5)  boundary=(1.0, 1.0, 0.5)
public_0137  rank=18  target=(1.0, 1.0, 1.0)  boundary=(1.0, 1.0, 1.0)
```

Zero of the 4 have any remaining discriminating information within the
existing hierarchy — every signal FIX-04A/FIX-05 already compute is
exhausted for these specific groups.

### B2. MRR headroom — 176 hits

```text
rank 1: 90   rank 2: 17   rank 3: 16   rank 4: 17   rank 5: 4
rank 6: 15   rank 7:  7   rank 8:  4   rank 9: 3    rank 10: 3

hits not already at rank 1: 86 / 176
```

Per the authorization's own explicit caution ("do NOT invent a reranking
signal merely because this operation is mathematically safe"), the 86
rank>1 hits were further characterized: for each, every candidate ranked
above the target was checked against target's own
`(coverage, slot_coverage, phrase_coverage)` tuple.

```text
ALL candidates above target are FULLY TIED on every existing signal:  76 / 86  (88%)
ALL candidates above target STRICTLY DOMINATE on the existing hierarchy: 2 / 86
MIXED (some tied, some dominate):                                        8 / 86
```

**This is the same phenomenon as B1, just observed from the hit side.**
88% of the theoretical MRR headroom sits inside groups where term, slot,
and phrase coverage are already identical across every competing
candidate — pure BM25-order coincidence, with zero remaining information
in the current signal stack to break the tie correctly (as opposed to
arbitrarily). The 2 "strictly dominated" cases
(`public_0120`, `public_0145`) are sessions where higher-ranked candidates
legitimately have *better* coverage/slot/phrase values than the target —
reordering these would directly *contradict* the existing, already-earned
hierarchy, which the authorization explicitly prohibits ("Existing
hierarchy must remain respected unless the new hypothesis explicitly and
defensibly changes it").

### B3. MTTC headroom — first-hit-turn distribution

```text
turn  1: 31   turn 2: 33   turn 3: 22   turn 4: 14   turn 5:  6
turn  6:  1   turn 7: 16   turn 8: 19   turn 9: 24   turn 10: 10
```

Of the 145 hits at turn > 1: **56 had the target already present in the
Top-50 pool at turn 1** (visible early, but not yet ranking-competitive —
additional disclosed detail was needed to accumulate enough active-term/
slot/phrase coverage to climb into Top10); **89 did not even have the
target in the Top-50 pool until a later turn** (the same candidate-
generation-depth phenomenon as B1, resolving itself naturally as the query
expression accumulates more disclosed terms).

Per the authorization's own caution ("MTTC optimization can alter
conversation stopping and future state trajectory" and "do NOT assume
earlier is always safely achievable"), this pattern reads as normal,
expected dialogue behavior — early turns genuinely carry less information,
so a genuinely earlier rank is not "owed" to these sessions by any known
defect. No conversation-state defect (as distinct from expected,
information-limited early turns) was found.

### B4. Summary — the single most important observed residual failure class

**One unified phenomenon accounts for nearly all remaining headroom in
both the miss population (B1) and the hit population (B2): once term
coverage, slot coverage, and phrase coverage all saturate at their maximum
achievable value for a tied group, the current mechanism's only remaining
discriminator is raw BM25 score — and there is no fourth signal already
computed, or newly discovered in this audit, that distinguishes correctly
within those exact groups.**

---

## C. HYPOTHESIS

**None proposed.**

The read-only audit was searched explicitly for a signal meeting the
authorization's own bar (§5): a recurring structural property, a
candidate-level feature that consistently distinguishes correct products
from higher-ranked distractors, a conversation-state defect affecting a
general class of interactions, or a safe mathematically-constrained
reordering. What was found instead, directly measured rather than assumed:

- The dominant miss failure mode (83%) is not a ranking problem at all —
  it is unreachable by any reordering mechanism, and the one lever that
  *could* reach it (candidate-generation depth) is a closed branch with
  already-measured regression risk exceeding its benefit.
- The dominant MRR headroom (88%) sits in groups that are *already fully
  saturated* on every signal the existing hierarchy computes — meaning any
  new discriminator would necessarily have to reach for something finer
  than term/slot/phrase presence to separate these specific candidates.
  The two most obvious next candidates for such a finer signal — IDF/term-
  rarity weighting and deeper field-coherence — are **both explicitly
  listed as closed branches in this very authorization's §6**
  ("ordinary token-IDF as a solution to candidates matching the same
  complete token set"; "simple field-placement coherence"). No materially
  different mechanism (as opposed to a parameter variation on those) was
  identified.
- The remaining, smaller "dominated" population (§B2) is cases the
  existing hierarchy has already correctly resolved — touching those would
  violate the hierarchy, not extend it.

Manufacturing an experiment here — inventing a fourth discriminator against
groups already shown to be identical on every existing measured axis —
would have no conceptual basis for generalizing to the private/held-out
set beyond "it happened to break this specific tie in this specific
catalog," which is precisely the bad-evidence pattern the authorization
itself calls out in §5 ("these N public sessions need this").

**Generalization rationale for stopping, not proceeding**: a mechanism
with no evidence of a recurring, catalog-independent structural basis is,
by the authorization's own definition, not distinguishable from public-set
overfitting.

---

## D. SYNTHETIC / ADVERSARIAL RESULTS

N/A — no hypothesis was frozen, so there is nothing to falsify.

---

## E. SIMULATION

N/A — no hypothesis reached this stage.

---

## F. IMPLEMENTATION

N/A. No production file was touched.

---

## G. TESTS

Re-run for baseline confirmation only (§0 above): 54/54 pass, 0 failures,
0 errors. No new tests were added — nothing new to test.

---

## H. PRODUCTION EVALUATOR

Not re-run beyond the baseline confirmation already reported in §A — no
candidate mechanism exists to evaluate. The FIX-05 numbers already on
record (`ce71149`) stand unchanged:

```text
HR@10          0.880000
MRR            0.567583
MTTC           5.495000
Efficiency     0.550500
TechnicalScore 0.720375
```

Runtime: not independently re-measured in this pass (no code change to
measure); the existing, already-reported figure (~84.7–86.8s / 200
sessions) stands.

---

## I. EQUIVALENCE

N/A — no implementation exists to compare against a simulation.

---

## J. GIT STATUS — proof no commit/push occurred

```bash
git status --short
git rev-parse HEAD
```
```text
?? markdowns/MASTER_HANDOVER_ROUND3.md
?? markdowns/fix04a_commit_and_merge_reconciliation.md
?? markdowns/fix04a_implementation_handover.md
?? markdowns/fix05_commit_push_report.md
?? markdowns/fix05_implementation_handover.md
?? markdowns/fix05p0_exact_phrase_tiebreak_simulation.md

HEAD: ce7114904b8cb97f6223e7419ef3923cce178a90  (unchanged throughout this pass)
```

No `git add`, no `git commit`, no `git push` was executed at any point.
`starter/agent.py` and every test file are byte-identical to the committed
`ce71149` state (re-confirmed via SHA256 in §A). Everything produced in
this pass is external scratch (`final_sprint_audit.py`,
`final_sprint_analysis.py`, `final_sprint_mrr_headroom.py`, and their JSON
outputs), session-local and not part of git history.

---

## K. CLASSIFICATION

```text
NO SAFE EXPERIMENT FOUND
```

The remaining public-set headroom (24 misses, 86 sub-optimally-ranked
hits) is real but is not, on the evidence gathered, addressable by a
generalizable mechanism distinct from branches this project has already
investigated and closed (widen retrieval depth; IDF/term-rarity weighting;
field-coherence). Per §16 of the authorization: this outcome — proving
that the remaining headroom does not justify risking the locked 88.0%
build — is the defined success condition for this sprint, not a shortfall.
`ce71149` remains production until independent review says otherwise.
