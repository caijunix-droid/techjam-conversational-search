# Candidate Recall Audit — B0 Production Baseline

Produced per `FIX-01B1 — FINAL PRIVATE-GENERATION AUDIT REVIEW.md` §9 directive. Scope:
preserve the uncommitted FIX-01B1 experiment, restore `starter/agent.py` to the committed
B0 baseline, and measure how deep the target sits in baseline BM25 order for the 54
current misses — **no retrieval fix implemented, no B1 modification, nothing committed.**

---

## A. FIX-01B1 evidence preservation (before restoring)

```bash
git diff -- starter/agent.py > markdowns/patches/fix01b1_active_intent_ranking.patch
shasum -a 256 starter/agent.py
  # a8ed56bd218682807192035c3178e217f05f7851d2164fccba69c064b2f02231   (B1 patch applied)
shasum -a 256 markdowns/patches/fix01b1_active_intent_ranking.patch
  # 73a018d2db22c3baf1b54eb439e4e560dc8191baf08c4cd9cbb70f68681f70c7
```

Patch is 54 lines (diff header + hunks), captured before any restoration. Preserved
alongside it, all still on disk, untouched:

```
tests/test_fix01b1_active_intent_ranking.py           (later relocated -- see §C)
markdowns/fix01b1_active_intent_ranking_handover.md
markdowns/fix01b1_safety_boundary_verification.md
markdowns/fix01b1_private_generation_evidence_audit.md
```

**Naming note**: the directive's §A referred to
`markdowns/fix01b1_private_session_generation_evidence_audit.md`. The file that actually
exists on disk from that earlier step is named
`markdowns/fix01b1_private_generation_evidence_audit.md` (no `_session_`). Flagging this
verbatim rather than silently treating the names as equivalent or renaming the file —
the content itself is unaffected, this is a filename discrepancy in the directive's
prose only, confirmed by direct `ls`.

---

## B. B0 production restoration

```bash
git restore starter/agent.py
git rev-parse HEAD
  # 500fe7bc6fdf0709bf92d2f32deea1a7e5e5e647
shasum -a 256 starter/agent.py
  # 0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354
```

Both match the accepted B0 values recorded in every prior FIX-01B1 handover. `git diff
--stat -- starter/agent.py` now produces no output — the working-tree file is byte-
identical to the committed `500fe7b` blob. No commit was made; this is a working-tree
restore only, and HEAD has not moved.

---

## C. Historical B1 test relocation

`tests/test_fix01b1_active_intent_ranking.py` was re-run against the restored B0 code
before touching it, to confirm the failure mode is exactly "B1 method no longer exists,"
not something else:

```
test_a_cross_bucket_override_only_new_active_term_boosted ... ERROR
  AttributeError: 'Agent' object has no attribute '_active_expression'
test_b_same_bucket_override_only_new_value_boosted ... ERROR
  AttributeError: 'Agent' object has no attribute '_active_expression'
test_c_normal_buying_no_corruption ... ok
test_d_normal_browsing_no_corruption ... ok
test_e_boundary_no_corruption ... ok
test_f_no_active_constraint_falls_back_to_baseline_order ... ERROR
  AttributeError: 'Agent' object has no attribute '_active_expression'
Ran 6 tests in 0.012s — FAILED (errors=3)
```

All three failures are the same `AttributeError` on `_active_expression`, the method
that only exists in the uncommitted B1 patch — confirming the failure is solely because
B1 has been restored out of production, exactly the condition the directive named. (The
other three tests pass by coincidence: they only assert candidate-set/output equality
between the patched and baseline agents, which now trivially holds since both are the
same B0 code.)

Relocated byte-for-byte, not rewritten:

```bash
shasum -a 256 tests/test_fix01b1_active_intent_ranking.py
  # 82aaa49b9d7d866ed5324b67528ecb11fbe6300f7999a9ef023a500ffb14fa7c
cp tests/test_fix01b1_active_intent_ranking.py markdowns/historical_tests/test_fix01b1_active_intent_ranking.py
shasum -a 256 markdowns/historical_tests/test_fix01b1_active_intent_ranking.py
  # 82aaa49b9d7d866ed5324b67528ecb11fbe6300f7999a9ef023a500ffb14fa7c   (identical)
rm tests/test_fix01b1_active_intent_ranking.py
```

