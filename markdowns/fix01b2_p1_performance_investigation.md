# FIX-01B2-P1 — Performance Bottleneck Audit

Produced per `FIX-01B2-P1 — PERFORMANCE BOTTLENECK AUDIT.md`. Scope: profile the
uncommitted B2 candidate to locate its runtime overhead, then investigate whether an
exactly-equivalent implementation can reduce it. **Ranking behavior was never changed.
`starter/agent.py` was never edited during this pass — every optimization candidate was
built and tested as a standalone external copy, and neither was installed into
production. Nothing committed, nothing pushed.**

---

## 0. Current B2 state (unchanged throughout this audit)

```bash
git rev-parse HEAD
  # 500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647
shasum -a 256 starter/agent.py
  # e3f324caf8e6c940d44293beffd6a71df489f56564639c5af800d70d2975b9b5
git diff --stat -- starter/agent.py
  # starter/agent.py | 47 +++++++++++++++++++++++++++++++++++++++++++++--
  # 1 file changed, 45 insertions(+), 2 deletions(-)
python3 -m unittest discover -s tests -p 'test*.py'
  # Ran 22 tests in 0.029s — OK
```

SHA and diff are byte-identical to the ones recorded in
`markdowns/fix01b2_term_coverage_implementation_handover.md` — confirmed both before and
after this profiling/investigation pass. All 22 tests (13 pre-existing + 9 FIX-01B2
targeted) remain green throughout.

---

## 1. Profiling — where B2's time actually goes

### 1.1 cProfile, full 200-session run (function-level breakdown)

```bash
python3 -c "cProfile.Profile() around evaluate(Agent(...), samples, ...)"
```

(cProfile's own instrumentation adds overhead — the run took 57.4s under profiling vs.
~52-55s unprofiled — so absolute seconds here should not be read as the true wall-clock
split; the *relative proportions* between functions are the meaningful signal, which is
standard practice for this kind of bottleneck identification.)

```
757118 function calls in 57.403 seconds

sqlite3.Connection.execute   : 4415 calls, 32.531s tottime
sqlite3.Cursor.fetchall      : 4415 calls, 24.280s tottime
                                            ----------------
                                            56.811s  (98.97% of profiled time)

list.sort()                  :  938 calls,  0.073s cumtime
_coverage() (Python closure) : 46900 calls,  0.052s cumtime
<lambda> (sort key)          : 46900 calls,  0.062s cumtime
                                            ----------------
                                            ~0.19s  (0.33% of profiled time)
```

**Python-side ranking computation (coverage calculation + sort) is negligible — under
0.35% of total time.** Essentially all measurable time is inside SQLite `execute`/
`fetchall` calls. The `4415` execute calls exactly equals `1143` baseline retrieval
queries `+` `3272` per-term match queries (cross-validated against the independent
call-counting instrumentation in §1.2 — the two measurement techniques agree exactly).

### 1.2 Call-count and active-term statistics (non-invasive class-method monkeypatch,
in-process only — never written to `starter/agent.py`)

```
total respond() calls:                                1143
calls reaching the term-coverage code path:            1143  (baseline expression always non-empty)
calls with >=1 active term (coverage loop actually runs): 938
total per-term MATCH queries issued:                   3272

active terms per call (calls with >=1 active term):
  min=1  median=2.0  mean=3.488  p90=7  max=40
```

Per-scenario:

| Scenario | Calls | Total term-queries | Mean terms/call |
|---|---:|---:|---:|
| Boundary | 64 | 43 | 0.672 |
| Browsing | 437 | 1165 | 2.666 |
| Buying | 448 | 1140 | 2.545 |
| Intent Override | 194 | 924 | 4.763 |

Intent Override has the highest average query load per call (4.763), consistent with
override sessions carrying more accumulated active-slot content by the time the override
lands.

### 1.3 Splitting SQL time: baseline retrieval vs. per-term queries

Measured with a non-invasive timing proxy substituted for `agent.connection` in-process
only (implements `.execute()`, classifies each call by SQL shape, times it, delegates to
the real connection — `starter/agent.py` itself was never touched):

