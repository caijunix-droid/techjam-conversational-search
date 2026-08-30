# FIX-03 — Final Major Opportunity Audit

Written 2026-08-31. Executes `TECHJAM FINAL SPRINT — LOCK A2 + LAUNCH FINAL MAJOR
DIAGNOSTIC.md`. Phase 0 (commit A2) is complete and reported first. Phase 1 (the
combined diagnostic) is **read-only** — no production edits, no staging, no new
commit, no push beyond the Phase-0 A2 commit.

---

## 1. A2 committed baseline

Phase 0 executed exactly:

```bash
git rev-parse HEAD                              # c30c712... (before)
shasum -a 256 starter/agent.py                   # e3f324ca... (before)
python3 -m unittest discover -s tests -p 'test*.py'   # 30/30 PASS
python3 -m evaluator.local_evaluator             # matched required numbers exactly
git add starter/agent.py tests/test_fix02a2_slot_coverage_tiebreak.py
git commit -m "FIX-02A2: add active-slot coverage tie-break"
```

```
[main c642094] FIX-02A2: add active-slot coverage tie-break
 2 files changed, 289 insertions(+), 1 deletion(-)
```

Post-commit: `git rev-parse HEAD` → `c64209406be14fb0a0e823f7a9136c05284bdbf4`.
`git status --short` shows only pre-existing untracked markdown/research files.
**Not pushed** (per governance, push requires separate authorization).

Verified baseline for everything below:

```
HEAD             c642094
HR@10            0.810000
MRR              0.496028
MTTC             5.815000
Efficiency       0.518500
TechnicalScore   0.657508
Hits             162 / 200
Misses            38 / 200
```

---

## 2. Remaining miss distribution (post-A2)

```
Browsing          16
Buying            11
Intent Override    9
Boundary           2
Total              38
```

Bucketed by `FIX-02-P0`'s A/B/C/D classification (re-cross-referenced against
the current miss set, not assumed carried over):

```
A (Top50 baseline, coverage-tie)   18
B (rank 51-100)                    13
C (rank 101-500)                    6
D (>500/absent)                     1
Total                              38
```

Matches the audit brief's own stated approximation (`~18/13/6/1`) exactly.

---

## PART A — INTENT OVERRIDE RECOVERABILITY

### 3. Intent Override traces (A1)

All 9 remaining Intent Override misses (`public_0002, 0038, 0052, 0071, 0096,
0144, 0177, 0183, 0198`) were traced turn-by-turn against the live, current
(A2) `Agent`, capturing `active_slots`/`slots` before and after
`_parse_message` on every turn, `override_applied` gating, and target rank at
Top10/Top50/Top100 (raw BM25, no rerank — pure retrieval-depth diagnostic).
Full trace: `override_trace_output.json` (scratch, not part of the repo).

**Every session follows the identical structural pattern** — summarized once
here rather than 9 times:

```
Turn 1: opener sets ONE slot (classified "feature" in all 9 cases -- values
        like "Buckle closure", "Hand Wash Only", "Pull On closure" never
        match MATERIAL_RE/COLOR_RE/etc., so classify() defaults to "feature").
        override_source_attr/value = ("feature", <that value>).

Turn 2 (or later): a clarification answer sets a DIFFERENT slot -- in 8/9
        cases, "material" (the disclosed fabric composition).

Override turn: the scripted message "Actually, ignore my earlier preference.
        What I need is: {X}." fires. X is always the target's own material
        term (from intent_card()'s hard_constraints[0]).
        - The tracked "feature" slot is deleted (matches its recorded value
          exactly in all 9 cases -- the conditional-delete guard fires
          cleanly every time).
        - X gets classified (almost always "material" again) and OVERWRITES
          whatever was already in that bucket from the clarification turn --
          even though the override message never named that bucket.
```

### 4. Override semantic/state classification (A2)

Per session, what gets removed and why, classified from message semantics
and state-update mechanics only — not from whether preserving it would help
the target's rank:

