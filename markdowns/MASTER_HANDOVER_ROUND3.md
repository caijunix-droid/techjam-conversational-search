# MASTER HANDOVER — ROUND 3 (read this first, then `MASTER_HANDOVER_ROUND2.md`, then `MASTER_HANDOVER.md`)

Written 2026-08-31, later in the same overall project timeline as round 2 (a
new chat session picking this project back up). Purpose: identical to
rounds 1/2 — let a **fresh Claude session** pick this up with zero
re-derivation and zero hallucination risk. Everything under "Verified fresh
in this pass" was re-run via actual commands immediately before writing this
document. Everything under "Carried forward" was verified carefully when
originally produced (see the cited markdown files for actual command
output) but not re-run in this exact pass — this project's own established
discipline.

**Round 1 (`MASTER_HANDOVER.md`) still correctly describes the repo's
purpose, remotes, data provenance, and organizer-material context. Round 2
(`MASTER_HANDOVER_ROUND2.md`) is now itself stale on every specific number
and code-state claim it made** — the codebase and benchmark have moved
substantially since then (round 2 ended with FIX-01B2 freshly committed at
`c30c712`, HR@10 0.805, and a great deal of subsequent work uncommitted).
This document exists because everything since has changed.

---

## 0. The one-sentence version

Round 2 ended with FIX-01B2 committed (`c30c712`, HR@10 0.805). Since then,
three more production experiments were investigated, simulated, and
implemented under the same evidence-first gated discipline —
**FIX-02A2** (active-slot coverage secondary tie-break) and **FIX-03A**
(intent-override state-preservation correction) are both **committed and
pushed**; a fourth, **FIX-04A** (extending FIX-03A's fix to retrieval
evidence), is **simulated, positive, but explicitly not yet implemented**,
awaiting an authorization decision. Current accepted, live production
state: **HR@10 0.825, TechnicalScore 0.671932, 165/200 hits (82.5%)**. The
working tree is **completely clean** — no uncommitted code changes exist
right now, unlike at the end of round 1 or round 2.

---

## 1. Verified fresh in this pass

```bash
git log --oneline -10
```
```
f5f4255 docs: archive experiment handovers and research artifacts
1e2848e FIX-03A: preserve unrelated active intent on override
c642094 FIX-02A2: add active-slot coverage tie-break
c30c712 FIX-01B2: rerank candidates by active-term coverage
500fe7b FIX-01B0: decouple active intent from retrieval evidence
037b52d Revert "Fix budget parsing and vague-answer handling in agent."
c6461c4 added markdowns for Claude
068e8fa Fix budget parsing and vague-answer handling in agent.
9b5fc2f Add improved shopping agent with dialog memory + live demo script
9a35be5 Clarify participant model API costs
```

```bash
git rev-parse HEAD
  # f5f4255a67f2884eeb798ffe0f20adfe71de1e5d
git rev-list --left-right --count origin/main...main
  # 0  0    (fully in sync with origin/main -- everything in this handover
  #           that says "committed" has also been pushed)
git status --short
  # (completely empty -- clean working tree, nothing uncommitted at all)
shasum -a 256 starter/agent.py
  # c839811324f491049d397cad8b0b0c0a75d2466df272482037870a5ccddffb82
```

```bash
python3 -m unittest discover -s tests -p 'test*.py'
  # Ran 36 tests in 0.042s — OK
python3 -m evaluator.local_evaluator
```
```
hit_rate_at_10           = 0.825000
mrr                      = 0.510105
mttc                     = 5.680000
efficiency               = 0.532000
recommended_technical_score = 0.671932

boundary:          HR@10 0.800   MRR 0.501667  MTTC 6.600000
browsing:           HR@10 0.800   MRR 0.509142  MTTC 5.600000
buying:              HR@10 0.8625  MRR 0.469871  MTTC 5.575000
intent_override:     HR@10 0.800   MRR 0.622778  MTTC 5.866667
```

