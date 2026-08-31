# TechJam 2026 Track 4 — Conversational Shopping Copilot

> A lightweight, stateful conversational search agent that separates **what the shopper wants now** from **what the conversation has taught the retrieval system**.

## Overview

This repository contains our submission for **TikTok TechJam 2026 — Track 4: Conversational E-Commerce Search**.

The task is to build a multi-turn shopping agent that receives an anonymized user profile and a sequence of customer messages, asks useful clarification questions, and recommends the customer's hidden target product from a frozen catalog of 50,000 products within at most 10 turns.

Our final system is deliberately lightweight and fully deterministic. It uses **Python + SQLite FTS5 + BM25-style lexical retrieval**, combined with conversational state and hierarchical reranking. The scoring path uses **no external LLM, no model API, no network call, and no paid inference**.

### Final public-set result

| Metric | Final result |
|---|---:|
| **HR@10** | **88.0% (176 / 200 sessions)** |
| MRR | 0.567583 |
| MTTC | 5.495 turns |
| Efficiency | 0.550500 |
| **TechnicalScore** | **0.720375** |
| Unit tests | **54 / 54 passing** |

The 88.0% figure is **HR@10 on the organizer's 200-session public development set**, not generic real-world "accuracy" and not a claim about the held-out 800-session private set.

---

## Why This Problem Matters

Product search becomes harder when the user does not express a complete query in one message.

A shopper may start vague, reveal constraints gradually, change their mind, contradict an earlier preference, or care about several attributes at once. A useful conversational search system therefore needs to do more than retrieve products from the latest message: it must maintain state, distinguish current intent from historical context, ask productive follow-up questions, and rank products using all relevant information accumulated over the conversation.

Our main engineering insight came from precisely this problem.

---

## Core Insight — Two Different Kinds of Memory

Early in development, one state structure was effectively serving two roles:

1. **What does the customer currently want?**
2. **What lexical evidence from the conversation is still useful for retrieval?**

Those are not always identical.

We therefore separate them conceptually:

### `active_slots` — current conversational truth

`active_slots` represents the user's **currently active constraints**. It is used for:

- current intent;
- clarification logic;
- active-term coverage;
- active-slot coverage;
- exact-phrase matching.

When a user explicitly overrides a preference, this state must reflect the new intent.

### `slots` — accumulated lexical retrieval evidence

`slots` preserves the conversational evidence used to construct the lexical search query.

This allows the agent to update current intent without unnecessarily destroying useful retrieval evidence that may still help distinguish the correct product.

The separation emerged from measured failure analysis: an earlier attempt to make state semantically cleaner by simply deleting superseded evidence fixed the state representation but reduced benchmark performance. The final design therefore treats **conversation semantics** and **retrieval memory** as related but distinct responsibilities.

---

## How the Agent Works

```text
Customer message
      ↓
Template-aware parsing
      ↓
Conversation state
(active_slots + retrieval evidence)
      ↓
SQLite FTS5 lexical retrieval
      ↓
BM25 Top-50 candidate pool
      ↓
Hierarchical reranking
      │
      ├─ 1. Active-term coverage
      ├─ 2. Active-slot coverage
      ├─ 3. Exact multi-token phrase coherence
      └─ 4. Original BM25 order
      ↓
Top-10 recommendations
      +
next clarification question
```

The ranking hierarchy is strict: a later tier only breaks ties among candidates that are equal on all higher-priority tiers.

### Tier 1 — Active-term coverage

Measures how completely a candidate matches the distinct terms in the shopper's **current active intent**.

This addresses a key observation from the original 73% working milestone: many misses were already inside the BM25 candidate pool, so the dominant opportunity was often **second-stage discrimination**, not simply retrieving more products.

### Tier 2 — Active-slot coverage

Term count alone can over-reward one verbose constraint.

Slot coverage instead asks whether a candidate matches at least one usable term from each active constraint category, giving the ranker more awareness of the structure of the user's request.