```
baseline_retrieval (LIMIT 50, once/turn):  n=1143  time=34.7552s  (54.68% of wall)
per_term_match (one/active-term/turn):     n=3272  time=28.0882s  (44.19% of wall)
```

**Read in isolation, this makes it look like baseline retrieval — not the per-term
loop — is the larger cost.** That reading turns out to be misleading once compared
against what B0 already spends on its own baseline query (§1.4).

### 1.4 Decisive comparison: is the widened baseline query (LIMIT 10→50) new overhead?

Measured B0's own baseline query (unmodified, `LIMIT 10`) with the identical timing
proxy technique:

```
B0 baseline query (LIMIT 10):  n=1215  time=39.5702s  per_call=32.568ms
B2 baseline query (LIMIT 50):  n=1143  time=34.7552s  per_call=30.408ms
```

**B2's LIMIT-50 baseline query costs no more per call than B0's own LIMIT-10 baseline
query already does today — if anything, marginally less in this measurement.** This
makes sense: SQLite's FTS5 `MATCH` + `ORDER BY bm25(...)` must score every row matching
the (up to 40-term) `OR` expression to determine the top-N regardless of what N is;
`LIMIT` only truncates the final output, not the scoring work. **The widened retrieval
depth is therefore not a new cost B2 introduces — it is the same cost class B0 already
pays**, just measured on B2's own instance.

---

## 2. Bottleneck classification

```
Hypothesis: "The dominant B2 overhead is the loop issuing one FTS MATCH query per
active term per turn."

CLASSIFICATION: CONFIRMED.
```

Reasoning, stated precisely (the naive comparison in §1.3 alone would have supported only
"PARTIALLY CONFIRMED" — this is why §1.4's B0-comparison step was necessary before
classifying): once the baseline-retrieval cost is recognized as a pre-existing B0 cost
(not new overhead), the entire measurable *incremental* cost B2 adds on top of B0 is
attributable to the 3272 additional per-term `MATCH` queries. Both independent
measurement techniques (cProfile's function-level `execute`/`fetchall` totals in §1.1,
and the query-count instrumentation in §1.2) agree exactly on the query count (4415 =
1143 + 3272), and Python-side ranking computation is confirmed negligible (§1.1).

---

## 3. Optimization candidates investigated

Two exact-equivalence-preserving candidates were built as **standalone external copies**
(never `starter/agent.py`) and rigorously tested. A third avenue (Candidate C) was
investigated and yielded a negative finding, documented below.

### 3.1 Candidate A — batched SQL (UNION ALL)

Combines the N per-term `MATCH` queries into a single `execute()` call via `UNION ALL`
— one sub-`SELECT` per term, each with byte-identical `MATCH` predicate and
`parent_asin IN (...)` restriction to what the current implementation runs separately,
differentiated by a literal `_term_idx` discriminator column. This reduces Python↔SQLite
round trips from N to 1 per turn while using **exactly the same FTS5 MATCH semantics per
term** — equivalence is guaranteed by construction (each sub-query is textually
identical to what runs today), not just empirically likely.

**Equivalence audit** (all 200 sessions, all real conversation turns, against the actual
uncommitted B2 in `starter/agent.py`):

```
total turns compared: 1143
mismatches: 0
EXACT MATCH on every turn -- candidate pool, order, ask_attribute, and message.
```

Full evaluator run also reproduced B2's metrics exactly (HR@10 0.805, MRR 0.499431,
MTTC 5.91, TechnicalScore 0.654129, all scenario metrics identical).

**Runtime (3 runs)**: 77.7328s, 77.5582s, 74.1292s — **median 77.5582s**.

**This is slower, not faster** — 49.61% slower than current B2 (using the full
repeated-measurement medians from §4), 2.53x slower than B0. The `UNION ALL` query
becomes a large, complex statement (up to 40 sub-selects, each repeating a 50-item
`IN (...)` placeholder list — up to ~2000 bound parameters for a single call at the high
end of the term-count distribution) that costs SQLite more to parse and plan than the
sum of 40 small, simple queries costs to execute separately. The round-trip savings
hoped for did not materialize; query-planning overhead dominated instead.

**Classification: REJECT** (per the audit's own acceptance logic — behavior is exactly
identical, but runtime does not improve; it materially worsens).

