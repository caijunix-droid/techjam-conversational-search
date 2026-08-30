import json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from evaluator.local_evaluator import (
    load_jsonl, catalog_index, materialize_hidden_fields, initial_message,
    customer_reply, coarse_category, MAX_TURNS
)
from starter.agent import Agent, classify

samples = load_jsonl(REPO_ROOT / "data/public_set.jsonl")
catalog_ids, categories, products = catalog_index(REPO_ROOT / "data/catalog.jsonl")
override_samples = [s for s in samples if s["scenario_type"] == "intent_override"]

stale_persists = 0
same_bucket = 0
total = 0

for sample in override_samples:
    agent = Agent(REPO_ROOT / "data/catalog.jsonl")
    session_id = "probe_" + sample["sample_id"]
    agent.reset(session_id, sample["user_profile"])
    target = str(sample["ground_truth"]["parent_asin"])
    card, behavior = materialize_hidden_fields(sample, products)
    effective_sample = {**sample, "intent_card": card, "behavior": behavior}
    old_value = behavior["override"]["old_value"]
    new_value = behavior["override"]["new_value"]
    old_bucket = classify(old_value)
    new_bucket = classify(new_value)
    total += 1
    if old_bucket == new_bucket:
        same_bucket += 1

    disclosed = set()
    override_applied = False
    user_message = initial_message(effective_sample, coarse_category(categories.get(target, [])), disclosed)
    state_after_override = None
    for turn in range(1, MAX_TURNS + 1):
        response = agent.respond(session_id, user_message, turn, 10)
        state = agent._sessions[session_id]
        if override_applied and state_after_override is None:
            state_after_override = dict(state.slots)
        if turn == MAX_TURNS:
            break
        override = effective_sample.get("behavior", {}).get("override") or {}
        if not override_applied and turn + 1 == int(override.get("turn", 3)):
            override_applied = True
            user_message = str(override.get("message", ""))
        else:
            user_message, _ = customer_reply(effective_sample, response.get("ask_attribute"), disclosed, False)

    old_bucket_value = state_after_override.get(old_bucket, "") if state_after_override else ""
    if old_bucket != new_bucket and old_value.lower() in old_bucket_value.lower():
        stale_persists += 1
        print(f"{sample['sample_id']}: old={old_value!r}(bucket={old_bucket}) new={new_value!r}(bucket={new_bucket}) -> STALE PERSISTS: slots={state_after_override}")

print(f"\nTotal override sessions: {total}")
print(f"old/new classified to SAME bucket (override overwrites cleanly): {same_bucket}")
print(f"old/new classified to DIFFERENT buckets: {total - same_bucket}")
print(f"Of those different-bucket cases, stale old value verified still present in slots after override: {stale_persists}")
