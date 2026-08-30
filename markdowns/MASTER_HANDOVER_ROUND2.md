# MASTER HANDOVER — ROUND 2 (read this first, then `MASTER_HANDOVER.md` for static background)

Written 2026-08-31, same session as round 1 but much later. Purpose: same as round 1 —
let a **fresh Claude session** (or any other reader) pick up this project with zero
re-derivation and zero hallucination risk. Everything under "Verified fresh in this
pass" below was re-run via actual commands immediately before writing this document, not
recalled from earlier conversation turns. Everything under "Carried forward from prior
work in this session" was verified carefully when originally produced (see the cited
markdown files for the actual command output) but was **not** re-run in this exact pass
— treat those numbers as trustworthy-but-not-freshly-re-verified-this-second, per this
project's own established discipline.

**If you are a new session reading this: `MASTER_HANDOVER.md` (round 1) still correctly
describes the repo's purpose, remotes, data provenance, and organizer-material context —
none of that changed. This document exists because everything about the code and
benchmark state has moved on substantially since round 1, and round 1 is now stale on
those specific points.**

---

## 0. The one-sentence version

Round 1 ended with `starter/agent.py` clean at committed `500fe7b` (FIX-01B0). Since
then, a chain of measurement-only audits (never touching code) built the evidence for a
second-stage ranker, which was then **actually implemented, uncommitted, in
`starter/agent.py` right now** — raising the local benchmark from **HR@10 0.73 →
0.805, TechnicalScore 0.598 → 0.654** — verified by the real evaluator, not simulation.
It is fully tested, fully verified, **and still uncommitted**, pending your decision on
one flagged runtime concern (~1.6–1.9x slower than committed B0) and an explicit
commit go-ahead.

---

## 1. Verified fresh in this pass

```bash
git log --oneline -7
```
```
500fe7b FIX-01B0: decouple active intent from retrieval evidence
037b52d Revert "Fix budget parsing and vague-answer handling in agent."
c6461c4 added markdowns for Claude
068e8fa Fix budget parsing and vague-answer handling in agent.
9b5fc2f Add improved shopping agent with dialog memory + live demo script
9a35be5 Clarify participant model API costs
2a6cc8e Publish conversational search challenge
```

```bash
git rev-parse HEAD
  # 500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647   (unchanged since round 1)
git rev-list --left-right --count origin/main...main
  # 0  0    (still in sync, still nothing new pushed)
```

**`starter/agent.py` is NOT at the committed baseline right now** — it has an
uncommitted working-tree patch applied:

```bash
git status --short -- starter/agent.py
  #  M starter/agent.py
shasum -a 256 starter/agent.py
  # e3f324caf8e6c940d44293beffd6a71df489f56564639c5af800d70d2975b9b5
git diff --stat -- starter/agent.py
  # 1 file changed, 45 insertions(+), 2 deletions(-)
```

This is the **FIX-01B2** patch (active-term-coverage second-stage ranking — see §3).
This SHA is committed-nowhere; it exists only in the working tree.

```bash
python3 -m unittest discover -s tests -p 'test*.py'
  # Ran 22 tests in 0.023s — OK
python3 -m evaluator.local_evaluator
```
```
hit_rate_at_10           = 0.805
mrr                      = 0.499431
mttc                     = 5.91
efficiency               = 0.509
recommended_technical_score = 0.654129

boundary:          HR@10 0.8      MRR 0.501667  MTTC 6.6
browsing:           HR@10 0.8      MRR 0.509142  MTTC 5.6625
buying:              HR@10 0.85     MRR 0.478378  MTTC 5.75
intent_override:     HR@10 0.7      MRR 0.528929  MTTC 6.766667
```

**This is the current benchmark of the uncommitted working tree, re-run this second —
not a simulation, not a cached number.** The committed baseline (what's actually live if
you `git checkout` a clean tree, or what the organizer would score if this were
submitted as-is right now) is still B0's `500fe7b`, HR@10 **0.730**, TechnicalScore
**0.597737** — reproduce that specifically by loading `git show 500fe7b:starter/agent.py`
(every prior handover in this session did this and hash-verified it against
`0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354`).