| Session | Turn-1 tracked slot removed | Classification | Material-slot overwrite | Classification |
|---|---|---|---|---|
| `public_0002` | feature: "Buckle closure" | **SUPERSEDED** — explicitly named | "100% Leather" → "leather" | STRUCTURAL LOSS (minor — "100%" qualifier only, substance retained by coincidence) |
| `public_0038` | feature: "Lace Slip On Sneaker" | **SUPERSEDED** | none — new value "Textile" also classifies to "feature" (same tracked bucket) | n/a — clean supersession |
| `public_0052` | feature: "Hand Wash Only" | **SUPERSEDED** | "60% polyester" → "polyester" | STRUCTURAL LOSS (minor) |
| `public_0071` | feature: "Pull On closure" | **SUPERSEDED** | "90% Cotton, 10% Others" → "cotton" | **STRUCTURAL LOSS (major — "10", "others" destroyed, not named by the override message)** |
| `public_0096` | feature: "Pull On closure" | **SUPERSEDED** | "95% Polyester, 5% Spandex" → "polyester" | **STRUCTURAL LOSS (major — "spandex" destroyed, a real disclosed fact never contradicted)** |
| `public_0144` | feature: "Zipper closure" | **SUPERSEDED** | "100% Polyester" → "polyester" | STRUCTURAL LOSS (minor) |
| `public_0177` | feature: "Button closure" | **SUPERSEDED** | "Cotton, Rayon" → "cotton" | **STRUCTURAL LOSS (major — "Rayon" destroyed; customer disclosed two possible materials, override silently drops one)** |
| `public_0183` | feature: "Hand Wash Only" | **SUPERSEDED** | "100% Polyester" → "polyester" | STRUCTURAL LOSS (minor) |
| `public_0198` | feature: "Imported" | **SUPERSEDED** | "leather" → "leather" (identical value) | n/a — no information lost |

**No `AMBIGUOUS` cases** — the override message's own text ("ignore my
earlier preference", singular) unambiguously names only the turn-1 tracked
preference in every session; nothing in any message authorizes discarding a
*different* slot's value. The classification above follows directly from
that text, not from rank impact.

**The turn-1 deletion mechanism (the one B0 already had a conditional-delete
guard for) works correctly in all 9/9 cases — this is not the defect.** The
defect is specifically: the override's new value can land in a bucket that
was *never named* by the override message, and the code has no equivalent
guard there — it just overwrites unconditionally.

**Rank impact directly traceable to the major structural-loss cases**:
`public_0071` (rank 1 → 44 at the override turn), `public_0096` (rank 23,
in-pool → not found in Top100 at all), `public_0177` (rank 8 → not found in
Top100 at all) — all three show severe regressions exactly at the turn the
richer material description gets clobbered down to a single common word.

### 5. Override recoverability simulation (A3)

**One general correction was formulated and simulated** (not implemented in
production): when applying the override's new value, if the target bucket
already holds a value **and that bucket is not the tracked
`override_source_attr` bucket**, append the new value instead of overwriting
(retrieval evidence `state.slots` is untouched either way — this only changes
`state.active_slots`). If the bucket is empty, or is the tracked source
bucket itself, behavior is byte-identical to production.

This is fully general: it depends only on which bucket a value classifies
into and which bucket was tracked as superseded — no session ID, ASIN, or
scenario-specific logic anywhere.

**Full 200-session counterfactual** (simulated via a scratch copy of the
current committed `agent.py` with only this one branch changed — production
`starter/agent.py` was never touched):

| Metric | A2 (committed) | +Override correction | Δ |
|---|---:|---:|---:|
| HR@10 | 0.810000 | **0.825000** | **+0.015 (net +3 hits)** |
| MRR | 0.496028 | **0.510105** | **+0.014077** |
| MTTC | 5.815000 | **5.680000** | **−0.135** |
| Efficiency | 0.518500 | **0.532000** | **+0.0135** |
| TechnicalScore | 0.657508 | **0.671932** | **+0.014424** |

Intent Override scenario specifically:

| Metric | A2 | +Correction |
|---|---:|---:|
| HR@10 | 0.700000 | **0.800000** |
| MRR | 0.528929 | **0.622778** |
| MTTC | 6.766667 | **5.866667** |

