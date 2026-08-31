# FINAL REPOSITORY HARDENING REPORT

Written 2026-08-31. Executes `TECHJAM 2026 — FINAL REPOSITORY HARDENING
PASS.md` exactly. **Documentation, hygiene, and reproducibility only — no
scoring/ranking/state file was touched, no commit, no push.**

```text
CLASSIFICATION: READY FOR FINAL DOCS/README COMMIT
```

---

## A. BASELINE

```bash
git status --short
git rev-parse HEAD
git rev-parse origin/main
git log -5 --oneline
```
```text
HEAD:        ce7114904b8cb97f6223e7419ef3923cce178a90
origin/main:  ce7114904b8cb97f6223e7419ef3923cce178a90   (match, confirmed at pass start)

ce71149 FIX-05: add exact phrase coherence tie-break
cd03f19 Merge branch 'main' of https://github.com/caijunix-droid/techjam-conversational-search
68497f1 FIX-04A: preserve unrelated retrieval evidence on override
992defe Merge teammate's improved retrieval with demo robustness fixes
f5f4255 docs: archive experiment handovers and research artifacts
```

Pre-pass `git status --short` showed only the untracked markdown files
already anticipated by the authorization's §2, plus `final_score_sprint_
report.md` (produced in the immediately prior pass) — no unexpected
tracked-file modification. Cleared to proceed.

---

## B. FILES PROPOSED FOR FINAL COMMIT

```text
 M README.md                                          (documentation only)
?? markdowns/FINAL_SUBMISSION_STATE.md                (new, this pass)
?? markdowns/MASTER_HANDOVER_ROUND3.md
?? markdowns/final_score_sprint_report.md
?? markdowns/fix04a_commit_and_merge_reconciliation.md
?? markdowns/fix04a_implementation_handover.md
?? markdowns/fix05_commit_push_report.md
?? markdowns/fix05_implementation_handover.md
?? markdowns/fix05p0_exact_phrase_tiebreak_simulation.md
```

All eight untracked files were inspected (not assumed) before being
proposed: each is a genuine implementation/simulation/audit report from
this project's own FIX-04A through final-score-sprint work, already
correctly located under `markdowns/` — no file needed to be moved or
archived from elsewhere, and none is scratch, a debug script, a JSON
instrumentation dump, or local benchmark output. Nothing was excluded from
this list on the grounds of being superseded — per the authorization's own
instruction, historical reports are left as historical, not rewritten.

---

## C. README CHANGES

`README.md` — the file was still, in substance, the organizer's original
starter-kit template: it never described what the team actually built, its
architecture, its final score, or its limitations (matching round 1's own
long-standing open item that this had "still not been started"). Added,
verified against the code/data before writing (not assumed):

- **Title/intro**: reframed as "Team Submission," states the headline
  88.0% HR@10 up front.
- **"What This Agent Does" + the `active_slots` vs `slots` key insight**,
  in plain language — the single largest source of the project's own early
  lost hits, per `markdowns/fix01_intent_override_handover.md` onward.
- **"Architecture"**: the exact four-tier ranking pipeline (term coverage
  → slot coverage → phrase coherence → BM25), matching `starter/agent.py`'s
  actual `candidate_asins.sort()` key order line-for-line.
- **"Final Performance"**: full metrics table + scenario breakdown, taken
  directly from the already-verified `ce71149` numbers (re-confirmed fresh
  in §H below, not just copied forward).
- **"Baseline distinction"**: explicitly separates the organizer's 12.5%
  weak reference (`docs/baseline_results.json`) from the team's own 73.0%
  early milestone (commit `500fe7b`) — verified by `grep`ing the actual
  commit history rather than trusting the authorization's own stated
  figure at face value (see §E).
- **"Quick Start"**: corrected to the actual runnable commands, including
  the demo's real invocation (`python3 -m demo.interactive`, read directly
  from `demo/interactive.py`'s own docstring rather than guessed), and an
  explicit distinction between the scored evaluator and the unscored demo.
- **"Model Choice and Cost" disclosure, "Runtime," "Limitations"**: see §E.
- **"Files"**: corrected — it previously described `starter/agent.py` as
  "editable weak starter" (stale; that file is now the team's finished
  submission) and never mentioned `starter/agent_baseline.py`,
  `tests/`, `demo/`, or `markdowns/` at all.

Everything organizer-required was preserved unchanged: the Task
description, Download-the-Catalog instructions, the `Agent` interface
contract, the TechnicalScore formula, the Model Choice policy paragraph,
the Judging/Submission Policy links, and the Data Source attribution.
Nothing under `docs/`, `demo/`, `starter/`, `evaluator/`, or `tests/` was
edited.

---

## D. DOCUMENTATION ARCHIVED

No file needed to be moved — all reviewed engineering evidence was already
under `markdowns/` from the passes that produced it. One new canonical
file was created (it did not already exist, checked directly):
`markdowns/FINAL_SUBMISSION_STATE.md`, recording only verified facts (see
§H) plus an explicit "what this file deliberately does not claim" section,
per the authorization's own instruction not to claim private-set
performance, a confirmed runtime root cause, or production-deployment
readiness.

No historical report was rewritten.

---

## E. SUBMISSION DISCLOSURES

All verified directly against the code before writing, per the
authorization's own "do not assume" instruction:

```bash
grep -n "^import\|^from" starter/agent.py evaluator/local_evaluator.py demo/interactive.py
find . -maxdepth 1 -iname "requirements*.txt" -o -iname "pyproject.toml" -o -iname "setup.py"
grep -rn "requests\.|openai|anthropic|http://|https://|urllib|socket\." starter/agent.py evaluator/local_evaluator.py
```

```text
Dependencies:               Python standard library only (json, re, sqlite3,
                             pathlib, argparse, random, statistics, uuid,
                             collections) across agent.py, local_evaluator.py,
                             AND demo/interactive.py. No requirements.txt /
                             pyproject.toml / setup.py exists or is needed.