### Tier 3 — Exact phrase coherence

Term and slot coverage can both saturate.

For example, two candidates may contain every word in:

> "shaft measures approximately 1 inch from arch"

but one contains the complete sequence while the other has the same words scattered throughout its metadata.

The phrase-coherence tier preserves that contiguous structure across `title`, `features`, `details`, and `description`.

### Tier 4 — Original BM25 order

When all three constraint-aware signals are tied, the original BM25 ranking remains the final deterministic tie-break.

---

## Conversation Behaviour

On each turn the agent can both recommend products and ask one follow-up question.

Supported clarification areas include:

- category;
- material;
- color;
- size;
- style;
- brand;
- budget;
- feature;
- use case.

The parser also handles common conversational forms such as:

- initial shopping requests;
- clarification answers;
- explicit intent overrides;
- "no preference" responses;
- filler or vague replies;
- free-form fallback input for the live demo.

The interactive demo uses the same agent as the evaluator; it is simply an **unscored human-facing interface**.

---

## Performance

Measured using the organizer's **unmodified** `evaluator/local_evaluator.py` on all 200 public sessions:

| Scenario | Sessions | HR@10 | MRR | MTTC |
|---|---:|---:|---:|---:|
| Browsing | 80 | 90.0% | 0.618204 | 5.30 |
| Buying | 80 | 88.75% | 0.495288 | 5.50 |
| Intent Override | 30 | 83.3% | 0.646984 | 5.63 |
| Boundary | 10 | 80.0% | 0.502778 | 6.60 |

### Baselines — important distinction

Three different milestones appear in the project history and should not be conflated:

- **12.5% HR@10** — the organizer's deliberately weak stateless BM25 reference agent in `starter/agent_baseline.py`.
- **73.0% HR@10** — our team's first accepted working multi-turn milestone before the final ranking improvements.
- **88.0% HR@10** — the final verified public-set result.

The documented final optimization cycle progressed:

```text
73.0%
→ 80.5%
→ 81.0%
→ 82.5%
→ 83.0%
→ 88.0%
```

Detailed experiment, simulation, regression, and commit reports are preserved under `markdowns/`.

---

## Evidence-Driven Engineering

We did not accept an idea because it sounded more sophisticated.

The project used an evidence-controlled workflow:

```text
hypothesis
→ simulation / targeted analysis
→ implementation
→ tests
→ full evaluator
→ session-level delta analysis
→ review
→ commit only after acceptance
```

Several ideas were rejected when measured results did not support them.

Examples include:

- deleting stale conversational evidence too aggressively;
- broad active-only BM25 reranking;
- a lightweight TF-IDF semantic-style retrieval experiment;
- simply widening or changing ranking behaviour without evidence of a generalizable failure mode.

The final scoring sprint intentionally ended with **"no safe experiment found"** rather than forcing another public-set optimization after the residual analysis stopped revealing a defensible new signal.

This process is documented in `markdowns/`.

---

## Technical Execution and Reproducibility

### Requirements

- Python 3.10+ recommended
- No third-party Python packages required
- SQLite with FTS5 support
- Local competition catalog at `data/catalog.jsonl`

### Download the catalog

Download `catalog.jsonl.gz` from the repository release, then:

```bash
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
```

Verify it using the published `SHA256SUMS`.

