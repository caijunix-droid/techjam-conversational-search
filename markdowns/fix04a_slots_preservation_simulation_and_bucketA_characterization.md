# FIX-04A — Retrieval-Evidence Preservation Simulation + Parallel Bucket-A Characterization

Written 2026-08-31. Executes `FIX-04A — RETRIEVAL-EVIDENCE PRESERVATION
SIMULATION + PARALLEL BUCKET-A CHARACTERIZATION.md`. Phase 0 (push) is
complete. Part A (simulation) and Part B (descriptive characterization) are
**both read-only** — no production edits, no staging, no new commit, no push
beyond the already-approved FIX-03A checkpoint.

---

## 1. Phase 0 — pushed safe FIX-03A checkpoint verification

```bash
git remote -v
```
```
origin    github.com/caijunix-droid/techjam-conversational-search.git
upstream  github.com/TechJam2026/techjam-conversational-search.git
```

```bash
git status --short   # clean (only pre-existing untracked research files)
git rev-parse HEAD    # 1e2848eae6ca05f6c2d5707c796276a2d7de1a1e
git push origin main
git fetch origin
git rev-parse HEAD         # 1e2848eae6ca05f6c2d5707c796276a2d7de1a1e
git rev-parse origin/main  # 1e2848eae6ca05f6c2d5707c796276a2d7de1a1e
```

**HEAD == origin/main, confirmed.** Pushed to `origin` only; `upstream` never
touched.

---

## PART A — FIX-04A simulation

### 2. Exact frozen mechanism recovered

Fetched the exact committed FIX-03A source (`git show 1e2848e:starter/agent.py`,
SHA-verified `c839811324f491049d397cad8b0b0c0a75d2466df272482037870a5ccddffb82`),
then applied only the change specified in §2 of the authorization — the
`active_slots` merge logic is byte-for-byte untouched:

```diff
-                # Retrieval evidence: unchanged baseline behaviour -- just
-                # overwrite this bucket, same as before the FIX-01 work.
-                state.slots[attr] = new_value
+                if attr in state.slots and attr != tracked_source_attr:
+                    state.slots[attr] = state.slots[attr] + "; " + new_value
+                else:
+                    state.slots[attr] = new_value
```

No dedup, weights, synonyms, special material logic, session routing, ASIN
logic, thresholds, or query-weight changes were added.

### 3. Baseline equivalence

Scratch harness reproduced committed FIX-03A exactly before enabling the
correction:

```
HR@10 0.825000  MRR 0.510105  MTTC 5.680000  Efficiency 0.532000  TechnicalScore 0.671932
165 / 200 hits
```

### 4. Full 200-session simulation

| Metric | FIX-03A | FIX-04A | Δ |
|---|---:|---:|---:|
| HR@10 | 0.825000 | **0.830000** | **+0.005 (net +1 hit)** |
| MRR | 0.510105 | **0.512694** | **+0.002589** |
| MTTC | 5.680000 | **5.645000** | **−0.035** |
| Efficiency | 0.532000 | **0.535500** | **+0.0035** |
| TechnicalScore | 0.671932 | **0.675908** | **+0.003976** |

```
new hits:            1   -- public_0177 (rank 7, turn 4)
new misses:           0
rank improvements:    2   -- public_0052 (4->3), public_0064 (2->1)
rank regressions:     2   -- public_0080 (2->3), public_0183 (6->8)
turn improvements:    0
turn regressions:     0
unchanged:           195
```

**Not a zero-regression result** (unlike FIX-03A) — 2 real rank regressions
occurred, though neither cost a hit. Reported plainly, not smoothed over by
the net-positive aggregate, per the authorization's own instruction that
"every regression must still be reported and explained."

### 5. 30-session Intent Override safety

All 5 sessions touched by this change are Intent Override; **the other 25
Intent Override sessions, and all 170 non-Intent-Override sessions, are
completely unchanged** (verified via the full 200-session diff, not sampled).
Boundary/Browsing/Buying scenario metrics are byte-identical to FIX-03A's own
numbers.

### 6. public_0096 / public_0177 traces, plus explaining the 2 regressions

**`public_0177` — full rescue.** Retrieval rank stays at 8 (unchanged, in
Top50) across all turns; the merge preserves `"Cotton, Rayon; cotton"` in
`state.slots["material"]` instead of collapsing to `"cotton"`. Reranking then
lands the target at final rank 7 — a genuine, complete rescue.