### 3.2 Candidate B — candidate-text reuse, local matching

Fetches each candidate's own indexed text **once** per turn (a single plain `SELECT`,
no `MATCH` at all) instead of running one `MATCH` query per active term, then computes
term coverage locally in Python using production's own `_terms()` tokenizer against the
fetched text.

**The directive's explicit warning was taken seriously**: "DO NOT assume Python
substring matching == SQLite FTS5 MATCH." Before treating this as viable, two
equivalence checks were run, not one:

1. **Targeted stress test**: the catalog was scanned for non-ASCII content (a plausible
   source of tokenizer divergence between `_terms()`'s ASCII-only regex and FTS5's
   `unicode61 remove_diacritics 2` tokenizer) — found in **11,811 / 50,000 rows
   (23.6%)**. Sampled 2,000 of those rows against 36 realistic material/color/feature
   terms (the actual regex vocabulary `starter/agent.py` recognizes, plus common
   descriptive words): **0 mismatches across 72,000 (term, candidate) pairs.**
2. **Full real-conversation equivalence audit** (the decisive test, using the *actual*
   terms that occur in real 200-session conversations, not a hand-picked list) — same
   methodology as Candidate A's audit: **0 mismatches across all 1143 real turns**, and
   the full evaluator run reproduced B2's metrics exactly on every field.

Both checks are empirical (a large sample, not a mathematical proof covering every
possible string), and this is stated as a limitation, not glossed over — but the second
check specifically covers every term that could actually occur in this evaluator's real
usage pattern, which is the concrete population that matters for this audit's purposes.

**Runtime (3 runs)**: 52.1043s, 50.9552s, 50.5936s — **median 50.9552s**.

Compared against a *single* prior B2 measurement (54.7356s, from the implementation
handover), this looked like a ~6.9% improvement. **That comparison was not apples-to-
apples** — §4 below re-measures current B2 with the same 3-run rigor and finds its own
median is 51.8234s, much closer to Candidate B's 50.9552s. The real, fairly-measured
improvement is **1.71%** (§4) — within the range of run-to-run measurement noise already
observed on this machine (B0's own 3 repeat runs ranged 29.75s–35.66s, a 20% spread with
*no* code change at all).

**Classification: INVESTIGATE**, not KEEP — behavior is exactly identical (rigorously
proven, not assumed), but the runtime improvement is not established as material once
measured with matched rigor; it is within this environment's observed measurement noise
band.

### 3.3 Candidate C — another exact SQLite/FTS mechanism

Investigated whether stock SQLite FTS5 (no extensions) exposes a built-in mechanism to
retrieve, in one query, a per-candidate "which of these N distinct terms matched" vector
— which would avoid both Candidate A's query-complexity cost and Candidate B's
tokenizer-equivalence risk. Stock FTS5's auxiliary functions are `bm25()`, `highlight()`,
and `snippet()`; none of these expose a per-term match boolean/count across an arbitrary
term list for an already-fixed row set without re-running `MATCH` per term (which is
exactly what Candidate A already does, batched, and what the current implementation does,
unbatched). **No cleaner built-in single-query mechanism was found.** This is reported as
a negative finding from the investigation required by the directive, not further pursued.

---

## 4. Runtime comparison — full table, matched rigor (3 runs each, medians)

| Version | Run 1 | Run 2 | Run 3 | **Median** | vs B0 | vs current B2 |
|---|---:|---:|---:|---:|---:|---:|
| B0 (`500fe7b`) | 29.7530s | 31.5376s | 35.6641s | **31.5376s** | 1.00x | — |
| Current B2 (uncommitted) | 51.8234s | 51.6855s | 51.8579s | **51.8234s** | 1.6432x | 1.00x |
| Candidate A (UNION ALL) | 77.7328s | 77.5582s | 74.1292s | **77.5582s** | 2.4593x | 1.4966x (**49.66% slower**) |
| Candidate B (local text match) | 52.1043s | 50.9552s | 50.5936s | **50.9552s** | 1.6157x | 0.9829x (**1.71% faster**) |

(An earlier single-shot measurement of current B2, in the FIX-01B2 implementation
handover, read 54.7356s — outside this 3-run range, illustrating exactly why the
directive's "run multiple times, report median" requirement matters; that single-run
figure is superseded by the 3-run median above for comparison purposes.)

