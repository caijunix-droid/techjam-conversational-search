# Handover 2 — Independent Verification Findings (for backtesting)

## Purpose of this document

This is a **verification handover**, not a design doc. It was produced by independently
reproducing the claims in `HANDOVER.md` against the actual code and the real organizer
dataset, then probing specific spec requirements from
`TechJam2026_Shopping_Copilot_Hackathon_Slides_Digested.md` against the live agent.

**No code was edited to produce this document.** Everything below is either:
- **OBSERVED** — directly seen by running the real code, or
- **CODE-DERIVED** — directly read from the current source, or
- **INFERENCE** — explicitly labeled as such.

If you are the LLM picking this up: your job is to **backtest these findings**, not trust
them. Re-run the reproduction commands yourself before acting on any of this. Treat every
claim here as a hypothesis with attached evidence, not a verdict.

---

## 0. Environment / reproduction prerequisites

The repo does not ship the product catalog (by design, gitignored). To reproduce anything
below you need it locally:

```bash
curl -sL -o data/catalog.jsonl.gz \
  https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz
gunzip -k data/catalog.jsonl.gz
# Optional integrity check — compare against SHA256SUMS in the same release
```

Verified: SHA256 of the downloaded `catalog.jsonl.gz` matches the release's `SHA256SUMS`
file exactly. Decompressed row count = 50,000 (matches spec).

Repo state at time of this verification:
- Branch: `main`, clean working tree
- Commit: `9b5fc2f` "Add improved shopping agent with dialog memory + live demo script"
- Files: `starter/agent.py` (current/"improved" agent), `starter/agent_baseline.py`
  (byte-identical copy of the organizer's original stub agent — confirmed via `diff`
  against `git show 2a6cc8e:starter/agent.py`), `evaluator/local_evaluator.py`,
  `demo/interactive.py`

---

## 1. Claims from `HANDOVER.md` that were reproduced (CONFIRMED)

Ran `python -m evaluator.local_evaluator` twice, in independent processes, against the
real 200-session public set + real 50k catalog:

| Metric | HANDOVER.md claim | Run 1 (observed) | Run 2 (observed) |
|---|---:|---:|---:|
| Hit Rate@10 | 0.73 | 0.73 | 0.73 |
| MRR | 0.465 | 0.465458 | 0.465458 |
| MTTC | 6.35 | 6.345 | 6.345 |
| Technical Score | 0.598 | 0.597737 | 0.597737 |

Runs were byte-identical except for randomly generated session UUIDs — fully deterministic.
The pre-existing `docs/baseline_results.json` also matches the handover's "weak baseline"
row exactly (0.125 / 0.068034 / 9.81 / 0.10671).

Also confirmed:
- No network/API calls anywhere in `starter/` or `demo/` (grepped for
  `requests|openai|anthropic|urllib|http.client|socket`) — supports the "no paid LLM, no
  external API" claim.
- `tests/test_evaluator.py` (3 tests) passes via `python3 -m unittest tests.test_evaluator`.
- `demo/interactive.py` runs end-to-end with piped scripted input, returns plausible
  ranked products, no crash.

**Not independently verifiable**: the three "tried and reverted" ideas in HANDOVER.md
(slot erasure on override, tiered strict/loose search, retrieval cutoff). Git history
(`git log --oneline --all -- starter/`) shows only two commits total — the organizer's
original stub and one rewrite commit. There are no intermediate commits for these
experiments, so their code doesn't exist to inspect or test. Take this section of
HANDOVER.md as the team's word, not as verified fact.

---

## 2. Findings against the TechJam spec (this session's new work)

### 2.1 — REAL_PRODUCT_DEFECT (confirmed): Intent Override does not replace the old constraint

**Spec requirement** (slides digest §"Slide 9", doc §6.3): when the customer says
"Actually, ignore my earlier preference. What I need is: X," the **old** constraint must
be replaced, not accumulated alongside the new one. This is explicitly the "weak agent
appends / strong agent replaces" test case, and Intent Override is 15% of the benchmark
mix.