**This is the live, committed, pushed production state — not a simulation,
not an uncommitted candidate.** `git status --short` is empty: unlike every
prior handover in this session, there is nothing sitting uncommitted in the
working tree right now.

---

## 2. Repo/remotes/data (unchanged from rounds 1/2 — not re-verified this pass beyond the remote URLs above, no reason to expect drift)

Same as before: `origin` = `github.com/caijunix-droid/techjam-conversational-search.git`
(team fork, all work lives here, confirmed in sync above), `upstream` =
`github.com/TechJam2026/techjam-conversational-search.git` (organizer
read-only, confirmed untouched throughout every pass this session). Data
provenance, competition spec structure, and organizer-slide-deck context are
unchanged — see round 1 for full detail.

---

## 3. What happened since round 2 — chronological narrative

Same evidence-first gated discipline throughout: investigate → simulate →
report → wait for go-ahead → implement → test → benchmark → report → wait
for commit go-ahead → commit → (sometimes) push. All markdown files this
produced are listed in §5.

### 3.1 FIX-02-P0 — remaining-39 miss root-cause audit (diagnostic only)

Diagnostic pass against the frozen FIX-01B2 baseline (`c30c712`, HR@10
0.805, 39 misses). Classified all 39: **A1 (coverage tie) = 19 (48.7%), B
(rank 51–100) = 13, C (rank 101–500) = 6, D (>500/absent) = 1**. Central,
directly-measured finding: **36/39 missed targets have perfect (1.0)
active-term coverage** — coverage is saturating, not failing, because the
dominant active terms ("closure," "cotton," "polyester," etc.) sit at
15–39% catalog document frequency (measured directly against the 50k-item
catalog) — essentially boilerplate, not discriminating. A counterfactual
depth sweep (Top100/Top500) showed only 3/39 rescuable and real regression
risk at Top500 — ruled out "just widen the pool." Recommended (not
implemented) an IDF-weighted coverage experiment. Also found and precisely
traced two distinct override-related mechanisms — active-term collapse on
override, and "phantom hits" (target reaches Top10 pre-override but the
evaluator's gate can never count it) — both later became directly relevant
to FIX-03/FIX-03A.

### 3.2 FIX-02A0 — active-only BM25 blanket tie-break (simulation) — REJECTED

Tested whether raw active-only BM25 score could discriminate inside
saturated coverage ties. **REJECT**: net hit loss (9 rescued vs. 10 existing
hits lost), MRR collapsed ~9.3% relative, 9 previously clean rank-1 hits
thrown to rank 7–10. The signal has *some* real discriminating power
(rescued 9/19 targeted ties) but applying it blanket-wide damages far more
than it helps.

### 3.3 FIX-02A1 — boundary-localized active BM25 tie-break (simulation) — REJECTED

A refinement of A0: only reorder the specific coverage-tied group straddling
the evaluator's Top-10 boundary, leaving other groups untouched. Reduced
collateral damage substantially (regression severity ratio improved from
~1.94x to ~1.24x) and MRR actually improved slightly — but **HR@10 and
existing-hit destruction were byte-for-byte identical to the already-rejected
A0** (same 10 hits lost), because the 9 lost sessions' tied groups already
span from position 1 through past position 10 (near-catalog-wide ties),
making localization structurally unable to protect them. Still **REJECT**.

### 3.4 FIX-02A2 — active-slot coverage secondary tie-break — IMPLEMENTED, COMMITTED, PUSHED

First recovered and reproduced the exact historical "Diagnostic C" slot-
coverage definition from `second_stage_ranking_separability_audit.md`
(9/54 rescued, 0/146 regressed — reproduced exactly before trusting it).
Simulated adding it as a secondary tie-break *inside* B2's existing
term-coverage groups (never overriding term coverage): **HR@10 0.805→0.810
(+1 net hit), TechnicalScore 0.654129→0.657508, 0/161 existing hits lost**,
only 4 sessions touched out of 200 — a small, surgical, mechanism-fully-
explained win. Implemented exactly (reusing the already-computed
`term_matches`, zero new SQL queries — the required performance
architecture), 0 session mismatches against the simulation, no measurable
runtime cost. **Committed as `c642094`.**

### 3.5 FIX-03 — final major opportunity diagnostic (Part A + Part B, read-only)

**Part A — Intent Override recoverability.** Traced all 9 remaining Intent
Override misses turn-by-turn. Found one consistent, general defect: the
override branch correctly deletes the tracked superseded slot (SUPERSEDED,
working as intended in 9/9 cases) but **silently overwrites a different,
already-populated bucket** (usually "material") that the override message
never named — destroying real disclosed information ("spandex," "rayon,"
"10% others") that was never contradicted. Simulated a general correction
(merge instead of overwrite when the bucket wasn't the tracked one): **+3
net hits, 0 regressions of any kind across all 200 sessions**, TechnicalScore
0.657508→0.671932, every non-intent_override scenario byte-identical
before/after.

**Part B — Semantic/TF-IDF feasibility.** Environment audit found the repo
declares **zero** third-party dependencies (agent.py: stdlib only through
every fix to date) and no dependency manifest; the organizer may disable
network access at scoring time. Tested the lightest defensible tier
(TF-IDF+cosine, no model download): **0/20 Top50 recall on the current B/C/D
misses, and it never once surfaced a target BM25 missed** across 40 sessions
tested. Correctly gated off before building a hybrid mechanism — **REJECT**,
measured not assumed. Neural/contextual embeddings remain untested (out of
scope for that pass), not rejected.

### 3.6 FIX-03A — Intent Override state correction — IMPLEMENTED, COMMITTED, PUSHED

Implemented FIX-03's Part A mechanism exactly (recovered byte-for-byte from
the scratch simulation file, not reconstructed from memory). 6 targeted
tests (A–F), all passed first run. Full evaluator reproduced the simulation
exactly: **HR@10 0.825000, TechnicalScore 0.671932, 165/200 hits**. 0
session mismatches against the simulation across all 200 sessions. Runtime
unchanged (median ~52.6s, matching prior passes). **Committed as `1e2848e`,
and pushed to `origin/main`** (verified `HEAD == origin/main`).

### 3.7 FIX-04 — remaining-35 root-cause audit (read-only)

Recomputed the full 35-miss population fresh under the committed FIX-03A
agent (not assumed by subtraction). **Central finding**: all 6 remaining
Intent Override misses now show `term_coverage = 1.0` **and**
`slot_coverage = 1.0` on every countable turn — both of A2's discrimination
signals are maximally saturated; the bottleneck moved entirely to candidate
generation. Directly traced *why* preserving `active_slots` evidence wasn't
enough for 2 of the 6 (`public_0096`, `public_0177`): **FIX-03A's fix only
touched `active_slots` (used for reranking) — `state.slots` (used to build
the retrieval query that decides the Top50 pool) still has the exact same
unconditional-overwrite defect, untouched by design.** Measured directly:
`public_0096`'s retrieval rank was 23 (comfortably in Top50) before its
override collapsed `state.slots["material"]` from `"95% Polyester, 5%
Spandex"` to `"polyester"`, dropping it to rank 199; `public_0177` went from
rank 8 to rank 156 the same way. Recommended (not implemented) simulating
the same merge extension on `state.slots`.

### 3.8 FIX-04A — retrieval-evidence preservation simulation + Bucket-A characterization (read-only)

**Part A**: simulated extending FIX-03A's exact merge logic to `state.slots`.
Result: **+1 net hit** (not +2 — `public_0177` fully rescued, `public_0096`
was NOT rescued: its retrieval rank correctly stabilizes at 23, but that
just converts it from a retrieval-depth problem into a Bucket-A saturated-tie
problem, still unsolved). TechnicalScore 0.671932→0.675908. **2 real rank
regressions** (not hit losses) — traced with exact query expressions from
both agent versions: FIX-03A's defect had been *accidentally* dropping
tokens in a way that, for those two specific candidate pools, happened to
rank the target slightly better by BM25 coincidence; preserving the correct
evidence removes that accidental benefit. All 5 touched sessions are Intent
Override; the other 195 sessions are untouched. Classified **RETURN FOR
INDEPENDENT REVIEW** (not automatic implementation) — weaker than FIX-03A's
own zero-regression result, but net positive and mechanistically explained.
**Not implemented.**

**Part B**: descriptive-only characterization of the 15 current Bucket-A
misses vs. a comparison sample of hits, looking for a next discriminator
(field coherence, phrase coherence, slot-to-field alignment). **Honest null
result**: an apparent "hits show broader field coherence" pattern was fully
explained by a confound (hit sessions simply average more than double the
accumulated active terms by their hit turn) — checked directly, not assumed
away. **No new discriminator recommended.**

### 3.9 Documentation archive commit — COMMITTED, PUSHED

All 34 files under `markdowns/` (handovers, audits, simulations, historical
tests, patches, probes) committed in one archival commit and pushed.
Credential/secret scan run first (two matches, both confirmed false
positives on inspection — "no secrets committed" checklist text and
"commit authorization:" prose). No large files. Production code
(`starter/`, `tests/`, `evaluator/`, `data/`) verified untouched by this
commit. **Committed as `f5f4255`, pushed to `origin/main`.**

---

## 4. Open items — real, unresolved, not yet decided

1. **FIX-04A's `state.slots` merge extension is simulated only, not
   implemented.** It cleared its own fast-quality-gate (net hits > 0,
   TechnicalScore improves, regression surface small and explained,
   mechanism semantically defensible) but is meaningfully weaker than
   FIX-03A's own zero-regression result (2 rank regressions, no hit losses).
   Nobody has authorized implementation yet — it sits exactly where
   FIX-02A2/FIX-03A sat before their own implementation authorizations.
2. **Current accepted, live baseline is FIX-03A only**: HR@10 0.825,
   TechnicalScore 0.671932, 165/200 (82.5%). FIX-04A would move this to
   166/200 (83.0%) if implemented — still short of the stated 85% stretch
   target by 4 hits even then (5 hits short at the current 165 baseline).
3. **No further evidence-backed mechanism exists for the remaining Bucket
   A/B/C/D non-override misses** beyond what's already been characterized:
   `FIX-02-P0`'s IDF-weighted-coverage hypothesis (well-evidenced, but never
   simulated — explicitly flagged in `FIX-04A` §10 that any such proposal
   must explain what new discriminatory information it adds beyond
   full-match/full-match ties, which plain IDF may struggle to do for the
   dominant "target and competitor both match everything" case); TF-IDF
   semantic retrieval (rejected, measured); Bucket-A field coherence
   (null result, measured). Neural/contextual embeddings remain genuinely
   untested — not rejected, not recommended, an open question with real
   dependency/network-access risk given the repo's current zero-dependency
   footprint and the organizer's stated possible network restrictions.
