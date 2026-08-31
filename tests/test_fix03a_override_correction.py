from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent as PatchedAgent

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_A2_COMMIT = "c642094"
ACCEPTED_A2_HASH = "33d4ee6580a5f7043f91bd8620b422c2c31c0d89f88e886bf0f78c0d2bd29f93"


def _load_a2_agent_class():
    source = subprocess.run(
        ["git", "show", f"{ACCEPTED_A2_COMMIT}:starter/agent.py"],
        cwd=REPO_ROOT, capture_output=True, check=True, text=True,
    ).stdout
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != ACCEPTED_A2_HASH:
        raise RuntimeError(f"A2 source hash mismatch: got {digest}, expected {ACCEPTED_A2_HASH}")
    spec = importlib.util.spec_from_loader("baseline_agent_a2_ref_fix03a", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "baseline_agent_a2_ref_fix03a.py", "exec"), module.__dict__)
    sys.modules["baseline_agent_a2_ref_fix03a"] = module
    return module.Agent


A2Agent = _load_a2_agent_class()


def _make_catalog(directory: Path) -> Path:
    rows = [
        {"parent_asin": "P1", "title": "Shoes with buckle closure design", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P2", "title": "Shoes made of leather material", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P3", "title": "Shoes 90 percent cotton 10 others blend", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P4", "title": "Shoes pure cotton fabric", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P5", "title": "Shoes in classic black color", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P6", "title": "Shoes in white color trim", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
    ]
    catalog_path = directory / "catalog.jsonl"
    catalog_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return catalog_path


class Fix03ATest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog_path = _make_catalog(Path(self._tmp.name))
        self.patched = PatchedAgent(self.catalog_path)
        self.a2 = A2Agent(self.catalog_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _replay(self, agent, session_id: str, messages: list[str], top_k: int = 10):
        agent.reset(session_id, {"preference_tags": []})
        response = None
        for turn, message in enumerate(messages, start=1):
            response = agent.respond(session_id, message, turn, top_k)
        return response

    # A. Existing unrelated bucket is preserved (merged, not destroyed).
    def test_a_existing_unrelated_bucket_preserved(self) -> None:
        session_id = "case_a"
        messages = [
            "I'm looking for Shoes. Pull On closure",
            "For that, what matters is: 90 percent cotton, 10 others.",
            "Actually, ignore my earlier preference. What I need is: cotton.",
        ]
        self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        # The tracked source ("feature": "Pull On closure") is superseded and gone.
        self.assertNotIn("feature", state.active_slots)
        # The UNRELATED material evidence from the clarification turn is
        # preserved, not silently overwritten -- the new override value is
        # merged in alongside it.
        self.assertIn("90 percent cotton, 10 others", state.active_slots.get("material", ""))
        self.assertIn("cotton", state.active_slots.get("material", ""))

    # B. Tracked source bucket still supersedes normally (fix must not make
    # genuine overrides additive).
    def test_b_tracked_source_bucket_still_replaces(self) -> None:
        session_id = "case_b"
        messages = [
            "I'm looking for Shoes. cotton",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        # override_source_attr was "material" (from turn-1 "cotton"), and the
        # new value "leather" also classifies to "material" -- this IS the
        # tracked bucket, so it must be a clean replace, not a merge.
        self.assertEqual(state.active_slots.get("material"), "leather")
        self.assertNotIn("cotton", state.active_slots.get("material", ""))

    # C. Empty destination bucket: behavior remains equivalent to prior production.
    def test_c_empty_destination_bucket_unchanged(self) -> None:
        session_id = "case_c"
        messages = [
            "I'm looking for Shoes. Buckle closure",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        response = self._replay(self.patched, session_id, messages)
        a2_response = self._replay(self.a2, f"{session_id}_a2", messages)
        state = self.patched._sessions[session_id]
        # material was never populated before the override -- direct set,
        # identical to prior production.
        self.assertEqual(state.active_slots.get("material"), "leather")
        self.assertEqual(
            [r["parent_asin"] for r in response["recommendations"]],
            [r["parent_asin"] for r in a2_response["recommendations"]],
        )

    # D. Unrelated scenarios (Buying/Browsing/Boundary) unchanged -- this
    # code path is only ever reached by the literal override message text,
    # which the evaluator only ever scripts for intent_override sessions.
    def test_d_buying_browsing_boundary_unaffected(self) -> None:
        flows = {
            "buying": ["I'm looking for Shoes. A key requirement is: leather."],
            "browsing": ["I'm looking for Shoes, but I'm still exploring."],
            "boundary": [
                "I'm looking for Shoes, but I'm still exploring.",
                "I don't have a preference for material; please use your judgment.",
            ],
        }
        for name, messages in flows.items():
            with self.subTest(flow=name):
                response = self._replay(self.patched, f"case_d_{name}", messages)
                a2_response = self._replay(self.a2, f"case_d_{name}_a2", messages)
                self.assertEqual(
                    [r["parent_asin"] for r in response["recommendations"]],
                    [r["parent_asin"] for r in a2_response["recommendations"]],
                )

    # E. FIX-03A's own scope: this test file pins active_slots behavior at
    # the FIX-03A commit only. FIX-04A (a later, separately authorized
    # change -- see test_fix04a_slots_preservation.py) intentionally
    # extends the same merge rule to retrieval evidence (`slots`), so this
    # test no longer pins slots to unconditional-overwrite; it pins the
    # feature bucket, which this scenario never touches on override, to
    # confirm the merge is scoped to the actually-overridden bucket only.
    def test_e_retrieval_evidence_untouched_buckets_unaffected(self) -> None:
        session_id = "case_e"
        messages = [
            "I'm looking for Shoes. Pull On closure",
            "For that, what matters is: 90 percent cotton, 10 others.",
            "Actually, ignore my earlier preference. What I need is: cotton.",
        ]
        self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        # The feature bucket (tracked source, never targeted by this
        # override's classified attr) is untouched, exactly as before.
        self.assertEqual(state.slots.get("feature"), "Pull On closure")

    # F. Existing override-related tests remain green (run separately via
    # the full suite; this is a direct spot-check of the specific B0/B2
    # override behavior that must remain intact).
    def test_f_prior_same_bucket_override_behavior_intact(self) -> None:
        session_id = "case_f"
        messages = [
            "I'm looking for Shoes. black",
            "Actually, ignore my earlier preference. What I need is: white.",
        ]
        self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        # turn-1 "black" classifies to "color" and IS the tracked source;
        # override new value "white" also lands in "color" -- same bucket,
        # so this is a clean replace, matching prior B0/B2 behavior exactly.
        self.assertEqual(state.active_slots.get("color"), "white")
        self.assertNotIn("black", state.active_slots.get("color", ""))


if __name__ == "__main__":
    unittest.main()