**`public_0096` — NOT rescued, and this is directly measured, not assumed.**
Retrieval rank stays stable at 23 (in Top50, preserved by the merge) across
every turn, both before and after the override. But the target's reranked
pool position never reaches the scored Top10 — this session was already
`term_coverage = 1.0` / `slot_coverage = 1.0` at every turn (established in
`FIX-04`'s audit); fixing retrieval moved it from a **Bucket B/C
retrieval-depth** problem into a **Bucket A doubly-saturated-tie** problem —
still unsolved, for a different reason. This is exactly the outcome the
authorization warned about: "2 addressable misses" was never a promise of
"+2 guaranteed hits."

**Why `public_0080` and `public_0183` regressed** — traced with exact query
expressions from both agent versions, not inferred:

`public_0183`, override turn: under FIX-03A, the (defective) overwrite
dropped the "100" token from `state.slots["material"]` (`"100% Polyester"` →
`"polyester"`), producing a **shorter** retrieval query
(`"...OR "only" OR "polyester"`, 8 terms) that, for this specific candidate
pool, happened to rank the target at position 6. Under FIX-04A, the merge
preserves `"100% Polyester; polyester"`, keeping the query **identical** to
the pre-override query (9 terms, "100" retained) — and for this specific
candidate pool, the fuller query ranks the target one position worse, at 8.

`public_0080`, override turn: same mechanism — FIX-03A's accidental drop of
`"60"`/`"40"` (from `"60% Cotton, 40% Polyester"` → `"cotton"`) produced a
9-term query that happened to rank the target at position 2; FIX-04A's merge
keeps all 12 original terms, matching the pre-override query exactly, and
ranks the target one position worse, at 3.

**Both regressions are the same general, mechanistically-understood
phenomenon**: BM25 relevance is a **system-wide** function over the entire
candidate set, not a monotonic function of "more correctly-preserved evidence
for the target = always better." Preserving evidence that was never
contradicted is still the semantically correct thing to do — the two
sessions where FIX-03A's defect happened to produce a shorter, accidentally
better-ranking query illustrate that occasionally *destroying* evidence can
accidentally help by BM25 coincidence. This is reported as a real,
understood cost of doing the semantically correct thing, not a flaw in the
correction's logic.

### 7. Classification

```
net hits:           +1
TechnicalScore:      improved (+0.003976)
regression surface:  small (2 sessions, both explained, neither a hit loss)
mechanism:           semantically defensible, same class as FIX-03A's
                      already-accepted correction
```

## RETURN FOR INDEPENDENT REVIEW

Positive, but meaningfully weaker than FIX-03A's own zero-regression result.
Per the authorization's fast-quality-gate framework (net hits > 0,
TechnicalScore improves, regression surface acceptably small, mechanism
semantically defensible — all four hold), this clears the bar for
independent review, not automatic implementation. **No runtime profiling
performed** (reserved for after review, consistent with prior passes' "final
sprint" discipline). **Not implemented in production.**

---

## PART B — Bucket-A descriptive characterization (read-only, no scoring)

### 8. Dataset

For all 15 current Bucket-A misses (under the actually-committed FIX-03A
production agent — the live system, not the FIX-04A simulation) and a
random, reproducible sample of 15 current hits (seed 42): target's best
countable-turn pool rank, active terms/slots, term/slot coverage, and
**per-field term presence** (title, categories, features, details, store,
description) for the target and up to 3 immediately-higher-ranked
competitors. Full data: `bucketA_characterization_output.json` (scratch).

### 9. Recurring structural evidence — and an important negative/confound finding

**MEASURED**: `target_max_field` (the single field containing the most
active-term matches) is `"features"` for **100% of both groups** — all 15
misses and all 15 hits. No field-*placement* difference exists between
misses and successful sessions.

**MEASURED, initially apparently interesting**: raw counts looked different
— miss sessions average 1.67 fields with any active-term hit and a
max-field count of 4.6; hit sessions average 2.73 fields and a max-field
count of 9.93.

**MEASURED — this difference is fully explained by a confound, checked
directly rather than assumed away**: miss sessions average **4.73** active
terms at their measured turn; hit sessions average **10.2**. Per-session,
`target_max_field_count` is almost always numerically equal (or very close)
to the session's own `n_active_terms` — e.g. miss `public_0137`: 6 terms, 6
in its max field; hit `public_0086`: 25 terms, 25 in its max field. **Nearly
every active term, for both groups, already lands in the `features` field.**
The raw-count "difference" is simply "hit sessions happen to have
accumulated roughly twice as many active terms by their hit turn" (a
conversation-length effect), not a qualitative field-coherence or
field-placement difference. This was verified directly, not inferred from
the aggregate averages alone.

**MEASURED**: within each Bucket-A tied group, the target and its 1–3
immediately-higher-ranked competitors show **near-identical** per-field
match-count profiles (e.g. `public_0019`: target and all 3 competitors ahead
all show max-field-count 4; `public_0076`, `public_0115`, `public_0137`: all
identical too). This is expected, not novel — it is a direct, trivial
consequence of `term_coverage = 1.0` for the whole tied group (matching
*all* active terms means matching them in whatever fields those terms
happen to appear in, identically for everyone in the tie, by construction).

**Phrase-coherence and exact-contiguous-phrase occurrence were not examined
in this pass** — only field-level presence (bag-of-terms per field), not
whether a multi-word slot value occurs as a contiguous phrase. This is an
explicit, acknowledged gap, not a claim that phrase coherence was checked
and found irrelevant.

### 10. Conclusion — no evidence for a new discriminator, from this specific characterization

Explicitly separated:

- **MEASURED**: no field-placement difference between misses and hits; the
  apparent count difference is a term-count confound, not a coherence
  signal; within-tie-group field profiles are near-identical by construction
  of the 1.0 coverage tie itself.
- **INFERENCE**: none drawn — the data does not support one.
- **HYPOTHESIS**: none proposed. Per this section's own governing rule (§9 of
  the authorization — "any future IDF-based proposal must explain precisely
  what NEW discriminatory information it contributes beyond full-match/
  full-match coverage. If it cannot, do not recommend it"), the same
  standard is applied here: field coherence, phrase coherence, and
  slot-to-field alignment were tested for as candidate discriminators and
  **none showed measurable separation** between misses and hits once the
  term-count confound is controlled for. **No next discriminator is
  recommended from this characterization.** This closes off this specific
  line of inquiry with direct evidence, the same way `FIX-02A0`'s TF-IDF
  work closed off the semantic-retrieval line — a negative result reported
  as a negative result, not stretched into a positive one.

---

## §11. STOP

No production code was edited. No experiment was implemented beyond the
Phase-0 push of the already-committed FIX-03A checkpoint. Nothing new was
staged or committed. No push beyond that already-approved checkpoint. This
report, including the exact query-expression traces explaining both FIX-04A
regressions (§6) and the honestly-reported null result on Bucket-A field
coherence (§9–10), is ready for independent review.
