from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent as PatchedAgent

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_BASELINE_COMMIT = "037b52d"
ACCEPTED_BASELINE_HASH = "5b1d38d99fd49d8ba61e5f2ea278e8acfd665f8dfc50aa69f130e20415313544"


def _load_baseline_agent_class():
    """Load the exact accepted-baseline starter/agent.py straight from its git
    blob (not a hand-copied re-implementation), so retrieval-equivalence
    comparisons are against real baseline code, not a paraphrase of it."""
    source = subprocess.run(
        ["git", "show", f"{ACCEPTED_BASELINE_COMMIT}:starter/agent.py"],
        cwd=REPO_ROOT, capture_output=True, check=True, text=True,
    ).stdout
    import hashlib
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != ACCEPTED_BASELINE_HASH:
        raise RuntimeError(
            f"baseline source hash mismatch: got {digest}, expected {ACCEPTED_BASELINE_HASH}"
        )
    spec = importlib.util.spec_from_loader("baseline_agent_ref", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "baseline_agent_ref.py", "exec"), module.__dict__)
    sys.modules["baseline_agent_ref"] = module
    return module.Agent


BaselineAgent = _load_baseline_agent_class()


def _make_catalog(directory: Path) -> Path:
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


class Fix01B0Test(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog_path = _make_catalog(Path(self._tmp.name))
        self.patched = PatchedAgent(self.catalog_path)
        self.baseline = BaselineAgent(self.catalog_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _replay(self, agent, session_id: str, messages: list[str]) -> None:
        agent.reset(session_id, {"preference_tags": []})
        for turn, message in enumerate(messages, start=1):
            agent.respond(session_id, message, turn, 10)

    def _active_slots(self, session_id: str) -> dict[str, str]:
        return dict(self.patched._sessions[session_id].active_slots)

    def _patched_query(self, session_id: str) -> str:
        state = self.patched._sessions[session_id]
        return self.patched._build_query(state)

    def _baseline_query(self, session_id: str) -> str:
        state = self.baseline._sessions[session_id]
        return self.baseline._build_query(state)

    # A. Different-bucket override.
    def test_a_different_bucket_active_state_correct(self) -> None:
        session_id = "case_a"
        messages = [
            "I'm looking for Shoes. Buckle closure",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        self._replay(self.patched, session_id, messages)
        active = self._active_slots(session_id)
        self.assertNotIn("feature", active, "superseded feature must be gone from active intent")
        self.assertEqual(active.get("material"), "leather")

    def test_a_different_bucket_retrieval_evidence_retains_prior_term(self) -> None:
        session_id = "case_a_retrieval"
        messages = [
            "I'm looking for Shoes. Buckle closure",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        self._replay(self.patched, session_id, messages)
        retrieval_slots = dict(self.patched._sessions[session_id].slots)
        self.assertEqual(retrieval_slots.get("feature"), "Buckle closure")
        self.assertEqual(retrieval_slots.get("material"), "leather")

    # B. Same-bucket override.
    def test_b_same_bucket_active_state_replaces_value(self) -> None:
        session_id = "case_b"
        messages = [
            "I'm looking for Shoes. black",
            "Actually, ignore my earlier preference. What I need is: white.",
        ]
        self._replay(self.patched, session_id, messages)
        active = self._active_slots(session_id)
        self.assertEqual(active.get("color"), "white")

    def test_b_same_bucket_retrieval_matches_baseline_exactly(self) -> None:
        session_id = "case_b_retrieval"
        messages = [
            "I'm looking for Shoes. black",
            "Actually, ignore my earlier preference. What I need is: white.",
        ]
        self._replay(self.patched, session_id, messages)
        self._replay(self.baseline, session_id, messages)
        # Governing rule per directive: baseline retrieval equivalence, not
        # arbitrary accumulation. Baseline overwrites same-key dict entries,
        # so "black" does not survive in either agent's retrieval evidence.
        self.assertEqual(
            dict(self.patched._sessions[session_id].slots),
            dict(self.baseline._sessions[session_id].slots),
        )
        self.assertEqual(self._patched_query(session_id), self._baseline_query(session_id))

    # C. Preserve unrelated active constraints.
    def test_c_unrelated_active_constraints_survive(self) -> None:
        session_id = "case_c"
        messages = [
            "I'm looking for Shoes. black",
            "For that, what matters is: leather; under $80.",
            "Actually, ignore my earlier preference. What I need is: white.",
        ]
        self._replay(self.patched, session_id, messages)
        active = self._active_slots(session_id)
        self.assertEqual(active.get("color"), "white")
        self.assertEqual(active.get("material"), "leather")
        self.assertIn("budget", active)

    # D. Active-state question logic uses active_slots, not retrieval slots.
    def test_d_ask_attribute_ignores_stale_retrieval_evidence(self) -> None:
        session_id = "case_d"
        messages = [
            "I'm looking for Shoes. Buckle closure",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        self.patched.reset(session_id, {"preference_tags": []})
        for turn, message in enumerate(messages, start=1):
            response = self.patched.respond(session_id, message, turn, 10)
        state = self.patched._sessions[session_id]
        # 'feature' no longer active (superseded) -- it must be eligible to
        # be asked about again, i.e. NOT skipped just because retrieval
        # evidence (`slots`) still remembers "Buckle closure".
        self.assertIn("feature", state.slots)
        self.assertNotIn("feature", state.active_slots)
        next_attr = self.patched._next_ask_attribute(state)
        self.assertNotEqual(
            next_attr, None,
            "there should still be an eligible attribute to ask about",
        )

    # E. Retrieval-query equivalence for representative conversations.
    def test_e_retrieval_query_equivalence_representative_conversations(self) -> None:
        conversations = {
            "buying": [
                "I'm looking for Shoes. A key requirement is: leather.",
                "For that, what matters is: black; under $80.",
            ],
            "browsing": [
                "I'm looking for Shoes, but I'm still exploring.",
                "For that, what matters is: leather; black.",
            ],
            "override_cross_bucket": [
                "I'm looking for Shoes. Buckle closure",
                "For that, what matters is: black.",
                "Actually, ignore my earlier preference. What I need is: leather.",
                "For that, what matters is: under $80.",
            ],
            "override_same_bucket": [
                "I'm looking for Shoes. black",
                "Actually, ignore my earlier preference. What I need is: white.",
            ],
            "boundary": [
                "I'm looking for Shoes, but I'm still exploring.",
                "I don't have a preference for material; please use your judgment.",
            ],
        }
        for name, messages in conversations.items():
            with self.subTest(conversation=name):
                session_id = f"case_e_{name}"
                self._replay(self.patched, session_id, messages)
                self._replay(self.baseline, session_id, messages)
                self.assertEqual(
                    self._patched_query(session_id),
                    self._baseline_query(session_id),
                    f"retrieval query diverged from baseline for conversation {name!r}",
                )

    # F. Normal Buying / Browsing / Boundary flows unaffected.
    def test_f_normal_buying_flow_matches_baseline(self) -> None:
        session_id = "case_f_buying"
        messages = ["I'm looking for Shoes. A key requirement is: leather."]
        self._replay(self.patched, session_id, messages)
        self._replay(self.baseline, session_id, messages)
        self.assertEqual(self._patched_query(session_id), self._baseline_query(session_id))
        self.assertEqual(self._active_slots(session_id), {"material": "leather"})

    def test_f_normal_browsing_flow_matches_baseline(self) -> None:
        session_id = "case_f_browsing"
        messages = ["I'm looking for Shoes, but I'm still exploring."]
        self._replay(self.patched, session_id, messages)
        self._replay(self.baseline, session_id, messages)
        self.assertEqual(self._patched_query(session_id), self._baseline_query(session_id))

    def test_f_normal_boundary_flow_matches_baseline(self) -> None:
        session_id = "case_f_boundary"
        messages = [
            "I'm looking for Shoes, but I'm still exploring.",
            "I don't have a preference for material; please use your judgment.",
        ]
        self._replay(self.patched, session_id, messages)
        self._replay(self.baseline, session_id, messages)
        self.assertEqual(self._patched_query(session_id), self._baseline_query(session_id))


if __name__ == "__main__":
    unittest.main()
