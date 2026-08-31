# TechJam Conversational E-Commerce Search Challenge — Team Submission

Build an AI shopping agent that asks useful follow-up questions and recommends the customer's hidden target product within at most 10 turns.

This repository is the organizer's starter kit plus our team's completed submission: a fully deterministic, dependency-free conversational shopping agent implemented in `starter/agent.py`. It scores **88.0% HR@10** (176/200 public sessions) — see [Final Performance](#final-performance) below.

## What You Receive

- A frozen catalog of 50,000 products from the `Clothing_Shoes_and_Jewelry` category of Amazon Reviews 2023.
- 200 labeled public sessions for local development.
- A weak BM25 starter agent (`starter/agent_baseline.py`) and deterministic local evaluator.
- The Agent API contract and scoring rules.

The organizer keeps 800 additional sessions private for final evaluation.

## What This Agent Does

The agent holds a multi-turn conversation with a simulated shopper, asking one clarification question per turn (material, color, size, style, use case, budget, brand, or a free-form "feature"), and returns an updated ranked list of catalog products after every message. It never calls an external model — everything is deterministic keyword retrieval (SQLite FTS5 + BM25) reordered by how well each candidate matches what the customer has actually disclosed.

### The central insight: two different kinds of memory

The agent tracks the conversation in two separate structures, and keeping them separate is what most of our engineering work was about:

- **`active_slots` — what the customer currently wants.** This drives which question to ask next and which candidates get promoted, and it is updated *destructively*: if the customer says "actually, ignore my earlier preference, I need X instead," the old preference is genuinely superseded here.
- **`slots` — everything usable the customer has disclosed, ever.** This feeds the search query. A preference that gets superseded in `active_slots` (no longer the customer's current *intent*) may still be true and still be useful *retrieval evidence* — a customer who first said "cotton" and then pivoted to "cheap" hasn't necessarily stopped wanting cotton, so that evidence is preserved here rather than being silently overwritten.

Conflating these two was the single largest source of lost hits early in development (see `markdowns/fix01_intent_override_handover.md` onward) — an override message would correctly update what the agent asks about next, but would also destructively overwrite retrieval evidence the customer never actually contradicted.

## Architecture

```text
Conversation turn
  → template-aware message parsing (opener / clarification answer / override / "no preference")
  → conversation state (active_slots + slots, kept separate — see above)
  → SQLite FTS5 keyword retrieval → BM25 Top-50 candidate pool
  → re-rank the Top-50 pool, in strict priority order:
      1. active-term coverage       (does the candidate match the customer's CURRENT intent?)
      2. active-slot coverage       (does it match at least one term from EVERY active slot, not just the loudest one?)
      3. exact phrase coherence     (do multi-word disclosures like "95% Polyester, 5% Spandex"
                                      appear as an exact contiguous phrase, not just as scattered words?)
      4. original BM25 order        (final tie-break when everything above is identical)
  → Top-10 recommendations + next clarification question
```

Each tier only ever reorders candidates that are *already tied* on every tier above it — a later tier can never promote a candidate that scores worse on an earlier one. This ordering was built and verified incrementally; each tier's own simulation/implementation report lives under `markdowns/` (`fix01b2_*` for term coverage, `fix02a2_*` for slot coverage, `fix05p0_*`/`fix05_*` for phrase coherence).

## Final Performance

Measured with the organizer's own unmodified `evaluator/local_evaluator.py` against the 200 public sessions:

| Metric | Value |
|---|---|
| **HR@10** | **88.0%** (176 / 200 sessions) |
| MRR | 0.567583 |
| MTTC | 5.495 turns |
| Efficiency | 0.550500 |
| **TechnicalScore** | **0.720375** |
| Tests | 54 / 54 passing |

Scenario breakdown (public set: 80 Buying, 80 Browsing, 30 Intent Override, 10 Boundary):

| Scenario | HR@10 | MRR | MTTC |
|---|---|---|---|
| Boundary | 80.0% | 0.502778 | 6.60 |
| Browsing | 90.0% | 0.618204 | 5.30 |
| Buying | 88.75% | 0.495288 | 5.50 |
| Intent Override | 83.3% | 0.646984 | 5.63 |

**Baseline distinction** — two different numbers get called "baseline" in this project's history, and they should not be confused:

- The organizer provides a deliberately weak reference agent (`starter/agent_baseline.py`, stateless BM25 with no conversation memory) scoring **12.5% HR@10** (`docs/baseline_results.json`) — this is the floor any real submission is expected to beat.
- Our own first working multi-turn implementation (commit `500fe7b`, before any of the ranking-tier work described above) scored **73.0% HR@10**. That is *our own* early milestone, not an organizer-provided number. The engineering documented under `markdowns/` moved that 73.0% to the 88.0% reported above.

Full session-by-session verification, including exact commit SHAs and simulation-vs-production equivalence checks for every tier, is in `markdowns/fix05_implementation_handover.md` and `markdowns/fix05_commit_push_report.md`.

## Task

For each session, your agent receives an anonymized preference profile and a short customer message. Raw user IDs, review text, timestamps, and purchase history are never disclosed. On every turn the agent may:

- ask a natural clarification question in `message` and identify one requested field in `ask_attribute`;
- return a ranked list of up to 10 catalog `parent_asin` values;
- do both in the same response.

The session ends when the target product appears in the scored Top 10 or after turn 10. Sessions cover Buying, Browsing, Intent Override, and Boundary behavior.

## Download the Catalog

Download `catalog.jsonl.gz` from the GitHub Release attached to this repository, then run:

```bash
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
```

Verify the downloaded file using the published `SHA256SUMS` file.

## Quick Start

Python 3.10 or later is recommended. The agent uses only the Python standard library — no `pip install` step is required.

```bash
# 1. Run the unit test suite (54 tests covering every ranking tier)
python3 -m unittest discover -s tests -p 'test*.py'

# 2. Run the official 200-session evaluator against our agent
python3 -m evaluator.local_evaluator
# writes per-session results and aggregate metrics to results.json,
# and prints the summary (matches the "Final Performance" table above)

# 3. Try the agent yourself in a live, free-form conversation
python3 -m demo.interactive
```

The **evaluator** (`evaluator/local_evaluator.py`) is what actually measures HR@10/MRR/MTTC/TechnicalScore — it drives our agent through a scripted fake customer built from the 200 labeled public sessions. The **interactive demo** (`demo/interactive.py`) is a separate, unscored tool: it lets a real person type free-form messages to the same agent and see it respond live, so a judge can get a feel for the conversation without needing the labeled session data. It does not calculate accuracy.

Do not edit `evaluator/local_evaluator.py` or `data/public_set.jsonl` when reproducing our reported score — the evaluator, its labels, and the catalog are the organizer's frozen artifacts; only `starter/agent.py` is our submission.

For comparison, the organizer's own included weak BM25 starter (`starter/agent_baseline.py`) scores Hit Rate@10 `0.125`, MRR `0.068034`, and MTTC `9.81` on the released public set — see `docs/baseline_results.json`.

## Agent Interface

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return {
            "message": "Do you have a material preference?",
            "ask_attribute": "material",
            "recommendations": [
                {"parent_asin": "B000..."},
                {"parent_asin": "B001..."}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}
        }
```

`ask_attribute` is one of `category`, `material`, `color`, `size`, `style`, `brand`, `budget`, `feature`, `use_case`, `other`, or `null`. See `docs/agent_api_contract.json`.

## Technical Metrics

- **Hit Rate@10:** fraction of sessions that find the target within 10 turns.
- **MRR:** mean reciprocal rank of the target; a miss contributes zero.
- **MTTC:** mean first-hit turn; a miss is assigned turn 11.
- **Reported token usage:** prompt and completion tokens returned by the team's model client.

```text
TechnicalScore = 0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency = clip((11 - MTTC) / 10, 0, 1)
```

Only exact `parent_asin` equality produces a hit. Core metrics are also reported by scenario.

## Model Choice and Cost

Teams may use any legally accessible LLM API or local model. Teams manage their own credentials and must never commit API keys. Model choice, estimated cost, token usage, and latency must be disclosed. Token usage is a feasibility metric, not part of the core technical score. The organizer does not provide or reimburse model API credits; teams are responsible for any costs incurred through optional external services.

**Our team's disclosure** (verified directly against the code, not assumed):

- **Model / API used for scoring:** none. `starter/agent.py` and `evaluator/local_evaluator.py` import only Python standard-library modules (`json`, `re`, `sqlite3`, `pathlib`, `argparse`, `random`, `statistics`, `uuid`, `collections`) — no `requests`, no LLM SDK, no network call of any kind anywhere on the scoring path. `usage.prompt_tokens`/`usage.completion_tokens` are always reported as `0`.
- **Network access required for scoring:** none. The agent builds its own in-memory SQLite FTS5 index from the local catalog file at startup and never makes an outbound request.
- **External inference API calls:** 0.
- **LLM tokens used during scoring:** 0.
- **Estimated API inference cost:** $0.
- **Dependency manifest:** none needed — no `requirements.txt`/`pyproject.toml` is required to run this submission.

## Runtime

Measured on the development machine used for final verification: the full 200-session evaluator run (`python3 -m evaluator.local_evaluator`) takes approximately **85–87 seconds**. This is not a universal latency figure — it will vary with the judging machine's hardware. It is slower than the immediately-prior ranking tier (roughly 53 seconds) because of one additional per-turn database lookup added for the exact-phrase-coherence tier (see `markdowns/fix05_implementation_handover.md` §9); the suspected cause (an index gap on a lookup column) is documented but was **not confirmed with a profiler** and should be read as a hypothesis, not a proven root cause.

## Limitations

- **Public HR@10 (88.0%) does not guarantee equivalent performance on the organizer's 800 private sessions.** The public set is what every ranking tier described above was tuned and validated against; the private set may surface different failure patterns.
- **The architecture is entirely lexical** (SQLite FTS5 + BM25 + coverage/phrase tie-breaks) — it has no semantic or embedding-based matching. A read-only audit found this to be an intentional, evidence-based choice (a TF-IDF/embedding experiment was tried and rejected early on for near-zero recall — `markdowns/fix03_final_major_opportunity_audit.md`), not an oversight.
- **The exact-phrase-coherence tier is closely aligned with how this benchmark's own conversational constraints are generated** — the simulated customer's disclosed text is drawn directly from the target product's own catalog fields (`evaluator/local_evaluator.py`'s `intent_card()`), so a phrase match against the target is expected more often than it would be against organically-written customer language. This is disclosed explicitly in `markdowns/fix04a_implementation_handover.md` and `markdowns/fix05p0_exact_phrase_tiebreak_simulation.md` as a real caveat on how well this specific signal should be expected to generalize.
- **Runtime increased under the final ranking tier** (see Runtime above) — a genuine, disclosed trade-off accepted in exchange for the accuracy gain, not silently absorbed.
- A final internal audit (`markdowns/final_score_sprint_report.md`) explicitly searched for further improvements before submission and concluded none could be justified without risking these caveats getting worse — see that report for the full evidence trail.

## Files

```text
data/public_set.jsonl             200 labeled development sessions
docs/competition_specification.md participant rules and evaluation protocol
docs/agent_api_contract.json      machine-readable Agent contract
docs/evaluation_config.json       scoring configuration
docs/baseline_results.json        reproducible weak-starter reference score
starter/agent.py                  our team's submission (final ranking mechanism described above)
starter/agent_baseline.py         organizer's original weak BM25 reference agent (12.5% HR@10), kept for comparison
evaluator/local_evaluator.py      public-set simulator and scorer (organizer's, unmodified)
demo/interactive.py               unscored live demo -- see Quick Start
tests/                            54 unit tests covering every ranking tier
markdowns/                        full engineering history: every experiment, simulation, and
                                   implementation report behind the final agent, in chronological order
```

## Judging and Submission Policy

- Participant submission requirements: `docs/submission_rules.md`
- Participant release checklist: `docs/participant_release_checklist.md`
- Organizer-only final judging controls: `organizer/JUDGING_RUNBOOK.md`
- Organizer private release checklist: `organizer/private_release_checklist.md`
- Judging day operations SOP: `organizer/JUDGING_DAY_SOP.md`

## Data Source

The catalog and sessions are derived from Amazon Reviews 2023 by McAuley Lab, UCSD. See `DATA_ATTRIBUTION.md` before using or redistributing the data.
Sessions are sampled deterministically from the official Clothing 5-core leave-last-out split and joined to the frozen catalog.
