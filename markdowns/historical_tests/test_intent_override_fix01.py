from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent


def _make_catalog(directory: Path) -> Path:
    """Tiny synthetic catalog -- these tests exercise SessionState/_parse_message
    logic, not retrieval quality, so product content is irrelevant filler."""
    catalog_path = directory / "catalog.jsonl"
    rows = [
        {
            "parent_asin": "X1", "title": "Generic product", "features": [],
            "details": {}, "description": [], "categories": ["Clothing"],
            "store": "Example", "average_rating": 4.0, "rating_number": 1, "price": 20.0,
        },
    ]
    catalog_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return catalog_path


class IntentOverrideFix01Test(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog_path = _make_catalog(Path(self._tmp.name))
        self.agent = Agent(self.catalog_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _slots(self, session_id: str) -> dict[str, str]:
        return dict(self.agent._sessions[session_id].slots)

    # A. Different-attribute override: old=feature, new=material.
    def test_different_attribute_override_removes_old_and_sets_new(self) -> None:
        session_id = "case_a"
        self.agent.reset(session_id, {"preference_tags": []})
        self.agent.respond(session_id, "I'm looking for Shoes. Buckle closure", 1, 10)
        self.assertEqual(self._slots(session_id), {"feature": "Buckle closure"})

        self.agent.respond(
            session_id, "Actually, ignore my earlier preference. What I need is: leather.", 2, 10
        )
        slots = self._slots(session_id)
        self.assertNotIn("feature", slots, "superseded feature constraint must be removed")
        self.assertEqual(slots.get("material"), "leather")

    # B. Same-attribute override: old=color black, new=color white.
    def test_same_attribute_override_replaces_value(self) -> None:
        session_id = "case_b"
        self.agent.reset(session_id, {"preference_tags": []})
        self.agent.respond(session_id, "I'm looking for Shoes. black", 1, 10)
        self.assertEqual(self._slots(session_id), {"color": "black"})

        self.agent.respond(
            session_id, "Actually, ignore my earlier preference. What I need is: white.", 2, 10
        )
        slots = self._slots(session_id)
        self.assertEqual(slots.get("color"), "white")
        self.assertNotEqual(slots.get("color"), "black")

    # C. Preserve unrelated active constraints across an override.
    def test_unrelated_constraints_survive_override(self) -> None:
        session_id = "case_c"
        self.agent.reset(session_id, {"preference_tags": []})
        self.agent.respond(session_id, "I'm looking for Shoes. black", 1, 10)
        self.agent.respond(
            session_id, "For that, what matters is: leather; under $80.", 2, 10
        )
        before = self._slots(session_id)
        self.assertEqual(before.get("color"), "black")
        self.assertEqual(before.get("material"), "leather")
        self.assertIn("budget", before)

        self.agent.respond(
            session_id, "Actually, ignore my earlier preference. What I need is: white.", 3, 10
        )
        after = self._slots(session_id)
        self.assertEqual(after.get("color"), "white")
        self.assertEqual(after.get("material"), "leather", "unrelated material constraint must survive")
        self.assertEqual(after.get("budget"), before.get("budget"), "unrelated budget constraint must survive")

    # D. Old source slot already replaced (by something else) before override arrives.
    def test_override_does_not_delete_slot_if_source_no_longer_matches(self) -> None:
        session_id = "case_d"
        self.agent.reset(session_id, {"preference_tags": []})
        self.agent.respond(session_id, "I'm looking for Shoes. Buckle closure", 1, 10)
        self.assertEqual(self._slots(session_id), {"feature": "Buckle closure"})

        # Something else overwrites the 'feature' bucket before the override turn
        # (simulates the directive's case D: provenance no longer describes the
        # slot's current content).
        state = self.agent._sessions[session_id]
        state.slots["feature"] = "Something else entirely"

        self.agent.respond(
            session_id, "Actually, ignore my earlier preference. What I need is: leather.", 2, 10
        )
        slots = self._slots(session_id)
        self.assertEqual(
            slots.get("feature"), "Something else entirely",
            "must not blindly delete a slot value that no longer matches recorded provenance",
        )
        self.assertEqual(slots.get("material"), "leather")

    # E. Normal Buying / Browsing / Boundary flows are unaffected (no override involved).
    def test_normal_buying_flow_unaffected(self) -> None:
        session_id = "case_e_buying"
        self.agent.reset(session_id, {"preference_tags": []})
        response = self.agent.respond(
            session_id, "I'm looking for Shoes. A key requirement is: leather.", 1, 10
        )
        self.assertEqual(self._slots(session_id), {"material": "leather"})
        self.assertIsNotNone(response["ask_attribute"])

    def test_normal_browsing_flow_unaffected(self) -> None:
        session_id = "case_e_browsing"
        self.agent.reset(session_id, {"preference_tags": []})
        self.agent.respond(session_id, "I'm looking for Shoes, but I'm still exploring.", 1, 10)
        self.assertEqual(self._slots(session_id), {})

    def test_normal_boundary_flow_unaffected(self) -> None:
        session_id = "case_e_boundary"
        self.agent.reset(session_id, {"preference_tags": []})
        response = self.agent.respond(session_id, "I'm looking for Shoes, but I'm still exploring.", 1, 10)
        ask_attribute = response["ask_attribute"]
        self.agent.respond(
            session_id, f"I don't have a preference for {ask_attribute}; please use your judgment.", 2, 10
        )
        self.assertIn(ask_attribute, self.agent._sessions[session_id].exhausted)


if __name__ == "__main__":
    unittest.main()
