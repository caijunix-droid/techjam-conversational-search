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
# The accepted FIX-01B0 commit -- the baseline FIX-01B1 is not allowed to
# regress. Loaded straight from its git blob (not a hand-copied
# re-implementation) so comparisons are against real accepted code.
ACCEPTED_BASELINE_COMMIT = "500fe7b"
ACCEPTED_BASELINE_HASH = "0c67512c8f30bacc8f19da346e160f0e8bb9291ea4af677cd76de43d23bdf354"


def _load_baseline_agent_class():
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
    spec = importlib.util.spec_from_loader("baseline_agent_b0_ref", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "baseline_agent_b0_ref.py", "exec"), module.__dict__)
    sys.modules["baseline_agent_b0_ref"] = module
    return module.Agent


BaselineAgent = _load_baseline_agent_class()


def _make_catalog(directory: Path) -> Path:
    # Ten "Shoes" products, all equally category/title-relevant to a bare
    # "Shoes" query, differentiated by extra terms so BM25 gives a
    # deterministic non-trivial base order and specific products can be
    # targeted by an active-intent term (leather / black / buckle+closure).
    rows = [
        {"parent_asin": "P1", "title": "Shoes with buckle closure design", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P2", "title": "Shoes made of leather material", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P3", "title": "Shoes in classic black color", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P4", "title": "Shoes leather and black combo", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P5", "title": "Shoes canvas sneaker casual", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P6", "title": "Shoes running sport model", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P7", "title": "Shoes formal office wear", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P8", "title": "Shoes winter boot warm", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P9", "title": "Shoes sandal summer open", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P10", "title": "Shoes slipper home comfort", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
    ]
    catalog_path = directory / "catalog.jsonl"
    catalog_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return catalog_path


class Fix01B1Test(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog_path = _make_catalog(Path(self._tmp.name))
        self.patched = PatchedAgent(self.catalog_path)
        self.baseline = BaselineAgent(self.catalog_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _replay(self, agent, session_id: str, messages: list[str]) -> list[dict]:
        agent.reset(session_id, {"preference_tags": []})
        response = None
        for turn, message in enumerate(messages, start=1):
            response = agent.respond(session_id, message, turn, 10)
        return response

    def _asins(self, response: dict) -> list[str]:
        return [row["parent_asin"] for row in response["recommendations"]]

    # A. Cross-bucket override: old feature must not get an active boost.
    def test_a_cross_bucket_override_only_new_active_term_boosted(self) -> None:
        session_id = "case_a"
        messages = [
            "I'm looking for Shoes. Buckle closure",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        response = self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]

        active_expression = self.patched._active_expression(state)
        self.assertIn('"leather"', active_expression)
        self.assertNotIn('"buckle"', active_expression)
        self.assertNotIn('"closure"', active_expression)

        # Retrieval evidence (`slots`) still carries the old feature term --
        # unchanged FIX-01B0 behaviour, not reopened here.
        self.assertEqual(state.slots.get("feature"), "Buckle closure")

        baseline_response = self._replay(self.baseline, "case_a_baseline", messages)
        patched_set = set(self._asins(response))
        baseline_set = set(self._asins(baseline_response))
        self.assertEqual(patched_set, baseline_set, "candidate SET must be unchanged from B0 baseline")

        asins = self._asins(response)
        self.assertIn("P2", asins)  # "leather" title
        # Every candidate containing "leather" (active match) must precede
        # every candidate that does not, regardless of BM25 base order.
        leather_asins = {"P2", "P4"} & set(asins)
        other_asins = set(asins) - leather_asins
        if leather_asins and other_asins:
            last_leather_pos = max(asins.index(a) for a in leather_asins)
            first_other_pos = min(asins.index(a) for a in other_asins)
            self.assertLess(last_leather_pos, first_other_pos)
        # P1 (title has "buckle"/"closure", the superseded term) must NOT be
        # treated as an active match: its relative order vs. baseline must be
        # unaffected by active-intent promotion (it is not in leather_asins).
        self.assertNotIn("P1", leather_asins)

    # B. Same-bucket override: only the new value is active.
    def test_b_same_bucket_override_only_new_value_boosted(self) -> None:
        session_id = "case_b"
        messages = [
            "I'm looking for Shoes. black",
            "Actually, ignore my earlier preference. What I need is: white.",
        ]
        response = self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        active_expression = self.patched._active_expression(state)
        self.assertNotIn('"black"', active_expression)
        # "white" never appears in this synthetic catalog, so the active
        # expression matches nothing -- ranking must fall back to baseline
        # order (proves no accidental boost of "black").
        baseline_response = self._replay(self.baseline, "case_b_baseline", messages)
        self.assertEqual(self._asins(response), self._asins(baseline_response))

    # C. Normal buying: no corruption, candidate set == baseline.
    def test_c_normal_buying_no_corruption(self) -> None:
        messages = ["I'm looking for Shoes. A key requirement is: leather."]
        response = self._replay(self.patched, "case_c", messages)
        baseline_response = self._replay(self.baseline, "case_c_baseline", messages)
        self.assertEqual(set(self._asins(response)), set(self._asins(baseline_response)))
        asins = self._asins(response)
        self.assertEqual(asins[0], "P2")  # sole "leather" match promoted to front (or tied first)

    # D. Normal browsing: no active constraint ever set -> identical to baseline.
    def test_d_normal_browsing_no_corruption(self) -> None:
        messages = ["I'm looking for Shoes, but I'm still exploring."]
        response = self._replay(self.patched, "case_d", messages)
        baseline_response = self._replay(self.baseline, "case_d_baseline", messages)
        self.assertEqual(self._asins(response), self._asins(baseline_response))

    # E. Boundary: no corruption.
    def test_e_boundary_no_corruption(self) -> None:
        messages = [
            "I'm looking for Shoes, but I'm still exploring.",
            "I don't have a preference for material; please use your judgment.",
        ]
        response = self._replay(self.patched, "case_e", messages)
        baseline_response = self._replay(self.baseline, "case_e_baseline", messages)
        self.assertEqual(self._asins(response), self._asins(baseline_response))

    # F. No active constraint at all -> byte-identical fallback to baseline.
    def test_f_no_active_constraint_falls_back_to_baseline_order(self) -> None:
        session_id = "case_f"
        messages = ["I'm looking for Shoes, but I'm still exploring."]
        response = self._replay(self.patched, session_id, messages)
        state = self.patched._sessions[session_id]
        self.assertEqual(self.patched._active_expression(state), "")
        baseline_response = self._replay(self.baseline, "case_f_baseline", messages)
        self.assertEqual(self._asins(response), self._asins(baseline_response))


if __name__ == "__main__":
    unittest.main()
