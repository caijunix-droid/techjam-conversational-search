# MASTER HANDOVER — TechJam Conversational Search (read this first)

Written 2026-08-31. Purpose: let a **fresh Claude session** (or any other reader) pick up
this project with zero re-derivation and zero hallucination risk. Every number below was
re-verified by running actual commands against the actual repo immediately before writing
this document — none of it is recalled from memory only.

**If you are a new Claude session reading this: verify anything load-bearing yourself
before acting on it (`git log`, hashes, a fresh evaluator run). This document describes
state as of the commit listed below — if `git log` shows anything past that commit,
re-derive from current state instead of trusting this file blindly.**

---

## 0. What this repo is

A 72-hour hackathon submission (TechJam 2026, "Shopping Copilot") — a multi-turn
conversational shopping agent that must find a hidden target product in a fixed 50k-item
Amazon clothing catalog, scored by `HitRate@10` (50%), `MRR` (30%), and turn-efficiency
(20%). Full spec: `docs/competition_specification.md`. A denser digest of the organizer's
briefing slides (with the same numbers) is at
`TechJam2026_Shopping_Copilot_Hackathon_Slides_Digested.md` if that file is still present
in the conversation/repo — it is not itself part of the git repo, it was supplied as
context earlier in this session.

**Remotes**:
- `origin` = `https://github.com/caijunix-droid/techjam-conversational-search.git` — this
  is the team's own working/submission fork. All commits described below are here.
- `upstream` = `https://github.com/TechJam2026/techjam-conversational-search.git` — the
  organizer's read-only repo. **Confirmed untouched** by any of this session's work.

**Current HEAD** (both local `main` and `origin/main`, confirmed in sync, 0 ahead/0
behind, right before writing this document):
```
500fe7b FIX-01B0: decouple active intent from retrieval evidence
037b52d Revert "Fix budget parsing and vague-answer handling in agent."
c6461c4 added markdowns for Claude
068e8fa Fix budget parsing and vague-answer handling in agent.
9b5fc2f Add improved shopping agent with dialog memory + live demo script
9a35be5 Clarify participant model API costs
2a6cc8e Publish conversational search challenge
```