**Boundary, Browsing, and Buying scenario metrics are byte-identical before
and after** — confirming the correction is exactly scoped to the
`intent_override` code path and touches nothing else, as expected (only that
scenario type ever exercises the override branch).

**Session deltas, full 200-session diff:**

```
new hits:          3   -- public_0052 (rank 4, turn 3), public_0071 (rank 1,
                          turn 4), public_0183 (rank 6, turn 4)
new misses:         0
rank improvements:  4   -- public_0064 (7->2), public_0078 (4->1),
                          public_0080 (4->2), public_0103 (8->6)
rank regressions:   0
turn improvements:  1   -- public_0078 (turn 8->3)
turn regressions:   0
unchanged:        193
```

**All 4 rank-improved sessions are also Intent Override** — the correction
touches exactly 7 sessions total, all in-scenario, all strictly improved or
newly hit, zero regressions of any kind on any of the other 193 sessions.
`public_0103` is one of B2's own 6 originally-flagged regression sessions
(`fix01b2_term_coverage_end_to_end_simulation.md`) — this correction improves
it further (rank 8 → 6), not worsens it.

**Remaining Intent Override misses after this correction**: 6 —
`public_0002, 0038, 0096, 0144, 0177, 0198`. `public_0002` and `public_0144`
were never blocked by state collapse in the first place (their targets sit
too deep in raw BM25 rank regardless of override handling — a retrieval-depth
problem, not a state problem). `public_0038`, `0096`, `0177`, `0198` still
miss even with the corrected state — the correction fixes the *specific*
structural-loss mechanism identified in §4, not every possible cause of an
Intent Override miss.

### Classification: OVERRIDE FAMILY — HIGH RECOVERABLE OPPORTUNITY

General, mechanistically-explained, zero-regression, +3 net hits / +0.0144
TechnicalScore, fully reproducible. This is the strongest, cleanest result of
this entire FIX-02/FIX-03 series.

---

## PART B — SEMANTIC / HYBRID RETRIEVAL FEASIBILITY

### 6. Environment audit (B1)

```
Python version:           3.12.6
Repo dependency manifest: NONE FOUND (no requirements.txt, pyproject.toml,
                           or setup.cfg anywhere in the repo)
starter/agent.py imports: json, re, sqlite3, pathlib -- Python standard
                           library ONLY, through every FIX-01/FIX-02 pass to
                           date. Adding any third-party package would be the
                           FIRST external dependency this project has taken.
```

**Organizer runtime constraints** (`docs/submission_rules.md`, read directly,
not recalled):

```
"For official final scoring, organizer policy may disable network access."
"your submission must clearly document whether it requires network access"
"if your system has an offline fallback, describe it"
"The organizer reserves the right to run your submission under CPU, memory,
 timeout, and network restrictions." -- no specific numeric limits given
"Your submission package must contain: ... dependency manifest and install
 instructions"
```

**MEASURED FACT**: this development session's ambient `pip` environment
contains `numpy`, `scipy`, `scikit-learn`, `onnxruntime`, and even
`tensorflow`/`keras`/`chromadb`/`huggingface_hub`/`tokenizers` — but this is a
broad, generic, multi-project workstation environment (also contains
`streamlit`, `pyspark`, `yfinance`, `xgboost` — clearly not scoped to this
repo). **ENGINEERING JUDGMENT**: none of this can be assumed present at
organizer scoring time. The repo declares zero dependencies today; whatever
manifest gets submitted is what the organizer's environment would actually
be built from, and the submission rules explicitly flag that network access
(needed for `pip install` of anything not pre-bundled, and certainly for any
model download) may be disabled at scoring time. No local pretrained model
asset file (`.onnx`, `.bin`, `.safetensors`, `.pkl`, `.vec`) exists anywhere
in this repo.

**Conclusion**: per the audit's own preference order, tier 1 ("existing local
semantic/embedding capability already supported by repo/dependencies") does
not exist — the repo supports nothing beyond the standard library. Tier 3
(adding a new dependency, let alone a model download) carries real,
undocumented risk given the network-access uncertainty. This audit proceeds
with **tier 2**: the lightest deterministic local representation available —
TF-IDF + cosine similarity (`scikit-learn`), trained entirely on the local
catalog corpus at index-build time, with **no model download, no network call
of any kind, ever** — while explicitly flagging that even this is a **new**
dependency relative to the repo's current zero-dependency baseline, not a
free option.