**Code path**: [`starter/agent.py:161-167`](../starter/agent.py#L161-L167)

```python
if text.startswith("Actually, ignore my earlier preference. What I need is: "):
    new_value = text[len("Actually, ignore my earlier preference. What I need is: "):].rstrip(".").strip()
    if new_value:
        attr = classify(new_value)
        state.slots[attr] = new_value   # only overwrites the NEW value's own bucket
    return
```

This only clears/overwrites whichever bucket the **new** value classifies into. It never
looks at which bucket the **old** value was filed under. If old and new value classify to
different attribute buckets, the old one survives untouched.

**Reproduction**: [`probes/probe_override_batch.py`](probes/probe_override_batch.py) —
runnable as-is (`python3 markdowns/probes/probe_override_batch.py` from repo root, once
`data/catalog.jsonl` is present per §0). Runs against all 30 real intent-override sessions
in `data/public_set.jsonl`, using the evaluator's own `materialize_hidden_fields` to derive
the real intent card and override behavior (not synthetic data). Core loop: `agent.reset()`
→ replay real session turns via the evaluator's own `initial_message`/`customer_reply` →
after the override turn, inspect `agent._sessions[session_id].slots` directly.
A single-session, verbose version (prints every turn) is at
[`probes/probe_override_single.py`](probes/probe_override_single.py).

**Observed result**:
- 30/30 real override sessions checked.
- 24/30 (80%) have old_value and new_value classified into *different* attribute buckets.
- Of those 24, **24/24 (100%)** still have the stale old value present in `state.slots`
  after the override message is processed.

Example (`public_0002`):
```
intent_card.hard_constraints = ["leather", "100% Leather"]
override.old_value = "Buckle closure"   (classify() -> "feature")
override.new_value = "leather"          (classify() -> "material")
override message: "Actually, ignore my earlier preference. What I need is: leather."

state.slots BEFORE override: {'feature': 'Buckle closure', 'material': '100% Leather'}
state.slots AFTER override:  {'feature': 'Buckle closure', 'material': 'leather'}
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                          "ignored" constraint never left
```

**Corroborating product-impact signal**: in the full 200-session run (§1 above), the
per-scenario breakdown shows Intent Override as the **worst-performing scenario**:

```
boundary:         hit_rate 0.700
browsing:         hit_rate 0.7125
buying:           hit_rate 0.7875
intent_override:  hit_rate 0.6333   <- lowest
```

This is consistent with (does not alone prove) the stale-constraint defect degrading
retrieval on override sessions specifically.

**Classification**: `REAL_PRODUCT_DEFECT`. Directly contradicts an explicit, named spec
requirement, reproduced deterministically, corroborated by real scored data.

**Not yet done / left for backtest**: I did not measure the *counterfactual* — i.e., how
much HR@10/MRR would improve on the override subset if the stale bucket were correctly
cleared. That requires a code change and a re-run, which was out of scope for this
read-only pass (explicitly instructed not to edit).

---

### 2.2 — REAL_PRODUCT_DEFECT / architectural gap (confirmed): budget/price is never enforced

**Spec requirement** (doc §6.1): "price ceiling" is given as an example "active hard
constraint" that should "strongly filter or penalize candidates that violate them."

**Evidence**:
```bash
grep -n "price" starter/agent.py   # zero matches
```
The FTS5 virtual table schema ([`starter/agent.py:101-105`](../starter/agent.py#L101-L105))
only carries these columns: `parent_asin, title, categories, features, details, store,
description`. `price` is not indexed, not stored alongside the FTS row, and never read
anywhere in `respond()`.

**Consequence**: a customer message like "under $80" gets tokenized by `_terms()` into
loose words ("under", "80") and OR'd into the FTS5 query against product *text* — it has
no relationship to the catalog's actual numeric `price` field. A stated budget constraint
is inert; it can only coincidentally help if a product's title/description happens to
contain a matching numeral.

**Classification**: `REAL_PRODUCT_DEFECT` relative to the explicit spec example, though
also an **architectural gap** — fixing it requires carrying `price` through to
query/rank time (the FTS5 schema itself has no numeric filtering capability), not just a
one-line parsing fix like §2.1.

---

### 2.3 — Disclosed gap, but real (EXPECTED given honest self-disclosure, still worth flagging): no semantic/dense retrieval, no query rewriting, no reranking

**Evidence**:
```bash
grep -n "^import\|^from" starter/agent.py starter/agent_baseline.py demo/interactive.py
# only json, re, sqlite3, pathlib, uuid, sys — no embeddings/LLM/vector libs anywhere
find . -iname "requirements*.txt" -o -iname "pyproject.toml"   # none found
```

This matches HANDOVER.md's own "not built" disclosure — not a hidden gap. Flagging it here
because:
- The slides digest (Slide 12) states "The solution includes LLM Semantic Ranking" as if
  describing an expected component of a competitive submission.
- These are the exact three levers the slides name as the biggest score opportunity
  (retrieval / state / clarification — Slide 13), and semantic reranking specifically is
  named "in scope" (Slide 4, Slide 7 blueprint).
- Event-level judging weights Technical Execution (35%) and Innovation (20%) = 55% of the
  total score, and the local evaluator's HR@10/MRR/MTTC numbers do not capture that
  dimension at all — a team could hold the current metrics steady and still lose on
  judging criteria the local evaluator can't see.

**Classification**: `EXPECTED / ACCEPTABLE SEMANTICS` relative to the local evaluator
(nothing here breaks the contract or the scored metrics), but a real, named gap relative
to the full competition rubric.

---

### 2.4 — Minor, low-frequency (confirmed, deprioritized): compound single-string constraints lose one attribute

**Hypothesis**: `classify()` in [`starter/agent.py:56-73`](../starter/agent.py#L56-L73)
returns exactly one bucket per text string via an if/elif chain (budget → material →
color → size → style → use_case → feature). If a single constraint string mentions two
attribute types at once (e.g., a color word *and* a material word), only the
higher-priority one gets recorded as "known" — the other is never marked filled, and the
agent could later ask a redundant question whose answer was already given.

**Reproduction**: [`probes/probe_compound.py`](probes/probe_compound.py) — runnable as-is.
Scans all 800 real constraint strings (hard_constraints + soft_preferences, derived via
the evaluator's own `materialize_hidden_fields`) across all 200 public sessions for
strings matching both `MATERIAL_RE` and `COLOR_RE`.

**Observed result**: 3/800 (0.4%) constraint strings hit this pattern. Example:
```
"Solid colors: 100% Cotton; Heather Grey: 90% Cotton, 10% Polyester; ..." -> classified as 'material'
```

**Classification**: confirmed real, but `INSUFFICIENT` prevalence to prioritize (0.4% of
constraints, likely negligible MTTC cost). Listed for completeness, not urgency.

---

### 2.5 — Design choice, not a defect: static one-question-per-turn clarification

**Spec framing** (Slide 2): "A better question can be more valuable than another
retrieval call" — implies the decision to ask should be dynamic/value-aware.

**Code**: [`_next_ask_attribute`](../starter/agent.py#L209-L218) always asks about the
next unfilled attribute in a fixed `ASK_ORDER` if any remain and `turn < 10` — there is no
cost/value estimation, it's unconditional.

HANDOVER.md claims a dynamic variant ("retrieval cutoff when candidate pool is small") was
tried and reverted because it measured worse (increased average turns). **This claim is
not verifiable from git history** (see §1) — only two commits exist, no intermediate
experiment commits. Take it as team testimony, not evidence.

**Classification**: `EXPECTED / ACCEPTABLE SEMANTICS` given the (unverified) empirical
claim that the alternative was worse — but note that the spec's named "adaptive
clarification / question-value estimation" innovation direction remains, as far as
committed code shows, unexplored.

---

## 3. Summary table

| # | Finding | Classification | Evidence strength | Prevalence |
|---|---|---|---|---|
| 2.1 | Intent override doesn't clear old constraint | REAL_PRODUCT_DEFECT | Reproduced on 24/24 applicable real sessions | 24/30 (80%) of override sessions |
| 2.2 | Budget/price never enforced against numeric price | REAL_PRODUCT_DEFECT (architectural) | Direct code read + grep, zero ambiguity | 100% of budget-bearing sessions |
| 2.3 | No semantic/dense retrieval or reranking | EXPECTED (disclosed) but rubric-relevant | Direct import/dependency inspection | Applies to whole system |
| 2.4 | Compound-attribute single-bucket loss | Confirmed, low priority | Scanned 800 real constraint strings | 3/800 (0.4%) |
| 2.5 | Static clarification cadence (no value-aware skip) | Design choice, team claims tested | Code confirmed; team's "tested worse" claim unverifiable in git history | N/A |

---

## 4. What the next LLM should backtest before acting

1. **Re-run §1's reproduction** independently — don't trust these numbers without
   re-running `python -m evaluator.local_evaluator` yourself first.
2. **Re-verify §2.1** on at least a handful of the 24 flagged sessions (sample_ids are
   listed in the original probe output — re-derivable via `materialize_hidden_fields`) —
   confirm the stale-slot persistence independently before treating it as ground truth.
3. **Quantify the counterfactual** for §2.1 and §2.2: what's the actual HR@10/MRR delta on
   the Intent Override subset (and overall) if these are fixed? This was explicitly left
   undone here (no code changes were made in this pass).
4. **Treat §2.3 as a scope/priority decision for the user, not a bug** — confirm with the
   user whether they want to invest hackathon time in semantic reranking given the
   deadline, before spending effort there.
5. Do **not** assume the three "reverted experiments" in `HANDOVER.md` are true or false —
   there's no code or commit evidence either way. If it matters, ask the team member who
   claims to have run them.

## 5. Explicitly not done in this pass

- No code was modified.
- No fix was implemented or tested for §2.1 or §2.2.
- No attempt was made to reproduce or refute the three reverted-experiment claims beyond
  checking git history for their absence.