---

## 2. Repo/remotes/data (unchanged from round 1 — not re-verified this pass, no reason to expect drift)

Same as `MASTER_HANDOVER.md` §0/§6: `origin` =
`github.com/caijunix-droid/techjam-conversational-search.git` (team fork, all work
lives here), `upstream` = `github.com/TechJam2026/techjam-conversational-search.git`
(organizer read-only, confirmed untouched, unchanged). Data provenance, competition
spec structure, and the organizer slide-deck context (`docs/competition_specification.md`,
`DATA_ATTRIBUTION.md`, and the externally-held
`TechJam2026_Shopping_Copilot_Hackathon_Slides_Digested.md`) are all unchanged — see
round 1 for the full detail, and
`markdowns/fix01b1_private_generation_evidence_audit.md` for the deeper dive into what
those sources say about private-set session generation.

---

## 3. What happened since round 1 — chronological narrative

Everything below happened as a sequence of user-issued directives, each independently
reviewed (often by a separate "independent review" pass that caught real errors — see
§3.2), following the same gated evidence-first discipline round 1 described: investigate
→ report → wait → (sometimes) implement → test → benchmark → report → wait. All 13
markdown files this produced are listed in §5.

### 3.1 FIX-01B1 — binary active-intent-match reranking (superseded, never committed)

Hypothesis: rerank the existing top-10 by whether each candidate matches ≥1 term from
`state.active_slots` (the FIX-01B0 active-intent store), stable-partitioning
matches-first with no weights. Implemented, tested, benchmarked:
`HR@10 0.730 (unchanged) → MRR 0.465458→0.474675 → TechnicalScore 0.597737→0.600502`,
9/200 sessions changed, all rank improvements, 0 regressions on the public set. Patch
preserved uncommitted at `markdowns/patches/fix01b1_active_intent_ranking.patch`; its
test file archived at `markdowns/historical_tests/test_fix01b1_active_intent_ranking.py`
once superseded (see §3.4). **This entire line of work was later subsumed by FIX-01B2
(§3.4) and is not the current candidate** — kept only as historical evidence.

### 3.2 Independent review caught a real error, and it was corrected (not defended)