### 7. Semantic retrieval recall (B3)

TF-IDF index built over all 50,000 catalog products (title + categories +
features + details + store + description — the same six fields the FTS
index uses), unigrams+bigrams, sublinear TF, 50,000-feature cap. Query text
per turn: identical accumulated evidence to production's own `_build_query()`
(category + profile terms + all disclosed slots) — same evidence base as
BM25, different similarity mechanism, so any difference in outcome is
attributable to the ranking signal itself, not to different input.

For all 20 current B/C/D misses (best rank across all countable turns, Top100
diagnostic depth):

```
target reaches semantic Top10:    0 / 20
target reaches semantic Top20:    0 / 20
target reaches semantic Top50:    0 / 20
target reaches semantic Top100:   1 / 20   (public_0109, rank 59 -- not even
                                             inside the Top50 that any
                                             downstream reranker could work
                                             within)

combined B/C/D semantic Top50 recall: 0%  (0/20)
```

**19 of 20 targets do not appear anywhere in the semantic ranking's Top100 at
all**, across every eligible turn of the conversation.

### 8. BM25-vs-semantic overlap (B4)

Measured at each session's final (richest-evidence) turn, for the 20 B/C/D
misses and a random sample of 20 existing A2 hits (seed 42, reproducible):

```
average BM25-Top50/semantic-Top50 overlap: 14.75 / 50   (median 14)
```

Target-presence breakdown across the 20-hit sample (where BM25 already finds
the target, by definition — these sessions are currently hits):

```
both BM25 and semantic find the target:   17 / 20
BM25 only (semantic MISSES it):            3 / 20
semantic only (BM25 misses, semantic finds it): 0 / 20
neither:                                    0 / 20
```

**Semantic (TF-IDF) never once finds a target that BM25 misses, across every
session tested (0/20 in the miss set, 0/20 in the hit-sample "semantic-only"
column) — and it actively fails on 3/20 sessions where BM25 already
succeeds.** The two rankings overlap moderately (~30% of Top50 slots) but are
not complementary in the one direction that would matter: semantic never adds
a target BM25 doesn't already have.

### 9. Frozen hybrid counterfactual — NOT RUN

Per the audit's own explicit gate ("ONLY if semantic retrieval shows
meaningful orthogonal recall"), §7/§8 show **zero** orthogonal recall at any
depth tested. Constructing and running a full 200-session hybrid-candidate
counterfactual (§B5/B6) would not be a meaningful use of the "avoid repeated
evaluator runs until a mechanism survives the first quality gate" time
discipline this audit explicitly asks for. **Not run — correctly gated off,
not skipped for convenience.**

### 10. Generalization / risk analysis (B7)

Separated explicitly, as required:

**MEASURED FACT**: TF-IDF-cosine, computed purely from local catalog text
with no network/model dependency, shows 0/20 Top50 recall on the current
miss set and never surfaces a target BM25 misses, anywhere in 40 sessions
tested.

**INFERENCE**: this catalog's product descriptions are themselves
lexically literal (titles/features/details use direct attribute words —
"leather", "polyester", "cotton" — rather than descriptive paraphrase), so a
still-fundamentally-lexical/co-occurrence signal like TF-IDF has little room
to diverge usefully from BM25's own lexical matching; the two are measuring
highly correlated information from the same literal vocabulary.

