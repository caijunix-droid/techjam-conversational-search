# Second-Stage Ranking Separability Audit

Produced per `TECHJAM — SECOND-STAGE RANKING SEPARABILITY AUDIT.md`. Scope: measure
whether richer active-intent signals (beyond FIX-01B1's binary match) carry enough
discriminatory power to separate targets from competitors inside a larger BM25
candidate pool. **Measurement only — no `starter/agent.py` edit, no scored
implementation, no candidate-pool production change, no B1 modification, no tuning,
nothing committed.**

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

Matches committed B0 exactly. No file under `starter/` was written to at any point.

---

## 1. Candidate population and methodology

All 200 public sessions were replayed once through the real, unmodified B0
`Agent.respond()`, called with `top_k=100` (a legitimate parameter of the shipped
signature, used purely as an external measurement depth — the same technique validated
in `markdowns/candidate_recall_audit_b0.md` and `markdowns/candidate_rescue_simulation_b1.md`).
N=50 and N=100 pools were taken as prefixes of this single top-100 result (validated
strict-prefix equivalence to independent `top_k=N` queries in prior audits).

**No ground truth was used to construct any diagnostic.** Every signal below is computed
only from `state.active_slots` (read from the live B0 `SessionState` the committed code
itself populates), the visible catalog FTS index, and the existing BM25 machinery.
`target` (the ground-truth `parent_asin`) is used **only afterward**, to look up where it
landed in each diagnostic's pure ordering — never as an input to any diagnostic's score.

Intent Override eligibility gating (`override_applied`) matches the same corrected
methodology established in the two prior audits — pre-override turns are never counted.

**Two-tier evaluation, matching the directive's own emphasis on regression exposure:**
- For each of the **54 original B0 misses**: best (lowest) rank achievable under a given
  diagnostic's pure ordering, scanning across all eligible turns (mirrors the
  "best-across-eligible-turns" methodology from the recall audit).
- For each of the **146 original B0 hits**: rank under the same diagnostic's pure
  ordering, evaluated **only at the real official hit turn** (the turn the actual system
  stopped and scored at) — this directly measures "would this diagnostic, if it had been
  used to reorder that exact candidate list, have broken a session that currently works."

---

## 2. Diagnostics measured (as specified, no others)

- **A — Binary active match**: candidate matches ≥1 active term. Pure ordering: matches
  first (stable, baseline order preserved within each group) — this is exactly the
  frozen FIX-01B1 rule, included here as the reference point.
- **B — Active-term coverage**: `(distinct active terms matched by candidate) / (distinct
  active terms)`, ordered descending, baseline-order tiebreak. No weights.
- **C — Active-slot coverage**: for each `active_slots` key with ≥1 usable tokenized term
  ("matchable slot"), whether the candidate matches ≥1 of that slot's terms;
  `(slots satisfied) / (matchable slots)`, ordered descending, baseline-order tiebreak.
  No slot weights.