The original FIX-01B1 handover claimed the stable-partition mechanism "can never
demote" a target. An independent review proved this **false** — mechanically (a
minimal sort example) and through the real code (a constructed S1/S2 adversarial pair).
This was retracted, not rationalized, in
`markdowns/fix01b1_safety_boundary_verification.md`, along with a full public-set
exposure audit: of 146 hit sessions, 140 had the target *itself* match its own active
intent (structurally undemotable), 6 had no active constraint, and **0** were ever in
the exposed "target is not a match, a competitor is" configuration — traced to a
specific, cited mechanism (`evaluator/local_evaluator.py`'s `intent_card()` deriving
customer language from the target's own catalog text), not asserted as a general safety
property.

### 3.3 Recall/rescue/separability audits — the investigation that led to B2

In order:
- **`candidate_recall_audit_b0.md`**: restored clean B0, measured how deep the 54
  current misses' targets actually sit in baseline BM25 order. Finding: 39/54 (72%)
  within rank 50.
- **`candidate_rescue_simulation_b1.md`**: simulated the *frozen* binary B1 rule over
  larger pools (N=20/50/100). Result: only **1/54** rescued — the binary signal is too
  weak even with more candidates in view, because most candidates near the target are
  *also* active matches, so a binary partition can't discriminate among them. Also
  surfaced a real, distinct failure mode: 2 sessions got **worse** MRR from an
  early-pool match closing the session before a later, better rank was reached.
- **`second_stage_ranking_separability_audit.md`**: tested richer signals (term-coverage
  fraction, slot-coverage fraction, raw active-only BM25) as offline diagnostics.
  **Active-term coverage** (matched-terms / total-terms, no weights) rescued up to
  **18/54** misses at N=100 with only 2/146 regressions — an order of magnitude
  stronger than binary B1. Raw active-only BM25 was **rejected**: it also rescued
  ~17/54 but **destroyed 28–42/146** existing hits — clearly unsafe by the audit's own
  stated test.

### 3.4 FIX-01B2 — active-term-coverage ranking (IMPLEMENTED, uncommitted, current state)

Mechanism, frozen and then implemented exactly:

```
1. Same B0 candidate query, unchanged — but retrieval depth widened to
   internal_depth = max(50, top_k) instead of top_k.
2. Per candidate: coverage = (distinct active terms matched) / (distinct active terms),
   using state.active_slots only (never state.slots) and the same _terms() tokenizer.
3. Sort descending by coverage; ties (including "no active terms") keep baseline order.
4. Truncate to the caller's requested top_k (never more, regardless of internal_depth).
```

- **`fix01b2_term_coverage_end_to_end_simulation.md`**: simulated this under the *real*
  evaluator stopping protocol (not an oracle) before writing any code. Result: HR@10
  0.730→**0.805**, MRR→**0.499431**, TechnicalScore→**0.654129**. All 146 original hits
  preserved, exactly the 15 offline-flagged misses became real hits (zero
  substitutions), but 6 sessions that remained hits under both systems had their rank
  *degrade* — the same early-stop-timing effect from §3.3, now precisely quantified.
- **`fix01b2_term_coverage_implementation_handover.md`**: actually implemented in
  `starter/agent.py` (the diff in §1 above). The real evaluator reproduced the
  simulation's numbers **exactly**, session-for-session, on the first run — no tuning
  was needed or performed. 9 new targeted tests + all 13 prior = 22/22 green. Runtime
  flagged: single-run measurement showed **~1.87x slower** than B0 (54.7s vs 29.3s).
- **`fix01b2_p1_performance_investigation.md`**: profiled the slowdown (>98% of time is
  SQL `execute`/`fetchall`; confirmed via a B0-comparison that the widened retrieval
  depth is *not* new cost — the real added cost is ~3272 extra per-active-term `MATCH`
  queries across the 200-session set). Two exact-equivalence-proven optimization
  candidates were built and tested as **external scratch files, never touching
  `starter/agent.py`**: batching into one `UNION ALL` query (**REJECT** — 49.7%
  *slower*, SQL query-planning cost outweighs round-trip savings) and fetching
  candidate text once and matching locally in Python (**INVESTIGATE, not KEEP** — only
  ~1.7% faster once measured with proper 3-run-median rigor, which is within this
  machine's own run-to-run measurement noise band). **Neither was adopted. B2's
  implementation in `starter/agent.py` is unchanged from what §1 shows right now.**

---

## 4. Open items — real, unresolved, not yet decided

1. **B2 is implemented, tested, and verified, but still requires an explicit commit
   decision.** Nobody has said "commit B2" yet. It sits uncommitted exactly as
   governance required at every step.
2. **Runtime**: B2 is meaningfully slower than B0 (~1.6–1.9x across different
   measurement passes — the range itself reflects real machine noise, see
   `fix01b2_p1_performance_investigation.md` §4). Not resolved. `docs/submission_rules.md`
   notes the organizer may run submissions "under CPU, memory, timeout, and network
   restrictions" but this repo does not contain a specific numeric limit to check
   against.
3. **The 6 rank-regression sessions are real and understood** (early-stop timing, not a
   safety-invariant violation), but they mean B2 is not strictly monotonic — worth
   disclosing plainly if B2 is committed and written up for submission.
4. **Private-set generalization**: `fix01b1_private_generation_evidence_audit.md`
   established, from organizer-authored material (not mere extrapolation from public
   statistics), that private sessions share the *same* target-derived intent-card
   construction methodology as public ones. That audit was scoped to the binary B1
   signal's specific exposure question. **It has not been re-examined for B2's
   term-coverage mechanism specifically** — the underlying "customer language often
   echoes the target's own catalog text" mechanism plausibly extends, but this has not
   been explicitly re-audited for B2 and should not be assumed carried over silently.
5. **Items 1–4 from round 1's own open-items list are still entirely untouched**: no
   semantic/dense retrieval, budget/price still never enforced numerically (and
   `second_stage_ranking_separability_audit.md` §7 found the public set has **zero**
   genuine numeric budget disclosures the current classifier extracts correctly — two
   false positives, both traced to specific misclassified strings), compound
   multi-attribute constraint loss (~0.4% prevalence, still low priority), and static
   one-question-per-turn clarification. Round 1's item 5 (README/Devpost/demo
   video/submission checklist) also **has not been started**.

---

## 5. Full file inventory — committed vs. uncommitted trail

**Committed** (in `500fe7b`, unchanged since round 1 — still the only commit containing
code changes):
```
starter/agent.py                                    (FIX-01B0 content, at HEAD)
tests/test_fix01b0_state_retrieval_decoupling.py
markdowns/historical_tests/test_intent_override_fix01.py
```

**Uncommitted working-tree change** (exists only on disk right now):
```
starter/agent.py    -- FIX-01B2 patch applied, SHA e3f324ca... (see §1)
```

**Uncommitted test file** (new since round 1, not yet staged):
```
tests/test_fix01b2_term_coverage_ranking.py
```

**All markdown evidence produced since round 1** (all untracked, none committed):
```
markdowns/fix01b1_active_intent_ranking_handover.md
markdowns/fix01b1_safety_boundary_verification.md
markdowns/fix01b1_private_generation_evidence_audit.md
markdowns/candidate_recall_audit_b0.md
markdowns/candidate_rescue_simulation_b1.md
markdowns/second_stage_ranking_separability_audit.md
markdowns/fix01b2_term_coverage_end_to_end_simulation.md
markdowns/fix01b2_term_coverage_implementation_handover.md
markdowns/fix01b2_p1_performance_investigation.md
markdowns/historical_tests/test_fix01b1_active_intent_ranking.py   (archived, superseded)
markdowns/patches/fix01b1_active_intent_ranking.patch              (preserved historical patch)
```

Plus everything round 1 already listed as untracked (`fix01_*.md`, `fix01a_*.md`,
`fix01b0_*.md`, `markdowns/probes/*`, `MASTER_HANDOVER.md` itself) — all still present,
still untouched, still nobody's asked what to do with them.

---

## 6. How to verify any of this yourself, fast

```bash
git log --oneline -7                          # confirm history matches §1
git status --short -- starter/agent.py         # confirm the uncommitted B2 diff exists
shasum -a 256 starter/agent.py                 # current working tree: e3f324ca...
python3 -m unittest discover -s tests -p 'test*.py'   # expect 22/22 pass
python3 -m evaluator.local_evaluator           # expect the §1 numbers (0.805/0.499431/...)

# To see the committed B0 baseline specifically (not the working tree):
git show 500fe7b:starter/agent.py | shasum -a 256   # expect 0c67512c...
```

If any of these disagree with this document, **trust the command output** — this file
describes state as of 2026-08-31, later same session as round 1.

---

## 7. Methodology note (unchanged from round 1, still the operating discipline)

Same evidence-first process throughout §3: investigate → report in markdown → wait for
explicit go-ahead → implement → test → benchmark → report → wait again before commit.
Every simulation was later verified against a real implementation before being trusted
(§3.4). Every safety/invariant claim was checked adversarially, and at least one was
found wrong and corrected in public rather than defended (§3.2). Every optimization
candidate was proven exactly behaviorally equivalent before its runtime was even
measured (§3.4's P1 audit). If continuing this project: same discipline — re-verify
before acting, don't trust a prior handover's numbers blindly (including this one — see
§6), ask before commit/push.