**ENGINEERING JUDGMENT**: a genuinely different representation — a neural
embedding model trained to capture true paraphrase/synonym relationships
(e.g. "good in rain" ≈ "water resistant", `MASTER_HANDOVER.md`'s own T6
example) — was **not tested in this pass**, per explicit governance ("Do NOT
download or integrate a model into production in this diagnostic pass").
This is a real, acknowledged gap, not a claim that all semantic approaches
would fail — only that the lightest, dependency-free tier does, decisively,
on this specific public set.

**Would this generalize to the private 800 sessions?** Not established
either way — this audit only measured the public set. Given the catalog
itself (shared between public and private scoring, per
`fix01b1_private_generation_evidence_audit.md`'s established methodology) is
the same literal-vocabulary source, there's no specific reason to expect
TF-IDF to perform differently on private sessions, but this is inference, not
measurement.

**Dependency/runtime risk**: `scikit-learn` is not currently a repo
dependency; adding it (for a signal shown to add zero value here) is not
justified. **False-positive competition risk**: not evaluated further — moot,
since the signal showed no value to weigh against it.

---

## 11. Full evaluator deltas

Only Part A produced a mechanism worth full-evaluator reporting — done in
§5 above (full 200-session HR/MRR/MTTC/Efficiency/TechnicalScore, scenario
breakdown, and complete session-delta table). Part B's semantic signal never
passed its own quality gate (§9), so no full-evaluator run was performed for
it, consistent with the audit's time-discipline instruction not to profile a
mechanism that hasn't shown a positive signal.

---

## 12. Opportunity comparison (Phase 2 decision matrix)

| Dimension | Override correction (Part A) | Semantic/hybrid, TF-IDF tier (Part B) |
|---|---|---|
| Measured net-hit upside | **+3 / 200**, fully verified | **0** (gated off before a hybrid mechanism was even built) |
| TechnicalScore upside | **+0.014424**, measured | none measured |
| Existing-hit damage | **0 / 200**, verified | n/a (not built) |
| Scenario stability | Confined to Intent Override only, verified | n/a |
| Mechanistic clarity | Full message-semantics trace, all 9 sessions individually classified | Overlap/recall pattern well-characterized, but underlying *why* is inference-level |
| Private-set generalization risk | Low — general rule, same mechanism class as B0/B2's own already-shipped logic | Unknown — untested signal, no private-set evidence either way |
| Implementation complexity | Minimal — one conditional branch change | Would require a new dependency, index-build step, and a hybrid-merge design not yet specified |
| Runtime | Not separately measured this pass (same order of magnitude as existing state-update work; no new query layer) | N/A — not built |
| Dependency risk | None — zero new dependencies | Real — first-ever third-party dependency, with real network-access uncertainty at scoring time |
| Time-to-verify | Already done, this pass | Already ruled out at its cheapest tier, this pass |

```
OVERRIDE:           HIGH opportunity
SEMANTIC/HYBRID (TF-IDF tier): LOW opportunity (measured)
SEMANTIC/HYBRID (neural tier): UNTESTED -- not ruled in or out
```

---

## 13. Recommended next production experiment

**Implement the Part A override-state correction** (§5's exact mechanism) as
the next production experiment, following this project's established
gated workflow (implement → targeted tests → full tests → benchmark →
session-delta check → report → stop for independent review, matching
`FIX-02A2`'s own pattern) — **not done in this pass**, since this diagnostic
was explicitly read-only per its own governance.

Do **not** pursue the TF-IDF semantic tier further — it is decisively ruled
out by measurement, not by assumption. A genuinely neural/contextual semantic
signal remains a legitimate open question but was explicitly out of scope for
this pass and would need its own dedicated feasibility audit, starting from
the same environment-audit discipline in §6 (in particular: resolving the
network-access-at-scoring-time question before any model download is even
attempted).

**On the stated +8-net-hit / ≥170/200 stretch target**: Part A alone reaches
**165/200 (82.5%)** if implemented — real, verified progress, but short of
the 170/200 stretch goal by 5 hits. This gap is reported plainly rather than
implied closed. Per §5, 6 Intent Override misses remain even after this
correction (2 retrieval-depth-limited, 4 not yet re-examined for a *different*
cause now that state-collapse is accounted for) — a natural, evidence-backed
place to look next, but not yet audited in this pass.

---

## 14. STOP

No production code was edited in Phase 1. No experiment was implemented
beyond the already-authorized Phase 0 A2 commit. Nothing new was staged or
committed. Nothing was pushed. This report, including the full override
trace/classification (§3-5) and the semantic recall/overlap evidence (§7-8),
is ready for independent review.