### Run the test suite

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```

Expected final result:

```text
54 tests
54 PASS
0 failures
0 errors
```

### Reproduce the public evaluation

```bash
python3 -m evaluator.local_evaluator
```

Expected aggregate result on the released 200-session public set:

```text
HR@10          0.880000
MRR            0.567583
MTTC           5.495000
Efficiency     0.550500
TechnicalScore 0.720375
```

The evaluator writes session-level and aggregate results to `results.json`.

Do not modify `evaluator/local_evaluator.py` or `data/public_set.jsonl` when reproducing these results.

### Run the live demo

```bash
python3 -m demo.interactive
```

The live demo lets a human enter free-form shopping requests and interact with the same agent used by the evaluator.

It does **not** calculate HR@10 because a free-form human interaction has no benchmark target label.

### Fresh-clone verification

The final committed repository was also reproduced from a fresh local clone:

- 54 / 54 tests passed;
- agent import and FTS index construction succeeded;
- interactive demo imported successfully;
- the full 200-session evaluator reproduced the final metrics above.

---

## Agent Interface

The submission implements the organizer's required API:

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(
        self,
        session_id: str,
        user_message: str,
        turn: int,
        top_k: int,
    ) -> dict:
        return {
            "message": "Do you have a material preference?",
            "ask_attribute": "material",
            "recommendations": [
                {"parent_asin": "B000..."},
                {"parent_asin": "B001..."},
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
            },
        }
```

See `docs/agent_api_contract.json` for the complete machine-readable contract.

---

## Model Choice, Dependencies and Cost

The scoring agent intentionally does **not** use an external LLM or model API.

| Item | Submission |
|---|---|
| External inference model/API | None |
| External API calls during scoring | 0 |
| LLM prompt tokens during scoring | 0 |
| LLM completion tokens during scoring | 0 |
| Estimated API inference cost | **$0** |
| Network access required for scoring | No |
| Third-party Python dependencies | None |

The runtime path uses Python standard-library components including `sqlite3`, `re`, `json`, `pathlib`, and related utilities.

This design was chosen for reproducibility and operational simplicity. It should not be read as a claim that lexical retrieval is universally superior to neural or hybrid search; it is the architecture that survived our measured experiments under this benchmark and time constraint.

---

## Runtime

On the development machine used for final verification, the complete 200-session public evaluator took approximately:

```text
85–87 seconds
```

This is an environment-specific batch runtime, not a universal per-request latency measurement.

The final phrase-coherence tier increased runtime relative to the immediately preceding build. An additional candidate-text database lookup is a plausible optimization target, but the exact root cause was **not profiler-confirmed**, so we do not present it as established fact.

---

## Limitations and Future Work

### 1. Public-set generalization

The reported 88.0% HR@10 is measured on the released 200-session public set.

The organizer's 800-session private set may contain different failure patterns, so we do not claim equivalent private-set performance.

### 2. Primarily lexical architecture

The final system uses lexical matching rather than embeddings or a neural semantic retriever.

A lightweight TF-IDF semantic-style experiment did not improve the relevant miss population enough to justify integration, but this does **not** establish that stronger neural retrieval would fail.

**Future work:** evaluate genuine dense/hybrid retrieval against a separate validation set while preserving the current state architecture.

### 3. Residual candidate-generation depth

The final audit found that most remaining public misses were outside the internal Top-50 candidate pool.

Simply widening the pool had previously shown poor risk/reward, so we did not alter the frozen submission without a better candidate-generation mechanism.

**Future work:** investigate stronger first-stage retrieval rather than merely increasing candidate depth.

### 4. Phrase-coherence benchmark alignment

The evaluator constructs some conversational constraints from the target product's catalog fields.

Exact phrase matching is therefore particularly compatible with this benchmark's generation process and may be less powerful on organically written customer requests.

**Future work:** evaluate phrase and semantic signals on naturally authored shopping conversations.

### 5. Clarification policy

The agent uses a largely fixed attribute priority order rather than a learned information-gain policy.

**Future work:** dynamically choose the next question based on expected reduction in candidate uncertainty.

### 6. Runtime

The phrase-coherence tier improves ranking quality but increases batch evaluation runtime.

**Future work:** cache normalized candidate text or redesign the lookup path, subject to exact output-equivalence testing.

---

## Impact and Practicality

The core problem extends beyond this benchmark: real shoppers rarely express a perfect product query once.

A practical conversational search system needs to distinguish:

> **What does the shopper want now?**

from:

> **What information from the conversation remains useful for retrieval?**

