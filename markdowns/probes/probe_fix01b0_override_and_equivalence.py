import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from evaluator.local_evaluator import (
    load_jsonl, catalog_index, materialize_hidden_fields, initial_message,
    customer_reply, coarse_category, MAX_TURNS,
)
from starter.agent import Agent as PatchedAgent

ACCEPTED_BASELINE_COMMIT = "037b52d"
ACCEPTED_BASELINE_HASH = "5b1d38d99fd49d8ba61e5f2ea278e8acfd665f8dfc50aa69f130e20415313544"


def _load_baseline_agent_class():
    source = subprocess.run(
        ["git", "show", f"{ACCEPTED_BASELINE_COMMIT}:starter/agent.py"],
        cwd=REPO_ROOT, capture_output=True, check=True, text=True,
    ).stdout
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != ACCEPTED_BASELINE_HASH:
        raise RuntimeError(f"baseline hash mismatch: {digest}")
    spec = importlib.util.spec_from_loader("baseline_agent_ref", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "baseline_agent_ref.py", "exec"), module.__dict__)
    return module.Agent


BaselineAgent = _load_baseline_agent_class()

samples = load_jsonl(REPO_ROOT / "data/public_set.jsonl")
catalog_ids, categories, products = catalog_index(REPO_ROOT / "data/catalog.jsonl")
override_samples = [s for s in samples if s["scenario_type"] == "intent_override"]

active_stale_before = 0  # baseline slots, cross-bucket, stale
active_stale_after = 0   # patched active_slots, cross-bucket, stale
cross_bucket_total = 0
query_mismatches: list[str] = []

for sample in override_samples:
    patched = PatchedAgent(REPO_ROOT / "data/catalog.jsonl")
    baseline = BaselineAgent(REPO_ROOT / "data/catalog.jsonl")
    session_id = "probe_" + sample["sample_id"]
    patched.reset(session_id, sample["user_profile"])
    baseline.reset(session_id, sample["user_profile"])
    target = str(sample["ground_truth"]["parent_asin"])
    card, behavior = materialize_hidden_fields(sample, products)
    effective_sample = {**sample, "intent_card": card, "behavior": behavior}
    old_value = behavior["override"]["old_value"]
    new_value = behavior["override"]["new_value"]

    disclosed = set()
    override_applied = False
    user_message = initial_message(effective_sample, coarse_category(categories.get(target, [])), disclosed)

    mismatch_this_session = False
    # Snapshot active-state immediately after the override turn is processed
    # -- NOT at the end of the whole 10-turn conversation. Checking only the
    # final turn would conflate "never removed" with "removed correctly,
    # then legitimately re-stated later" (the evaluator's own initial_message()
    # never marks an intent-override old_value as `disclosed`, so the same
    # fact can be honestly re-offered in reply to a later, properly re-asked
    # question once the attribute is freed up -- observed directly via a
    # single-session trace before writing this check).
    active_state_right_after_override: dict | None = None
    just_overrode = False
    for turn in range(1, MAX_TURNS + 1):
        patched_response = patched.respond(session_id, user_message, turn, 10)
        baseline_response = baseline.respond(session_id, user_message, turn, 10)

        if just_overrode and active_state_right_after_override is None:
            active_state_right_after_override = dict(patched._sessions[session_id].active_slots)

        patched_query = patched._build_query(patched._sessions[session_id])
        baseline_query = baseline._build_query(baseline._sessions[session_id])
        if patched_query != baseline_query:
            mismatch_this_session = True

        if turn == MAX_TURNS:
            break
        override = effective_sample.get("behavior", {}).get("override") or {}
        if not override_applied and turn + 1 == int(override.get("turn", 3)):
            override_applied = True
            just_overrode = True
            user_message = str(override.get("message", ""))
        else:
            just_overrode = False
            user_message, _ = customer_reply(
                effective_sample, patched_response.get("ask_attribute"), disclosed, False
            )

    if mismatch_this_session:
        query_mismatches.append(sample["sample_id"])

    from starter.agent import classify
    old_bucket = classify(old_value)
    new_bucket = classify(new_value)
    if old_bucket != new_bucket:
        cross_bucket_total += 1
        baseline_slots = dict(baseline._sessions[session_id].slots)
        if old_value.lower() in baseline_slots.get(old_bucket, "").lower():
            active_stale_before += 1
        active_right_after = active_state_right_after_override or {}
        if old_value.lower() in active_right_after.get(old_bucket, "").lower():
            active_stale_after += 1

print(f"Total override sessions: {len(override_samples)}")
print(f"Cross-bucket cases: {cross_bucket_total}")
print(f"Active-state stale BEFORE (baseline slots, reference): {active_stale_before}/{cross_bucket_total}")
print(f"Active-state stale AFTER  (patched active_slots):      {active_stale_after}/{cross_bucket_total}")
print()
print(f"Retrieval query mismatches vs baseline: {len(query_mismatches)}/{len(override_samples)}")
if query_mismatches:
    print("Mismatched sample_ids:", query_mismatches)
else:
    print("All 30/30 override sessions: retrieval query byte-identical to baseline at every turn.")