**Note on push**: `500fe7b` was already pushed to `origin/main` — confirmed by
`git rev-list --left-right --count origin/main...main` returning `0 0`. This happened
outside of any explicit push command in this session (no git hooks exist in
`.git/hooks/` that could explain it) — the user noted it was likely accidental, but the
content itself was fully reviewed, tested, and explicitly approved before commit, and
`upstream` (the organizer's repo) is unaffected. Not something to undo unilaterally.

---

## 1. Current, real, reproducible benchmark numbers (as of `500fe7b`)

Re-run this yourself to confirm before trusting any number below:
```bash
curl -sL -o data/catalog.jsonl.gz https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz
gunzip -k data/catalog.jsonl.gz   # 50,000 rows; not committed to git, gitignored by design
python3 -m evaluator.local_evaluator
python3 -m unittest discover -s tests -p 'test*.py'
```

```
Hit Rate@10      = 0.73
MRR              = 0.465458
MTTC             = 6.345
Efficiency       = 0.4655
TechnicalScore   = 0.597737

Buying:           HR@10 0.7875   MRR 0.436796   MTTC 6.2875
Browsing:         HR@10 0.7125   MRR 0.470184   MTTC 6.025
Intent Override:  HR@10 0.633333 MRR 0.520556   MTTC 7.233333
Boundary:         HR@10 0.7      MRR 0.491667   MTTC 6.7
```

Deterministic (confirmed via repeated runs, byte-identical except random session UUIDs).
Weak baseline for comparison (pre-existing file, `docs/baseline_results.json`): HR@10
0.125, MRR 0.068034, MTTC 9.81, TechnicalScore 0.10671.

Test suite: `python3 -m unittest discover -s tests -p 'test*.py'` → **13/13 pass, 0 fail,
0 error** (this is the correct, current expected count — see §4 for why it isn't 20).

---

## 2. What the agent actually does (`starter/agent.py`, pure Python stdlib — no LLM, no API)

- SQLite FTS5 keyword search (BM25 ranking) over `title/categories/features/details/store/
  description`. **`price` is not in the index and is never read anywhere in the file** —
  budget/price constraints are never enforced against the actual numeric price (see §5,
  open item #2).
- Per-session `SessionState` with **two parallel dicts** (this is the FIX-01B0
  architecture, current and committed):
  - `slots` — retrieval evidence, feeds `_build_query()`. Deliberately kept
    byte-equivalent to the original baseline's accumulation behavior at every call site,
    **including the Intent Override branch**, where it still just overwrites the same
    bucket with no deletion (the original, semantically-wrong-but-retrieval-useful
    behavior).
  - `active_slots` — active customer intent, feeds `_next_ask_attribute()` (decides what
    to ask next). This one **does** correctly delete a superseded preference on an
    explicit override, via provenance tracking (`override_source_attr`/
    `override_source_value`).
- One clarifying question per turn, fixed priority order (`ASK_ORDER`), no dynamic
  cost/value skipping.
- `demo/interactive.py` — CLI wrapper for a human to type live messages at the same
  `Agent` class.

---

## 3. The investigation this session did, and why the architecture looks like this

### 3.1 Verified the original `HANDOVER.md`'s claims (all confirmed true)
Files exist as claimed, commit exists, the 0.73/0.465/6.35/0.598 table reproduces exactly,
no API/network code anywhere, tests passed, demo runs end-to-end. The three "tried and
reverted" ideas named in `HANDOVER.md` (slot erasure, tiered search, retrieval cutoff)
**could not be independently verified** — no commits exist for them, take them as team
testimony only.

### 3.2 Found a real defect: Intent Override doesn't replace, it accumulates
Spec (`docs/competition_specification.md` + the slides digest) explicitly requires that
when a customer says "ignore my earlier preference," the **old** constraint must be
removed, not kept alongside the new one — this is 15% of the benchmark (Intent Override
scenarios). Traced through all 30 real override sessions in `data/public_set.jsonl`:
**24/30 (80%) have old/new values classifying into different attribute buckets, and
24/24 of those retained the stale old value** in the single pre-FIX-01 `state.slots`
dict. Reproduction scripts: `markdowns/probes/probe_override_batch.py`,
`probe_override_single.py`.

### 3.3 FIX-01A — first attempted fix — REJECTED, evidence preserved (not committed)
Simplest fix: track which bucket the old value went into, delete it on override. Fixed
the defect (24/24 → 0/24 stale) and passed all 7 targeted tests, but the **full
200-session benchmark regressed**: TechnicalScore 0.597737 → 0.594491, all of it in the
Intent Override scenario (MRR −12.6% relative), with **zero of the 7 changed sessions
improving** (5 worse rank, 2 same rank but later turn). Root cause (traced, not
speculated): the evaluator's `intent_card()` derives both the old and new override values
from the **same real target product's own listing text**, so the "stale" term wasn't
noise — it was genuine BM25 signal for the same target, and deleting it cost retrieval
quality with nothing to replace it. Rejected per explicit instruction; the patch itself
is preserved at `markdowns/patches/fix01a_intent_override.patch` and the full writeup at
`markdowns/fix01_intent_override_handover.md` / `fix01a_revert_and_architectural_finding.md`.
`starter/agent.py` was restored to the exact pre-FIX-01A baseline (hash-verified) before
proceeding.

### 3.4 FIX-01B0 — the architectural fix — ACCEPTED, COMMITTED (`500fe7b`)
Insight from 3.3: `state.slots` was doing two jobs at once (active-intent tracking *and*
retrieval evidence). Solution: split them (see §2). Result, independently re-measured
multiple times:
- Active-state correctness: 24/24 → 0/24 stale (measured **immediately after** the
  override turn — see the important methodology note below).
- Retrieval-query equivalence vs. the real baseline `Agent` class (loaded from its exact
  git blob, hash-verified, not a hand-copied reference): **0/30 mismatches**, every turn,
  across all 30 real override sessions.
- Full 200-session benchmark: **zero delta on every metric, every scenario, and every
  individual session** (200/200 session outcomes unchanged from baseline).
- 13 targeted + regression tests, all passing.

**Important methodology note, in case it comes up again**: the first version of the
30-session active-state probe measured `active_slots` at the *end* of the 10-turn
conversation and wrongly reported 24/24 still "stale." A single-session trace showed the
value *was* correctly cleared right after the override — but the evaluator's own scripted
customer legitimately re-mentions the same fact later, because `initial_message()` never
marks an override's `old_value` as "disclosed," so it can be honestly re-offered once the
attribute is freed up (which is the *intended* effect of the fix). The probe was corrected
to snapshot right after the override turn instead. Full detail:
`markdowns/fix01b0_state_retrieval_decoupling_handover.md` §5. **This is a fixed
probe-methodology bug, not an open question — the 0/24 corrected result is what's real.**

Full trail: `fix01b0_state_retrieval_decoupling_handover.md` →
`fix01b0_precommit_test_hygiene.md` → `fix01b0_test_governance_applied.md` →
`fix01b0_final_commit_preflight.md`. Explicit user approval ("GO — COMMIT FIX-01B0") was
given before the commit was made.

### 3.5 Test governance
`tests/test_intent_override_fix01.py` (FIX-01A's own test suite) asserted correctness via
`state.slots` directly — valid for FIX-01A's single-store design, not for FIX-01B0's
two-store one. Archived byte-for-byte (hash-verified) to
`markdowns/historical_tests/test_intent_override_fix01.py`, out of active `tests/`
discovery, per explicit authorization. This is why full discovery is 13/13, not 20/20 —
13 is the current correct expected count.

---

## 4. Repo state right now — what's committed vs. what's still sitting as investigation trail

**Committed** (in `500fe7b`, on `origin/main`):
- `starter/agent.py` (the FIX-01B0 patch)
- `tests/test_fix01b0_state_retrieval_decoupling.py`
- `markdowns/historical_tests/test_intent_override_fix01.py`

**Still untracked** (exist on disk, never staged/committed — this entire session's
evidence trail, deliberately not swept into the FIX-01B0 commit per explicit scope):
```
markdowns/fix01_cleanup_inspection.md
markdowns/fix01_intent_override_handover.md
markdowns/fix01_prepatch_verification.md
markdowns/fix01_restored_baseline.md
markdowns/fix01a_revert_and_architectural_finding.md
markdowns/fix01b0_final_commit_preflight.md
markdowns/fix01b0_precommit_test_hygiene.md
markdowns/fix01b0_state_retrieval_decoupling_handover.md
markdowns/fix01b0_test_governance_applied.md
markdowns/patches/fix01a_intent_override.patch
markdowns/probes/probe_fix01b0_override_and_equivalence.py
markdowns/handover2.md, markdowns/probes/probe_compound.py,
markdowns/probes/probe_override_batch.py, markdowns/probes/probe_override_single.py
```
Nobody has been asked yet whether these should be committed, gitignored, or left as local
scratch. **Ask the user before doing anything with them** — don't assume.

---

## 5. Open items — real, verified, not yet acted on

1. **No semantic/dense retrieval, no query rewriting, no reranking.** Confirmed via
   import inspection — pure stdlib (`json, re, sqlite3, pathlib`). Honestly disclosed in
   the original `HANDOVER.md`. The organizer's slides frame "LLM Semantic Ranking" as part
   of a competitive solution and name this as a scoring lever the local evaluator's
   HR@10/MRR/MTTC can't see (it's part of the 35%+20% Technical Execution + Innovation
   event-judging weight, not just the local benchmark).
2. **Budget/price is never enforced against the catalog's numeric `price` field.**
   `grep -n "price" starter/agent.py` → zero matches, and the FTS5 schema doesn't even
   carry `price` as a column. A stated "under $80" becomes loose keyword noise, not an
   actual filter. This is a different, separate defect from the Intent Override one — not
   touched by any FIX-01/FIX-01A/FIX-01B0 work. Doc `docs/competition_specification.md`
   §6.1 explicitly names "price ceiling" as an example hard constraint that "should
   strongly filter or penalize candidates that violate them."
3. **Compound single-string constraints lose one attribute** (e.g. a string mentioning
   both a color and a material word only gets classified into one bucket). Measured
   prevalence: 3/800 (0.4%) of real constraint strings. Real but low-priority.
4. **Static one-question-per-turn clarification**, no dynamic cost/value check. The
   spec's own slide explicitly invites this ("a better question can be more valuable than
   another retrieval call"). Team claims (unverifiable in git history) that a dynamic
   version was tried and measured worse.
5. **From the original `HANDOVER.md`, still not done**: README.md sections (overview,
   setup, reproduction steps, limitations reflection, team contributions), Devpost written
   description, demo video (2-4 min, YouTube, public, linked in Devpost), and the final
   submission checklist (repo public, no secrets committed, submit before deadline).

None of items 1-4 have had any fix attempted. Item 5 hasn't been started at all this
session.

---

## 6. How to verify any of this yourself, fast

```bash
git log --oneline -8                         # confirm commit history matches §0
shasum -a 256 starter/agent.py               # current: 0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
python3 -m unittest discover -s tests -p 'test*.py'   # expect 13/13 pass
python3 -m evaluator.local_evaluator         # expect the §1 numbers, need data/catalog.jsonl first
```

If any of these disagree with this document, **trust the command output, not this file**
— something changed since this was written, and this file itself says so at the top.

---

## 7. How this session worked (methodology, if you need to continue in the same style)

Everything above was produced under a strict evidence-first process (a loaded skill:
`evidence-first-independent-verifier`) and a sequence of user-authored directives
(`TECHJAM_FIX01_*`, `FIX01_GOVERNANCE_CORRECTION_*`, `FIX-01B0_*`) that each explicitly
gated: investigate → report in markdown → **wait for explicit go-ahead** → implement →
test → benchmark → report → **wait again** before commit. No step assumed a prior claim
was true without re-running it. Every markdown file listed in §4 is a real, standalone
record of one such gated step, with actual command output, not summarized claims. If
continuing this project, the same discipline (re-verify before acting, don't trust a
prior handover's numbers blindly, ask before commit/push) is the established and explicitly
requested working style — not a one-off.