That distinction supports changing preferences without discarding useful context and can be applied to other constraint-heavy catalog search and guided-shopping systems.

The current implementation is also operationally simple:

- deterministic execution;
- no external service dependency;
- no API credentials;
- zero inference cost;
- reproducible local evaluation;
- lightweight deployment requirements.

We present these as feasibility advantages, not as evidence of production-scale performance.

---

## Team Contributions

The project was developed collaboratively, with responsibilities changing between the initial working system and the final optimization/submission phase.

### Teammate — initial agent foundation, conversational robustness and demo

Based on the project handover, the teammate's main contributions were:

- built and tested the initial working multi-turn shopping agent that established the team's early **73.0% HR@10** milestone;
- implemented the foundational dialog-memory behaviour and proactive clarification flow;
- developed template-aware parsing and fallback handling for free-form or vague user responses;
- built the interactive live demo in `demo/interactive.py`;
- contributed later parsing/demo robustness improvements, including broader budget/style/no-preference/filler handling and safer fallback state updates;
- performed early evaluator experiments and documented the initial technical handover for the remainder of the project.

### Sam — evaluation strategy, final optimization direction, governance and submission

Sam's primary role in the final development cycle was project control, evaluation strategy and technical decision-making rather than claiming every repository edit as personally authored code.

Contributions included:

- reproduced key evaluator baselines and benchmark states locally;
- established the evidence-first experiment workflow and go/no-go criteria used for final optimization;
- directed the root-cause investigation of remaining misses, intent-override failures and ranking saturation;
- coordinated and approved the progression from the team's **73.0% HR@10** working milestone to the final **88.0% HR@10** implementation;
- required session-level regression reporting, targeted tests, simulation-to-production equivalence and rollback-safe Git checkpoints before accepting scoring changes;
- coordinated concurrent teammate changes, merge/reconciliation decisions and the final scoring freeze;
- led the final no-overfitting audit, repository hardening, reproducibility verification and submission-readiness process;
- owned the final technical narrative, metric/limitation disclosures and README/Devpost preparation.

This division is intentionally stated conservatively: implementation and command execution performed through development tooling are not presented as personal human coding where the project record only supports direction, review or approval.

---

## Development Tooling

Development used Git/GitHub and AI-assisted coding/review tooling during the engineering workflow.

Those tools are **development aids only**. They are not runtime dependencies of the submitted agent.

The frozen scoring implementation itself is deterministic and makes no external model or network calls.

---

## Repository Map

```text
starter/agent.py
    Final team submission

starter/agent_baseline.py
    Organizer's weak BM25 reference implementation

evaluator/local_evaluator.py
    Organizer's unmodified public evaluator

demo/interactive.py
    Human-facing, unscored live demo

tests/
    54 unit tests

data/public_set.jsonl
    200 labeled public development sessions

docs/
    Competition specification, API contract and evaluation configuration

markdowns/
    Full experiment, simulation, verification and closeout history
```

---

## Data Source

The catalog and sessions are derived from **Amazon Reviews 2023** by McAuley Lab, UCSD, using the organizer-provided frozen Track 4 assets.

See `DATA_ATTRIBUTION.md` for the repository's data-attribution details.

---

## Submission Notes

- Public repository: this repository
- Scoring entry point: `starter/agent.py`
- Public evaluator: `python3 -m evaluator.local_evaluator`
- Interactive demo: `python3 -m demo.interactive`
- Public YouTube demo: **add the final video link here before submission**
- Full engineering evidence: `markdowns/`

For participant requirements, see:

- `docs/submission_rules.md`
- `docs/participant_release_checklist.md`

---

## Final Status

```text
Public HR@10:       88.0% (176 / 200)
MRR:                0.567583
MTTC:               5.495
TechnicalScore:     0.720375
Tests:              54 / 54 PASS
External API calls: 0
LLM tokens:         0
Inference cost:     $0
```

**Scoring implementation frozen for submission.**