Pre/post SHA identical, confirmed by direct `diff` as well as the hash match above. The
file now lives at `markdowns/historical_tests/test_fix01b1_active_intent_ranking.py`,
alongside the existing `test_intent_override_fix01.py` archived during FIX-01B0, out of
active `tests/` discovery.

---

## D. B0 baseline reconfirmation

```bash
python3 -m unittest discover -s tests -p 'test*.py'
# Ran 13 tests in 0.015s — OK
python3 -m evaluator.local_evaluator
```

```
HR@10          0.730000
MRR            0.465458
MTTC           6.345000
Efficiency     0.465500
TechnicalScore 0.597737
```

Matches the required benchmark exactly. Proceeding to the recall audit.

---

## E. Candidate-recall audit methodology

`starter/agent.py` was **not modified**. The probe used only the public `Agent.respond()`
interface, calling it with `top_k=500` instead of the official `10` — a legitimate
parameter of the shipped `respond(self, session_id, user_message, turn, top_k)` signature
(the `LIMIT ?` in the committed SQL is bound directly to `top_k`), used here purely as an
external measurement tool. This does not touch `_build_query()`, the FTS index, or the
`ORDER BY bm25(...)` clause — it only asks the same deterministic, unmodified query for
more rows of an already-ordered result. Verified this doesn't change the real 10-item
result: since BM25 ordering is deterministic and `LIMIT` only truncates a longer prefix
of the same ordered stream, the first 10 entries of a `top_k=500` call are identical to
what a `top_k=10` call would return — confirmed empirically by the exact HR@10
reproduction below (§ sanity check). Dialogue flow (`ask_attribute`, `asked`,
`exhausted`) is unaffected by `top_k` in the committed code, so replaying the real 200
conversations once with `top_k=500` reproduces the official evaluator's turn-by-turn
behavior exactly while additionally exposing deeper ranks for inspection.

**Eligibility correction (found and corrected during this audit, not in the original
directive)**: the competition spec's Session Protocol states *"An Intent Override session
cannot convert before the new intent is sent"* — the official evaluator enforces this via
its `override_applied` flag, which starts `False` for Intent Override sessions and only
flips `True` once the override turn (3 or 4) is reached; a hit before that point is never
credited. An initial pass computed each session's best rank across **all** 10 turns
regardless of this flag, and for Intent Override sessions that produced misleading
results: several sessions showed an excellent "best rank" (e.g. rank 1) that occurred
before the override — a turn that could never have counted as a hit even at rank 1, per
spec, because the old, pre-override query naturally favors a target whose disclosed
attributes were literally sourced from it. Recomputed restricting each session's "best
rank" to only override-eligible turns (mirroring the official evaluator's own gating
exactly). This changed the classification bucket for **6 of the 11** Intent Override
misses (`public_0038`, `0052`, `0064`, `0071`, `0096`, `0177`) — in every case, the
corrected bucket is *worse* (deeper) than the naive one, because the naive version was
crediting a rank that was never actually reachable as a hit. **All numbers below use the
corrected, eligibility-gated methodology.**

```
sanity check: found_le_10 (audit) = 146  ==  HR@10 * 200 = 0.73 * 200 = 146   ✓ match
```

---

## F. All 200 sessions — target-rank bucket distribution

| Bucket | Count |
|---|---|
| Found ≤10 (= official hits) | 146 |
| Found 11–20 | 18 |
| Found 21–50 | 16 |
| Found 51–100 | 13 |
| Found 101–500 | 6 |
| Not found ≤500 | 1 |
| **Total** | **200** |

---

## G. The 54 misses — depth distribution

| Bucket | Count | % of 54 misses |
|---|---|---|
| Found 11–20 | 18 | 33.3% |
| Found 21–50 | 16 | 29.6% |
| Found 51–100 | 13 | 24.1% |
| Found 101–500 | 6 | 11.1% |
| Not found ≤500 | 1 | 1.9% |

**39/54 (72.2%) of misses have the target within rank 50** under the exact same
unmodified BM25 query already in production — i.e., the target is not far from the
top-10 cutoff for most misses. Only 7/54 (13.0%) are deep (101–500 or entirely absent
from the top 500).

### Scenario breakdown (misses / total per scenario)

