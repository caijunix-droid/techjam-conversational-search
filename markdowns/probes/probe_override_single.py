import json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from evaluator.local_evaluator import (
    load_jsonl, catalog_index, materialize_hidden_fields, initial_message,
    customer_reply, coarse_category, normalize_recommendations, MAX_TURNS
)
from starter.agent import Agent

samples = load_jsonl(REPO_ROOT / "data/public_set.jsonl")
catalog_ids, categories, products = catalog_index(REPO_ROOT / "data/catalog.jsonl")
override_samples = [s for s in samples if s["scenario_type"] == "intent_override"]
sample = override_samples[0]

agent = Agent(REPO_ROOT / "data/catalog.jsonl")
session_id = "probe_1"
agent.reset(session_id, sample["user_profile"])
target = str(sample["ground_truth"]["parent_asin"])
card, behavior = materialize_hidden_fields(sample, products)
effective_sample = {**sample, "intent_card": card, "behavior": behavior}
print("sample_id:", sample["sample_id"])
print("intent_card:", json.dumps(card, indent=2))
print("override_behavior:", json.dumps(behavior, indent=2))

disclosed = set()
override_applied = False
user_message = initial_message(effective_sample, coarse_category(categories.get(target, [])), disclosed)

for turn in range(1, MAX_TURNS + 1):
    print(f"\n--- TURN {turn} ---")
    print("CUSTOMER SAYS:", repr(user_message))
    response = agent.respond(session_id, user_message, turn, 10)
    state = agent._sessions[session_id]
    print("AGENT slots AFTER parsing this message:", dict(state.slots))
    print("AGENT asked:", state.asked, "| exhausted:", state.exhausted)
    print("AGENT ask_attribute:", response["ask_attribute"], "| message:", response["message"])
    ranked = normalize_recommendations(response["recommendations"], catalog_ids)
    hit = override_applied and target in ranked
    print("target in top10:", hit, "| target rank if present:", (ranked.index(target)+1) if target in ranked else None)
    if hit:
        print("HIT on turn", turn)
        break
    if turn == MAX_TURNS:
        break
    override = effective_sample.get("behavior", {}).get("override") or {}
    if not override_applied and turn + 1 == int(override.get("turn", 3)):
        override_applied = True
        new_value = str(override.get("new_value", ""))
        if new_value:
            disclosed.add(new_value)
        user_message = str(override.get("message", ""))
        print(">>> OVERRIDE ABOUT TO BE SENT NEXT TURN <<<")
    else:
        user_message, _ = customer_reply(effective_sample, response.get("ask_attribute"), disclosed, False)
