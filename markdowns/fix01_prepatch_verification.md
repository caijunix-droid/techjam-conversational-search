# FIX-01 Intent Override — Pre-Patch Reproduction (governance §0–§2)

Status: **pre-patch only**. No files under `starter/`, `evaluator/`, `demo/`, `docs/`, or
`data/` were edited to produce this document. This satisfies directive
`TECHJAM_FIX01_INTENT_OVERRIDE_DIRECTIVE.md` §0–§2 (inspect, hash, reproduce baseline,
independently reproduce the claimed defect) before any implementation begins.

---

## ⚠️ Governance flag: repository state differs from the directive's assumed baseline

The directive quotes a previously-verified baseline and explicitly warns "DO NOT trust
these numbers." That warning was warranted — **the repo advanced since that verification
was written**:

```
c6461c4  added markdowns for Claude                                  (adds markdowns/ — matches prior session's output)
068e8fa  Fix budget parsing and vague-answer handling in agent.       <-- NEW, modifies starter/agent.py
9b5fc2f  Add improved shopping agent with dialog memory + live demo script   (commit the prior verification was run against)
```

`068e8fa` is **not** the commit the directive's quoted baseline was verified against. Per
governance rule ("if repository state materially differs from the handover, STOP and
report it rather than adapting silently"), this was re-verified rather than assumed to
still hold — see §1 below.

**What changed in `068e8fa`** (diffed directly, not assumed):
- Expanded `BUDGET_RE` to catch more phrasings ("around 150", "X dollars").
- Expanded `NO_PREFERENCE_PHRASES` ("nope", "meh", "flexible", etc.).
- Added an unused `known_slot_count()` display helper (not called by the scored evaluator).
- Cosmetic change to `demo/interactive.py`'s print limit.
- **Does not touch intent-override logic at all** — no lines in the override code path
  changed.
- Contains a code comment documenting a *second* reverted experiment (excluding numeric
  tokens from search dropped hit rate 0.73 → 0.675) — unlike the three experiments named
  in the original `HANDOVER.md`, this one has an actual code comment as evidence, though
  still no separate commit for the reverted attempt itself.

---

## 0. Repository state

```
Branch:  main
Commit:  c6461c488a7b0cfb6ac16fa91697d986e31747cd
Status:  clean, up to date with origin/main
```

SHA256 — file that may be changed under FIX-01:
```
03d4ecfcc0fdc0337c8d04465105b580c363b8591d797f1905276391fd4ed371  starter/agent.py
```

SHA256 — control set, must not change during FIX-01:
```
79a5ea06f9a1b8c5036f30efa85dc1f36b8f6b06eb8feb8f545dfa767bc45564  evaluator/local_evaluator.py
cd0fdade2d743aaf220b93a6cd3bfa7fb1b9b9065d2fbd174128ed2b0f1b812d  starter/agent_baseline.py
408e264acbd1e4567b98038d448fd23c9e9b51705149ca7da1bcd1571e10d001  docs/competition_specification.md
8ee0c899ddc68d521754cf9d2f239a8bc09851fb37c5872567160c30d431aa53  docs/evaluation_config.json
857259f7a438e6188ac63e18995b6ff4489bfcfc4a716a798b9a2aa0ee8f7579  data/public_set.jsonl
```

`grep -n "price" starter/agent.py` → zero matches (re-confirmed unchanged from prior
session's §2.2 finding). FTS5 schema still carries no `price` column.

---

## 1. Independent pre-patch reproduction of the current baseline

Commands run:
```bash
python3 -m evaluator.local_evaluator   # run twice, independent processes
python3 -m unittest tests.test_evaluator
```

| Metric | Run 1 | Run 2 |
|---|---:|---:|
| Hit Rate@10 | 0.73 | 0.73 |
| MRR | 0.465458 | 0.465458 |
| MTTC | 6.345 | 6.345 |
| Efficiency | 0.4655 | 0.4655 |
| TechnicalScore | 0.597737 | 0.597737 |

Byte-identical between runs (session UUIDs excluded from the diff). Unit tests: 3/3 pass.

**Result**: current `HEAD`'s aggregate metrics are unchanged from the previously-verified
numbers, even though `agent.py` itself changed in `068e8fa` — that commit is metric-neutral
on this scripted benchmark (the scripted customer never uses the new phrasings it added;
those target the live human demo, not the evaluator). The directive's quoted baseline
table is confirmed accurate on current `HEAD`, but only by re-running it, not by trusting
the document.

Scenario breakdown (unchanged from prior session):

```
Buying:           0.7875
Browsing:         0.7125
Intent Override:  0.6333   <- lowest
Boundary:         0.7000
```

---

## 2. Independent reproduction of the stale-state hypothesis

Ran [`probes/probe_override_batch.py`](probes/probe_override_batch.py) fresh against
current `HEAD`, using the evaluator's own `materialize_hidden_fields` /
`initial_message` / `customer_reply` (no synthetic data, no shortcuts, no use of
`ground_truth`/`intent_card` inside the Agent itself — those are read only by the probe,
external to the Agent).

**Result — confirmed, unchanged from prior session:**
- 30/30 real Intent Override sessions checked.
- 24/30 (80%) have `old_value` and `new_value` classifying into *different* attribute
  buckets.
- 24/24 (100%) of those retain the stale old value in `state.slots` after the override
  message is processed.

Representative example:
```
public_0002: old='Buckle closure' (bucket=feature)
             new='leather'         (bucket=material)
             slots after override: {'feature': 'Buckle closure', 'material': 'leather'}
             -> STALE PERSISTS
```

Full per-session table (sample_id / old_value / old bucket / new_value / new bucket /
slots after override) is reproducible verbatim by running the probe script above; all 30
sessions were checked, not a sample.

**Code path confirmed** in `starter/agent.py`'s override handler: sets
`state.slots[classify(new_value)] = new_value` and returns — never inspects or clears
whatever bucket the *old* value occupied. This matches the directive's hypothesis exactly,
with no discrepancy found.

---

## Summary — governance checklist before implementation

| Check | Result |
|---|---|
| Repo state matches directive's assumptions | **No** — flagged above; re-verified rather than assumed; no impact on conclusions |
| Baseline reproduced | ✅ 0.73 / 0.465458 / 6.345 / 0.597737, deterministic across 2 runs |
| Unit tests pass | ✅ 3/3 |
| Stale-state hypothesis independently reproduced | ✅ 24/30 sessions affected, 24/24 confirmed stale |
| Control-set files hashed pre-patch | ✅ recorded above |
| Any code edited to produce this document | ❌ none |

All pre-conditions in directive §0–§2 are satisfied. Implementation (§3 onward:
provenance-aware patch, targeted tests, 30-session backtest, full 200-session A/B,
session-level deltas) has **not** started and awaits go-ahead.