| Scenario | Misses / Total |
|---|---|
| Boundary | 3 / 10 |
| Browsing | 23 / 80 |
| Buying | 17 / 80 |
| Intent Override | 11 / 30 |

### Scenario × bucket (corrected, eligibility-gated)

| Scenario | 11–20 | 21–50 | 51–100 | 101–500 | Not found ≤500 |
|---|---|---|---|---|---|
| Boundary | 2 | 0 | 1 | 0 | 0 |
| Browsing | 8 | 10 | 3 | 1 | 1 |
| Buying | 6 | 3 | 6 | 2 | 0 |
| Intent Override | 2 | 3 | 3 | 3 | 0 |

Browsing carries the largest share of misses (23/54, 42.6%) and the largest share of
21–50-bucket misses (10/16) — consistent with Browsing's vaguer opening query giving
BM25 less to work with. Intent Override, after the eligibility correction, has the
highest proportion of its misses landing in the deep 101–500 bucket (3/11, 27.3%,
vs. ~11% overall) — plausibly related to the query-composition effect already documented
in `MASTER_HANDOVER.md` §3.3/§5 item 2 (old+new override terms compete in the same
`_build_query()` OR-expression), though this audit did not test that causally and this
is flagged as an unverified plausible explanation, not a finding.

### Turn producing the best (eligible) rank, across the 54 misses

| Turn | Count |
|---|---|
| 2 | 3 |
| 3 | 4 |
| 4 | 7 |
| 7 | 2 |
| 8 | 16 |
| 9 | 14 |
| 10 | 7 |
| (never found ≤500) | 1 |

Turns 8–10 account for 37/54 (68.5%) of best-rank occurrences — i.e., for most misses,
the target's best position is reached only after most or all clarification turns have
accumulated evidence into `_build_query()`, not early in the conversation. This is
consistent with the retrieval query improving as more slots fill in, but the improvement
still isn't enough to cross the top-10 line for these sessions within 10 turns.

### Full miss-level detail (54 rows)

| sample_id | scenario | bucket | best eligible rank | best eligible turn |
|---|---|---|---|---|
| public_0020 | buying | found_101_500 | 278 | 9 |
| public_0038 | intent_override | found_101_500 | 142 | 4 |
| public_0096 | intent_override | found_101_500 | 199 | 3 |
| public_0109 | buying | found_101_500 | 415 | 9 |
| public_0175 | browsing | found_101_500 | 130 | 8 |
| public_0177 | intent_override | found_101_500 | 156 | 4 |
| public_0011 | browsing | found_11_20 | 20 | 2 |
| public_0017 | buying | found_11_20 | 16 | 9 |
| public_0035 | boundary | found_11_20 | 14 | 10 |
| public_0041 | boundary | found_11_20 | 14 | 10 |
| public_0055 | browsing | found_11_20 | 15 | 10 |
| public_0057 | browsing | found_11_20 | 20 | 10 |
| public_0076 | browsing | found_11_20 | 17 | 2 |
| public_0078 | intent_override | found_11_20 | 19 | 3 |
| public_0081 | browsing | found_11_20 | 15 | 8 |
| public_0095 | buying | found_11_20 | 15 | 9 |
| public_0097 | buying | found_11_20 | 17 | 9 |
| public_0115 | browsing | found_11_20 | 18 | 8 |
| public_0120 | browsing | found_11_20 | 17 | 8 |
| public_0159 | buying | found_11_20 | 15 | 9 |
| public_0170 | browsing | found_11_20 | 17 | 8 |
| public_0171 | buying | found_11_20 | 17 | 9 |
| public_0178 | buying | found_11_20 | 15 | 9 |
| public_0183 | intent_override | found_11_20 | 15 | 4 |
| public_0012 | browsing | found_21_50 | 21 | 8 |
| public_0015 | browsing | found_21_50 | 26 | 8 |
| public_0016 | browsing | found_21_50 | 31 | 10 |
| public_0019 | browsing | found_21_50 | 23 | 8 |
| public_0040 | browsing | found_21_50 | 25 | 8 |
| public_0052 | intent_override | found_21_50 | 40 | 3 |
| public_0054 | buying | found_21_50 | 38 | 9 |
| public_0058 | buying | found_21_50 | 25 | 7 |
| public_0064 | intent_override | found_21_50 | 22 | 4 |
| public_0071 | intent_override | found_21_50 | 44 | 4 |
| public_0127 | browsing | found_21_50 | 31 | 8 |
| public_0137 | browsing | found_21_50 | 27 | 8 |
| public_0149 | buying | found_21_50 | 44 | 2 |
| public_0151 | browsing | found_21_50 | 31 | 10 |
| public_0172 | browsing | found_21_50 | 35 | 8 |
| public_0184 | browsing | found_21_50 | 23 | 8 |
| public_0002 | intent_override | found_51_100 | 78 | 3 |
| public_0028 | buying | found_51_100 | 92 | 9 |
| public_0083 | buying | found_51_100 | 73 | 9 |
| public_0087 | browsing | found_51_100 | 98 | 8 |
| public_0092 | browsing | found_51_100 | 87 | 8 |
| public_0126 | browsing | found_51_100 | 51 | 8 |
| public_0144 | intent_override | found_51_100 | 98 | 4 |
| public_0161 | buying | found_51_100 | 56 | 9 |
| public_0174 | buying | found_51_100 | 87 | 9 |
| public_0179 | buying | found_51_100 | 51 | 7 |
| public_0187 | boundary | found_51_100 | 63 | 10 |
| public_0194 | buying | found_51_100 | 66 | 9 |
| public_0198 | intent_override | found_51_100 | 92 | 4 |
| public_0073 | browsing | not_found_le_500 | — | — |