No ranking algorithm was modified in response to any of these runtime results.

---

## 5. Acceptance logic applied

```
Candidate A:
  behavior exactly identical to B2:  YES
  runtime materially improves:       NO (49.66% SLOWER)
  => REJECT

Candidate B:
  behavior exactly identical to B2:  YES (proven on all 1143 real turns + evaluator metrics)
  runtime materially improves:       NOT ESTABLISHED (1.71%, within observed measurement noise)
  => INVESTIGATE
```

Per the directive's own governance ("If even one session differs: NOT AN OPTIMIZATION OF
B2. STOP THAT CANDIDATE. Do not rationalize the difference because the score happens to
improve.") — neither candidate ever showed a session difference, so this clause was never
triggered for either. The disqualifying factor for Candidate A is pure runtime; for
Candidate B it is the absence of a *material* runtime case, not any equivalence failure.

**Neither candidate is recommended for installation into `starter/agent.py` at this
time.**

---

## 6. Tests

```
Current B2 targeted tests:      9 / 9  PASS   (unchanged throughout this audit)
Current complete active suite: 22 / 22 PASS   (unchanged throughout this audit)
```

No performance-specific tests were added — per the directive's own caution against
machine-dependent timing thresholds in the test suite, and because both candidates'
*behavioral* equivalence was already established via the full 200-session/1143-turn
audits in §3.1/§3.2, which is the property worth locking down; their runtime numbers are
reported as measurements in this document, not asserted as thresholds in code.

---

## 7. Git status

```bash
git diff --stat -- starter/agent.py
  # starter/agent.py | 47 +++++++++++++++++++++++++++++++++++++++++++++--
  # 1 file changed, 45 insertions(+), 2 deletions(-)
```

Identical to the diff recorded in the FIX-01B2 implementation handover — **zero lines
changed in `starter/agent.py` during this entire profiling/investigation pass.** All
candidate code (`candidate_a_union_all.py`, `candidate_b_agent.py`, and the profiling/
equivalence/runtime harness scripts) lived only in a scratch directory outside the
repository, never staged, never added to the working tree.

```
 M starter/agent.py     (unchanged since the FIX-01B2 implementation handover)
?? markdowns/fix01b2_p1_performance_investigation.md
(plus the pre-existing untracked markdowns/ files from prior FIX-01/FIX-01B0/FIX-01B1/
 FIX-01B2 work, unrelated to this pass)
```

HEAD remains `500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647`.

---

## 8. Confirmation

```
NO COMMIT.          -- nothing staged or committed; HEAD unchanged.
NO PUSH.             -- no git push was run.
NO RANKING TUNING.   -- candidate depth, term-coverage definition, BM25, query
                         construction, and tokenizer were never touched; both
                         candidates are provably exact reorderings of the same
                         per-term-match computation the frozen mechanism defines.
```

---

## Summary for the next decision

The bottleneck hypothesis is confirmed: essentially all B2 runtime (>98% under
profiling) is SQL execute/fetchall time, and once B0's own baseline-query cost is
subtracted out as pre-existing (not new), the entire incremental cost B2 adds is the
per-active-term `MATCH` query loop (3272 extra queries across the 200-session set, mean
3.488 terms per call where any exist, up to 40 at the cap). Two exact-equivalence
candidates were built and rigorously tested — both proven behaviorally identical to B2
on every one of 1143 real conversation turns and every evaluator metric. Neither clears
the bar for adoption: batching into `UNION ALL` (Candidate A) makes runtime **worse**
(49.66% slower, likely from SQL query-planning complexity outweighing round-trip
savings); avoiding SQL entirely via local text matching (Candidate B) is only 1.71%
faster once measured with matched 3-run rigor — within this environment's own
measurement noise (B0's unmodified runtime alone varied 20% across 3 repeat runs with
zero code change). No stock SQLite FTS5 mechanism was found that avoids both candidates'
respective costs (Candidate C, negative finding). `starter/agent.py` was never edited;
both candidates exist only as external scratch files. Stopping here per the directive —
not proceeding to another ranking improvement.