- **D — Active-only BM25**: raw `bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0)` score
  (production's own field weights, unchanged) computed against the active-intent
  expression only, ordered by that score (more negative = better in SQLite FTS5's
  convention, verified against production's own `ORDER BY bm25(...)` usage), baseline
  tiebreak. Not combined with baseline BM25.

Each is an **oracle-style, pool-restricted-only reorder** — the candidate set itself is
never changed, only its order, exactly mirroring how FIX-01B1 itself operates.

---

## 3. Results — 54-miss oracle rescue vs. 146-hit regression exposure

| Diagnostic | N | Rescued / 54 misses | Regressed / 146 hits | Net |
|---|---|---:|---:|---:|
| A — Binary active match | 50 | 1 | 0 | +1 |
| A — Binary active match | 100 | 1 | 0 | +1 |
| B — Active-term coverage | 50 | **15** | **0** | **+15** |
| B — Active-term coverage | 100 | **18** | 2 | **+16** |
| C — Active-slot coverage | 50 | 9 | 0 | +9 |
| C — Active-slot coverage | 100 | 9 | 0 | +9 |
| D — Active-only BM25 | 50 | 17 | **28** | **−11** |
| D — Active-only BM25 | 100 | 17 | **42** | **−25** |

**Diagnostic A (binary match) reproduces exactly the same 1/54 rescue count found in the
independent `candidate_rescue_simulation_b1.md` audit** (same session, `public_0064`) —
a direct cross-check confirming this harness's methodology agrees with the prior,
separately-built one.

**Diagnostic D (raw active-only BM25) is disqualified by the directive's own stated
test**: "A diagnostic that rescues 20 misses but destroys 30 existing hits is not
useful." At N=100 it rescues 17 but destroys 42 — worse than the threshold example given
in the directive, net strongly negative. At N=50 it is still net negative (17 rescued vs.
28 destroyed). This is a real, measured finding, not a hypothetical: raw BM25 magnitude
computed against a short, often single- or few-term active expression is not a stable
enough signal to reorder by directly — it appears to reward candidates with an unusually
strong match on one narrow term over candidates (including the actual target) with
broader but individually weaker relevance.

**Diagnostic B (active-term coverage — a fraction, no ground truth, no weights) is the
standout result**: rescues up to 18/54 (33.3%) misses at N=100 while damaging only 2/146
(1.4%) existing hits, and rescues 15/54 (27.8%) with **zero** damage at N=50. This is an
order of magnitude more rescue power than the binary signal (A) actually shipped in
FIX-01B1, at a regression cost close to zero.

**Diagnostic C (active-slot coverage) is the safest of the three richer signals** — zero
regressions at either N — but weaker than B, rescuing 9/54 (16.7%) at both N=50 and
N=100.

---

## 4. Representative per-session examples (directive §4 format)

| sample_id | scenario | N | baseline pos. | A (binary) rank | B (term cov.) rank | C (slot cov.) rank | D (active BM25) rank |
|---|---|---|---|---|---|---|---|
| public_0035 | boundary | 50 | 14 | 14 | **10 (rescued)** | 10 (rescued) | 21 |
| public_0035 | boundary | 100 | 14 | 14 | **10 (rescued)** | 10 (rescued) | 35 |
| public_0028 | buying | 100 | 92 | 92 | **4 (rescued)** | 77 | 18 |
| public_0011 | browsing | 50 | 20 | 20 | 13 | 19 | **11** |
| public_0064 | intent_override | 50 | 22 | **7 (rescued)** | **7 (rescued)** | **7 (rescued)** | **6 (rescued)** |

`public_0028` is the clearest single illustration of the audit's central finding:
binary match leaves the target completely stuck at rank 92 (it's *an* active match, but
so are ~91 other candidates ranked ahead of it — the same "block promotion, no internal
ordering" limitation documented in `markdowns/candidate_rescue_simulation_b1.md` §6),
while term-coverage — which can distinguish a candidate matching 3 of 3 active terms
from one matching only 1 of 3 — resolves that same block down to rank 4.

---

## 5. Scenario breakdown, N=100 rescue counts

| Diagnostic | Boundary (3) | Browsing (23) | Buying (17) | Intent Override (11) |
|---|---|---|---|---|
| A — Binary | 0 | 0 | 0 | 1 |
| B — Term coverage | 1 | **8** | 6 | 3 |
| C — Slot coverage | 1 | 4 | 2 | 2 |
| D — Active BM25 | 0 | **9** | 6 | 2 |

---

## 6. Browsing deep-dive (directive §6 — largest miss category, 23/54)

```
Binary match (A):        0 / 23 rescued
Active-term coverage (B): 8 / 23 rescued  -> public_0015, 0016, 0040, 0092, 0120, 0127, 0172, 0184
Active-slot coverage (C): 4 / 23 rescued  -> public_0015, 0040, 0127, 0184
Active-only BM25 (D):     9 / 23 rescued  -> public_0019, 0040, 0081, 0115, 0120, 0127, 0170, 0172, 0184
```

**Answer to the directive's §6 question**: Browsing does **not** fail because "all
candidates have similar lexical coverage" — richer match-strength signals (B, D) do
separate the target from competitors in over a third of Browsing misses (8–9 of 23).
It was specifically the binary partition's block-promotion behavior (§4's `public_0028`-
style mechanism, documented at scale in the prior rescue-simulation audit) that failed to
exploit separability that measurably exists. This directly overturns the plausible
alternative explanation raised in the rescue-simulation audit ("Browsing's vaguer opening
query gives BM25 less to work with") — the issue was not an absence of signal, but the
binary rule's inability to use the graded signal that was present.

---

## 7. Numeric / budget diagnostic

Replayed all 200 sessions tracking every turn where `state.active_slots["budget"]` was
set, and attempted to extract a numeric dollar threshold via `\$\s?(\d+(?:\.\d+)?)`.

```
Sessions with an active budget-classified slot at any point: 2 / 200
  public_0086 (browsing)
  public_0105 (browsing)

Of those 2, sessions with an extractable numeric threshold: 0 / 2
```

**Both are false-positive classifications, not genuine numeric constraints** — verified
by reading the actual disclosed text in both cases:

- `public_0086`, turn 10: `"...Long lasting 80D memory foam insole provides superior
  cushioning and padding, feels like ergonomic pillows **under** your feet..."` — the
  word "under" here is physical/spatial ("pillows under your feet"), not a price ceiling.
  Production's `BUDGET_RE` (`starter/agent.py`) matches the bare word "under" regardless
  of context, so `classify()` filed this under `budget`.
- `public_0105`, turns 5–10: `"...The High Quality Activewear is perfect for Fitness
  Enthusiasts and Everyday Athleisure as it is **Affordable** a..."` — "Affordable" is a
  brand-description adjective from the product's own store description (per
  `MASTER_HANDOVER.md`'s and prior audits' established finding that `intent_card()`
  derives constraint strings from the target's own catalog text), not a customer-stated
  numeric budget.

**Conclusion**: the public 200-session set contains **zero sessions with a genuine,
numerically-parseable active budget constraint**. The target-vs-pool price-satisfaction
comparison the directive asks for (§7) could not be computed — there is no denominator.
This is consistent with, and adds direct evidence for, `MASTER_HANDOVER.md` §5 item 2
("Budget/price is never enforced against the catalog's numeric price field... a stated
'under $80' becomes loose keyword noise, not an actual filter") — the present audit shows
the problem starts even earlier: on this public set, the simulated customer essentially
never states a numeric budget constraint that the current classifier extracts correctly
in the first place, so there is nothing here for even a hypothetical numeric filter to
act on. This is a public-set-specific observation; nothing here establishes whether the
private set contains genuine numeric budget disclosures.

---

## 8. Methodology limitations (as required, stated explicitly)

- **Best-across-eligible-turns for misses vs. single-turn for hits is an intentional
  asymmetry**, not an oversight: it mirrors what "rescued" vs. "regressed" actually mean
  operationally — a miss has no real stopping turn to anchor to, so its best opportunity
  across the conversation is the relevant question; a hit already has one fixed,
  real stopping turn, and that is the only turn whose reordering risk matters for whether
  today's working session would still work.
- **Diagnostics B and C use fractions, not raw counts, and are therefore already a small
  step past a strictly "binary-only" measurement** — computing coverage necessarily
  requires per-term match sets, which required issuing one small FTS `MATCH` query per
  active term per turn (up to 40, though real sessions typically produced far fewer active
  terms in practice — not separately tallied in this pass). This is a measurement
  necessity, not a scored production mechanism; it was never written into
  `starter/agent.py`.
- **The two-diagnostic-agreement sanity check (A vs. the independent rescue-simulation
  audit) covers only diagnostic A** — B, C, and D have no independent prior audit to
  cross-validate against; their internal consistency was checked only by code review of
  this harness and the smoke test on 8 sessions (§ below), not by a second, independently
  written implementation.
- **`D`'s regression count is sensitive to how ties/absence are broken** — candidates with
  no active-BM25 score (not matched by the active expression at all) were placed after all
  matching candidates, tie-broken by baseline order. This is a specific, stated design
  choice for the diagnostic's oracle ordering, not the only reasonable one; a different
  placement rule for non-matching candidates could change D's exact numbers, though it is
  unlikely to reverse the qualitative finding (D's core problem — over-rewarding a narrow
  single-term match — is about the matching candidates' relative order, not the
  non-matching ones' placement).
- **Slot-term "usable" definition (§C) does not special-case `budget`** — a budget slot's
  tokenized terms (e.g. `["under", "80"]` per §7) are treated identically to any other
  slot's terms for coverage purposes; this was a deliberate choice to match the
  directive's literal instruction not to special-case slots in diagnostic C, with the
  numeric-specific treatment reserved for §7's separate diagnostic.
- **This is single-run, deterministic data** (SQLite FTS5 MATCH and Python's stable
  `sorted()` are both deterministic, no randomness anywhere in the harness); a second
  independent run was not executed for this specific audit (unlike the prior
  rescue-simulation audit, which re-ran twice) given the harness's determinism was already
  established for the shared underlying data pipeline (`Agent`, catalog, evaluator
  helpers) in that prior work. Flagging this as a difference from the prior audit's
  practice, not a claim that determinism was independently re-verified here.
- **A brief harness smoke test was run on the first 8 samples before the full 200-session
  run**, to catch implementation bugs early (visible variation across diagnostics, plausible
  rank values) — this is a code-sanity check, not a statistical validation.

---

## 9. Git status

```
 (starter/agent.py: no modification, byte-identical to HEAD)
?? markdowns/second_stage_ranking_separability_audit.md
(plus the pre-existing untracked markdowns/ files from prior FIX-01/FIX-01B0/FIX-01B1
 work and the prior candidate_recall_audit_b0.md / candidate_rescue_simulation_b1.md,
 unrelated to this pass)
```

HEAD remains `500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647`. No `git add`, `git commit`, or
`git push` was run.

---

## 10. Confirmation

```
NO CODE EDIT.   -- starter/agent.py untouched throughout; all diagnostics computed in a
                    disposable external harness that only called the public respond()
                    method and read connection/state, never wrote them.
NO COMMIT.      -- nothing staged or committed; HEAD unchanged.
NO TUNING.      -- exactly the four predefined diagnostics (A-D) were measured, at
                    exactly the two predefined pool sizes (50/100); no threshold,
                    weight, or combination was invented or searched after seeing results.
```

## Summary for the next decision

The audit's hypothesis is **confirmed, not merely plausible**: binary active-match (the
signal FIX-01B1 actually shipped) discards substantial usable discriminatory information.
Active-term coverage (signal B) — a simple, weight-free fraction — rescues up to 16x more
of the 54 original misses (18 vs. 1) than the binary signal, at a cost of only 2/146
(1.4%) regressed hits at N=100, and **zero** regressed hits at N=50. Active-slot coverage
(C) is even safer (zero regressions at either N) but weaker (9/54). Raw active-only BM25
(D) is measurably unsafe by the directive's own stated test and should not be pursued
further as a standalone signal. Browsing, the largest miss category, is shown to have
real exploitable separability (8–9/23 rescued by B/D) that the binary rule simply could
not access. Per the directive, no new ranker is authorized by this document — these are
offline separability findings only. Stopping for independent review.