`public_0073` (Browsing) is the sole session whose target never appears anywhere in the
top 500 at any turn — the only case in the entire 200-session public set where the
current lexical query has essentially zero retrieval signal for the target, as opposed
to merely ranking it low.

---

## H. Retrieval-ceiling interpretation (measurement only — no fix implemented)

Per the directive's own interpretation guide:

```
many misses at 11-20   -> candidate-pool enlargement / reranking may be enough
many misses at 21-100   -> broader lexical retrieval + reranking may help
many misses very deep/absent -> lexical BM25 itself is the bottleneck
```

Measured distribution: 18 misses at 11–20, 16 at 21–50, 13 at 51–100 (47/54, 87.0%, at
≤100), and only 7/54 (13.0%) at 101–500 or absent. Under the directive's own stated
interpretation guide, this pattern — the large majority of misses clustered close to the
existing cutoff, few very deep or absent — points toward the first two bands rather than
the third: most misses are not evidence that lexical BM25 has fundamentally no signal for
the target, but that the top-10 cutoff combined with the current candidate pool size is
the binding constraint for most of them. This is stated as a direct reading of the
measured distribution against the directive's own interpretation guide, not as a
recommendation — no retrieval change was implemented or benchmarked in this pass, and
this document does not propose or evaluate any specific fix.

---

## I. Git status

```
 (no modification to any tracked file — starter/agent.py restored to HEAD byte-for-byte)
?? markdowns/candidate_recall_audit_b0.md
?? markdowns/historical_tests/test_fix01b1_active_intent_ranking.py
?? markdowns/patches/fix01b1_active_intent_ranking.patch
(plus the pre-existing untracked markdowns/ files from prior FIX-01/FIX-01B0/FIX-01B1
 work, unrelated to this audit)
```

`tests/test_fix01b1_active_intent_ranking.py` no longer exists at its old path (moved,
not deleted — preserved at `markdowns/historical_tests/`, byte-identical, §C). HEAD
remains at `500fe7b`. No `git add`, `git commit`, or `git push` was run at any point in
this pass.

---

## J. Confirmation

```
NO PRODUCTION EDIT.   -- starter/agent.py is byte-identical to committed 500fe7b.
NO COMMIT.            -- nothing staged or committed; HEAD unchanged.
NO RETRIEVAL FIX.     -- this document measures only; no query/candidate-pool/embedding
                          change was implemented or evaluated.
NO B1 MODIFICATION.   -- the preserved patch (§A) is untouched; B1 was not re-applied,
                          re-tuned, or altered during this pass.
```

Findings for the next decision: candidate recall (not just reranking) appears to be a
real, measurable constraint for the 54 current misses, with most misses (39/54, 72.2%)
sitting within rank 50 of the unmodified baseline query — a `starter/agent.py`-untouched
measurement, not a proposal. Per the directive, no fix is proposed or attempted here.
Stopping for the next directive.