External inference API calls: 0
LLM tokens used during scoring: 0  (usage.prompt_tokens/completion_tokens
                                     always 0 -- confirmed in local_evaluator's
                                     own reported_token_usage output, §H)
Estimated API inference cost: $0
Network access required for scoring: none -- no network-call pattern found
                                             anywhere on the scoring path
Runtime: ~84.7-86.8s / 200 sessions, measured on the development machine
         (not a universal figure; suspected but NOT profiler-confirmed cause
         disclosed as a hypothesis, not a fact)
```

Limitations disclosed in the README (§ "Limitations"), each backed by an
existing project report rather than asserted fresh: private-set generality
is unverified; the architecture is intentionally lexical (embeddings
tried and rejected — `fix03_final_major_opportunity_audit.md`, citation
verified by `grep`); the phrase-coherence tier's alignment with how this
specific benchmark generates constraint text (`fix04a_implementation_
handover.md`, `fix05p0_exact_phrase_tiebreak_simulation.md`); the runtime
increase; and the final-sprint's own "no safe experiment" conclusion.

---

## F. REPOSITORY HYGIENE FINDINGS

```bash
git status --short --ignored
```
```text
!! .claude/                  (already ignored)
!! data/catalog.jsonl         (already ignored)
!! data/catalog.jsonl.gz      (already ignored)
!! demo/__pycache__/          (already ignored)
!! evaluator/__pycache__/     (already ignored)
!! results.json               (already ignored)
!! starter/__pycache__/       (already ignored)
!! tests/__pycache__/         (already ignored)
```

`.gitignore` (already present, inspected — not modified) already covers
`__pycache__/`, `*.py[cod]`, `.DS_Store`, `.env`, `results.json`,
`data/catalog.jsonl(.gz)`, `data/SHA256SUMS`, `*.log`, plus organizer-only
paths (`organizer/`, `secure/`, `docs/audits/`, etc.). `git ls-files`
(tracked files only) contains no API keys, credentials, large catalog
data, or scratch output — checked directly, not assumed. **No `.gitignore`
change was needed.**

`README.md`'s "Judging and Submission Policy" section references
`docs/participant_release_checklist.md` and three files under `organizer/`
that do not exist in this working copy — checked directly
(`ls docs/participant_release_checklist.md` → not found). This is
**expected, not a defect**: `.gitignore` explicitly excludes exactly these
paths as "Organizer-only code, private evaluation data, manifests, and
build reports" / "Internal provenance and release-audit working
documents" — the same intentional-exclusion pattern as `organizer/`
itself. Left unchanged.

No stray untracked file exists anywhere outside `markdowns/` and the
already-ignored paths — confirmed via
`git status --short --ignored=no | grep -v '^?? markdowns/'`, which
returned only the modified `README.md`.

---

## G. TEST RESULTS

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```
```text
Ran 54 tests in 0.067s
OK
```