4. **Round 1's own original open items are still substantially untouched**:
   budget/price is still never enforced numerically (and multiple audits
   this session confirmed the public set contains zero genuine numeric
   budget disclosures the current classifier extracts correctly), compound
   multi-attribute constraint loss (~0.4% prevalence, still low priority),
   static one-question-per-turn clarification, and the README/Devpost/demo
   video/submission checklist (round 1's item 5) has still **not been
   started**.
5. **Working tree is completely clean right now** — a genuinely different
   state from every prior handover in this session. If continuing this
   project, the very next decision is simply: does the FIX-04A `state.slots`
   correction get authorized for implementation, or does the project instead
   pursue a different remaining-miss family (IDF coverage, or the still-open
   neural-semantic question)? Nothing is "in flight" uncommitted right now.

---

## 5. Full file inventory — committed vs. uncommitted trail

**Committed and pushed** (production code, all in `origin/main` as of
`f5f4255`):
```
starter/agent.py                                          (FIX-03A content, at HEAD)
tests/test_fix01b0_state_retrieval_decoupling.py
tests/test_fix01b2_term_coverage_ranking.py
tests/test_fix02a2_slot_coverage_tiebreak.py
tests/test_fix03a_override_correction.py
markdowns/historical_tests/test_intent_override_fix01.py
```

**Committed and pushed** (all markdown research/documentation, archived in
`f5f4255`, including everything round 2 already listed as untracked plus
everything produced this session):
```
markdowns/MASTER_HANDOVER.md
markdowns/MASTER_HANDOVER_ROUND2.md
markdowns/fix01_*.md, fix01a_*.md, fix01b0_*.md, fix01b1_*.md, fix01b2_*.md
markdowns/candidate_recall_audit_b0.md
markdowns/candidate_rescue_simulation_b1.md
markdowns/second_stage_ranking_separability_audit.md
markdowns/fix02_p0_remaining39_root_cause_audit.md
markdowns/fix02a0_active_bm25_tiebreak_simulation.md
markdowns/fix02a1_boundary_localized_tiebreak_simulation.md
markdowns/fix02a2_slot_coverage_tiebreak_simulation.md
markdowns/fix02a2_implementation_handover.md
markdowns/fix03_final_major_opportunity_audit.md
markdowns/fix03a_implementation_handover.md
markdowns/fix04_remaining35_root_cause_audit.md
markdowns/fix04a_slots_preservation_simulation_and_bucketA_characterization.md
markdowns/historical_tests/test_fix01b1_active_intent_ranking.py
markdowns/patches/*.patch
markdowns/probes/*.py
```

**Not in the repo at all** (external scratch, referenced by prior handovers
for full raw evidence, not part of the git history and not expected to
survive between sessions):
```
/private/tmp/.../scratchpad/*.py, *.json    -- all simulation/trace scripts
                                               and their output for FIX-02
                                               through FIX-04A. If a fresh
                                               session needs the underlying
                                               per-session trace data cited
                                               in these markdowns, it will
                                               need to be regenerated --
                                               these files are session-local
                                               and not guaranteed to persist.
```

**Uncommitted**: nothing. `git status --short` is empty.

---

## 6. How to verify any of this yourself, fast

```bash
git log --oneline -10                          # confirm history matches §1
git status --short                              # expect: nothing (clean)
git rev-list --left-right --count origin/main...main   # expect: 0  0
shasum -a 256 starter/agent.py                  # expect: c8398113...
python3 -m unittest discover -s tests -p 'test*.py'   # expect 36/36 pass
python3 -m evaluator.local_evaluator            # expect the §1 numbers (0.825/0.510105/...)
```

If any of these disagree with this document, **trust the command output** —
this file describes state as of 2026-08-31.

---

## 7. Methodology note (unchanged from rounds 1/2, still the operating discipline)

Same evidence-first process throughout §3: investigate → simulate (external
scratch harness, byte-for-byte equivalence to production verified before
trusting any result) → report in markdown → wait for explicit go-ahead →
implement (exact mechanism recovered from the scratch file, never
reconstructed from memory) → test → full-200-session benchmark → session-
level diff against the simulation (0 mismatches required) → report → wait
again before commit → commit exactly the authorized file set → wait again
before push. Every rejected mechanism (A0, A1, TF-IDF) was rejected on
measured evidence, with what *was* useful about it (A0/A1's real but
over-applied signal; TF-IDF's ruled-out-not-just-assumed status) reported
honestly rather than discarded wholesale. Every regression from an adopted
mechanism (FIX-04A's two rank regressions) was traced to an exact,
reproducible mechanism rather than hand-waved. If continuing this project:
same discipline — re-verify before acting, don't trust a prior handover's
numbers blindly (including this one — see §6), ask before commit/push.
