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
ACCEPTED_A3_COMMIT = "1e2848e"
ACCEPTED_A3_HASH = "c839811324f491049d397cad8b0b0c0a75d2466df272482037870a5ccddffb82"


def _load_a3_agent_class():
    source = subprocess.run(
        ["git", "show", f"{ACCEPTED_A3_COMMIT}:starter/agent.py"],
        cwd=REPO_ROOT, capture_output=True, check=True, text=True,
    ).stdout
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != ACCEPTED_A3_HASH:
        raise RuntimeError(f"FIX-03A source hash mismatch: got {digest}, expected {ACCEPTED_A3_HASH}")
    spec = importlib.util.spec_from_loader("baseline_agent_a3_ref_fix04a", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "baseline_agent_a3_ref_fix04a.py", "exec"), module.__dict__)
    sys.modules["baseline_agent_a3_ref_fix04a"] = module
    return module.Agent


A3Agent = _load_a3_agent_class()


def _make_catalog(directory: Path) -> Path:
    rows = [
        {"parent_asin": "P1", "title": "Shoes with Pull On closure design", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P2", "title": "Shoes made of leather material only", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P3", "title": "Shoes in Cotton and Rayon blend fabric", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P4", "title": "Shoes pure cotton fabric only", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P5", "title": "Shoes in classic black color", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P6", "title": "Shoes in white color trim", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P7", "title": "Buckle closure shoes basic style", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
    ]
    catalog_path = directory / "catalog.jsonl"
    catalog_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return catalog_path


class Fix04ATest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog_path = _make_catalog(Path(self._tmp.name))
        self.patched = PatchedAgent(self.catalog_path)
        self.a3 = A3Agent(self.catalog_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _replay(self, agent, session_id: str, messages: list[str], top_k: int = 10):
        agent.reset(session_id, {"preference_tags": []})
        response = None
        for turn, message in enumerate(messages, start=1):
            response = agent.respond(session_id, message, turn, top_k)
        return response

    # A. Unrelated existing state.slots (retrieval evidence) value is
    # preserved -- merged, not destroyed -- on override.
    def test_a_unrelated_retrieval_evidence_preserved(self) -> None:
        session_id = "case_a"
        messages = [
            "I'm looking for Shoes. Pull On closure",
            "For that, what matters is: 90 percent cotton, 10 others.",
            "Actually, ignore my earlier preference. What I need is: cotton.",
        ]
        self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        # tracked source ("feature") was never in the material bucket, so
        # the pre-existing material evidence must survive, with the new
        # override value merged in alongside it.
        self.assertIn("90 percent cotton, 10 others", state.slots.get("material", ""))
        self.assertIn("cotton", state.slots.get("material", ""))
        # The tracked source bucket itself is untouched by this override
        # (the override value classified into a different bucket).
        self.assertEqual(state.slots.get("feature"), "Pull On closure")

    # B. Tracked-source same-bucket override still replaces (must not
    # become additive just because it's the tracked bucket).
    def test_b_tracked_source_bucket_still_replaces(self) -> None:
        session_id = "case_b"
        messages = [
            "I'm looking for Shoes. cotton",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        self.assertEqual(state.slots.get("material"), "leather")
        self.assertNotIn("cotton", state.slots.get("material", ""))

    # C. Empty destination bucket: retrieval-evidence behavior, and the
    # resulting recommendations, remain exactly equivalent to the accepted
    # FIX-03A production agent.
    def test_c_empty_destination_bucket_matches_fix03a(self) -> None:
        session_id = "case_c"
        messages = [
            "I'm looking for Shoes. Buckle closure",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        response = self._replay(self.patched, session_id, messages)
        a3_response = self._replay(self.a3, f"{session_id}_a3", messages)
        state = self.patched._sessions[session_id]
        self.assertEqual(state.slots.get("material"), "leather")
        self.assertEqual(
            [r["parent_asin"] for r in response["recommendations"]],
            [r["parent_asin"] for r in a3_response["recommendations"]],
        )

    # D. state.active_slots FIX-03A semantics remain byte-for-byte intact --
    # not just "still passes its own tests", but identical, dict-for-dict,
    # to what the accepted FIX-03A commit itself produces for the same
    # unrelated-bucket-merge scenario.
    def test_d_active_slots_fix03a_semantics_intact(self) -> None:
        session_id = "case_d"
        messages = [
            "I'm looking for Shoes. Pull On closure",
            "For that, what matters is: 90 percent cotton, 10 others.",
            "Actually, ignore my earlier preference. What I need is: cotton.",
        ]
        self._replay(self.patched, session_id, messages)
        self._replay(self.a3, f"{session_id}_a3", messages)
        patched_state = self.patched._sessions[session_id]
        a3_state = self.a3._sessions[f"{session_id}_a3"]
        self.assertEqual(dict(patched_state.active_slots), dict(a3_state.active_slots))
        self.assertNotIn("feature", patched_state.active_slots)

    # E. Buying / Browsing / Boundary scenarios are unaffected -- these
    # flows never reach the override branch at all, so recommendations must
    # be identical to the accepted FIX-03A agent.
    def test_e_buying_browsing_boundary_unaffected(self) -> None:
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
                response = self._replay(self.patched, f"case_e_{name}", messages)
                a3_response = self._replay(self.a3, f"case_e_{name}_a3", messages)
                self.assertEqual(
                    [r["parent_asin"] for r in response["recommendations"]],
                    [r["parent_asin"] for r in a3_response["recommendations"]],
                )

    # F. Retrieval evidence merged by FIX-04A is actually consumed by
    # _build_query() -- not dead state. Both the preserved and the new
    # material terms must appear in the built query.
    def test_f_merged_retrieval_evidence_reaches_build_query(self) -> None:
        session_id = "case_f"
        messages = [
            "I'm looking for Shoes. Pull On closure",
            "For that, what matters is: Cotton, Rayon.",
            "Actually, ignore my earlier preference. What I need is: cotton.",
        ]
        self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        query = self.patched._build_query(state)
        self.assertIn('"cotton"', query)
        self.assertIn('"rayon"', query)

    # G. Public-style multi-value material example (the exact case cited in
    # the FIX-04A authorization) preserves all usable terms, not just the
    # newest one.
    def test_g_public_style_multi_value_material_preserved(self) -> None:
        session_id = "case_g"
        messages = [
            "I'm looking for Shoes. Pull On closure",
            "For that, what matters is: Cotton, Rayon.",
            "Actually, ignore my earlier preference. What I need is: cotton.",
        ]
        self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        self.assertEqual(state.slots.get("material"), "Cotton, Rayon; cotton")

    # H. No recommendation output exceeds top_k, including on the override
    # merge path.
    def test_h_recommendations_never_exceed_top_k(self) -> None:
        messages = [
            "I'm looking for Shoes. Pull On closure",
            "For that, what matters is: 90 percent cotton, 10 others.",
            "Actually, ignore my earlier preference. What I need is: cotton.",
        ]
        for top_k in (1, 2, 5, 10):
            with self.subTest(top_k=top_k):
                response = self._replay(self.patched, f"case_h_{top_k}", messages, top_k=top_k)
                self.assertLessEqual(len(response["recommendations"]), top_k)


if __name__ == "__main__":
    unittest.main()