54/54 PASS, 0 failures, 0 errors — run after the documentation changes,
confirming (as expected, since no scoring file was touched) the metrics
are unchanged.

---

## H. CLEAN-CLONE / REPRODUCIBILITY RESULTS

A fresh local clone of the committed repository state (`git clone` from
this working copy, landing at `ce71149` — identical to what a judge
cloning from `origin` would receive) was created, the catalog placed into
it per the README's own documented instructions (copied from the local
catalog into the clone's `data/` directory, exactly as a judge would do
after downloading the release), and verified from that clean clone (not
from the development working tree):

```text
python3 -m unittest discover -s tests -p 'test*.py':   54 / 54 PASS
Agent import + instantiation (loads/builds the FTS index): OK
demo.interactive import:                                    OK
python3 -m evaluator.local_evaluator (full 200 sessions):
  hit_rate_at_10: 0.88, mrr: 0.567583, mttc: 5.495,
  efficiency: 0.5505, recommended_technical_score: 0.720375,
  reported_token_usage: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
  -- exact match to the numbers already reported, reproduced independently
     from a genuinely separate clone/working tree.
```

The full clean-clone evaluator run was practical (catalog available
locally) and was actually performed — this is not claimed without having
been run. The temporary clone was deleted after verification (scratch,
outside the repository, never committed).

Not verified in a clean clone: the interactive demo's live input/output
loop itself (requires a real terminal/stdin; its import and the shared
`Agent` construction it depends on were verified instead, which is the
part that could plausibly break from a packaging defect).

---

## I. EXACT FINAL `git status --short`

```
 M README.md
?? markdowns/FINAL_SUBMISSION_STATE.md
?? markdowns/MASTER_HANDOVER_ROUND3.md
?? markdowns/final_score_sprint_report.md
?? markdowns/fix04a_commit_and_merge_reconciliation.md
?? markdowns/fix04a_implementation_handover.md
?? markdowns/fix05_commit_push_report.md
?? markdowns/fix05_implementation_handover.md
?? markdowns/fix05p0_exact_phrase_tiebreak_simulation.md
```

---

## J. PRODUCTION FILE CHECK

```text
starter/agent.py changed?                 NO  (git diff --stat: empty; SHA256
                                                unchanged: ab99c72e...)
tests/test_fix05_phrase_tiebreak.py changed? NO  (git diff --stat: empty; SHA256
                                                unchanged: b39107ab...)
evaluator/local_evaluator.py changed?     NO  (git diff --stat: empty)
Any other file under starter/, tests/, evaluator/, demo/, data/ changed? NO
```

---

## K. CLASSIFICATION

```text
READY FOR FINAL DOCS/README COMMIT
```

Per the authorization's own §12: **no `git add`, `git commit`, or
`git push` was performed.** This report, the updated `README.md`, and the
newly-written `markdowns/FINAL_SUBMISSION_STATE.md` are returned for Sam +
independent review. The scoring floor (`ce71149`) is exactly as it was at
the start of this pass — confirmed by empty diffs and unchanged SHA256
hashes on every scoring-path file, not merely by absence of an intent to
edit them.
