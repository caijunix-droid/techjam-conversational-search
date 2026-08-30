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
        raise RuntimeError(f"baseline source hash mismatch: got {digest}, expected {ACCEPTED_BASELINE_HASH}")
    spec = importlib.util.spec_from_loader("baseline_agent_b0_ref_b2", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "baseline_agent_b0_ref_b2.py", "exec"), module.__dict__)
    sys.modules["baseline_agent_b0_ref_b2"] = module
    return module.Agent


BaselineAgent = _load_baseline_agent_class()


def _make_small_catalog(directory: Path) -> Path:
    # Small catalog for cases A/B/C/F/G/H/I: 10 "Shoes" products, controlled
    # so term-coverage differences are directly observable.
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


def _make_depth_catalog(directory: Path) -> Path:
    # For case E: 55 filler products that all outrank a single deep target on
    # the baseline query (each filler repeats "shoes" 3x in the heavily
    # title-weighted field vs. the deep target's single mention), pushing the
    # deep target to baseline rank 56 -- past the internal_depth=50 cutoff --
    # even though its active terms give it perfect (2/2) term coverage.
    rows = []
    for i in range(55):
        rows.append({
            "parent_asin": f"F{i}", "title": "Shoes Shoes Shoes filler item", "features": [], "details": {},
            "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0,
        })
    rows.append({
        "parent_asin": "DEEP", "title": "Shoes premium alpha", "features": [], "details": {},
        "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0,
    })
    catalog_path = directory / "catalog.jsonl"
    catalog_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return catalog_path


class Fix01B2Test(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog_path = _make_small_catalog(Path(self._tmp.name))
        self.patched = PatchedAgent(self.catalog_path)
        self.baseline = BaselineAgent(self.catalog_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _replay(self, agent, session_id: str, messages: list[str], top_k: int = 10):
        agent.reset(session_id, {"preference_tags": []})
        response = None
        for turn, message in enumerate(messages, start=1):
            response = agent.respond(session_id, message, turn, top_k)
        return response

    def _asins(self, response: dict) -> list[str]:
        return [row["parent_asin"] for row in response["recommendations"]]

    # A. No active terms -> baseline ordering, byte-identical to B0.
    def test_a_no_active_terms_falls_back_to_baseline_order(self) -> None:
        messages = ["I'm looking for Shoes, but I'm still exploring."]
        response = self._replay(self.patched, "case_a", messages)
        baseline_response = self._replay(self.baseline, "case_a_baseline", messages)
        self.assertEqual(self._asins(response), self._asins(baseline_response))

    # B. Candidate matching more active terms outranks one matching fewer.
    def test_b_higher_coverage_outranks_lower_coverage(self) -> None:
        session_id = "case_b"
        self.patched.reset(session_id, {"preference_tags": []})
        self.patched.respond(session_id, "I'm looking for Shoes, but I'm still exploring.", 1, 10)
        response = self.patched.respond(session_id, "For that, what matters is: leather; black.", 2, 10)
        asins = self._asins(response)
        # P4 matches both "leather" and "black" (2/2); P2 and P3 match only one (1/2).
        self.assertLess(asins.index("P4"), asins.index("P2"))
        self.assertLess(asins.index("P4"), asins.index("P3"))

    # C. Equal term coverage preserves baseline BM25 order (stable tiebreak).
    def test_c_equal_coverage_preserves_baseline_order(self) -> None:
        session_id = "case_c"
        self.patched.reset(session_id, {"preference_tags": []})
        self.patched.respond(session_id, "I'm looking for Shoes, but I'm still exploring.", 1, 10)
        response = self.patched.respond(session_id, "For that, what matters is: leather.", 2, 10)
        state = self.patched._sessions[session_id]
        # P2 and P4 both match "leather" (P4 also matches nothing else active
        # here, so both are 1/1); baseline B0 order among them must be kept.
        baseline_expr = self.patched._build_query(state)
        baseline_rows = self.patched.connection.execute(
            "SELECT parent_asin FROM products WHERE products MATCH ? "
            "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
            (baseline_expr, 50),
        ).fetchall()
        baseline_order = [str(r[0]) for r in baseline_rows]
        asins = self._asins(response)
        p2_p4_baseline = [a for a in baseline_order if a in ("P2", "P4")]
        p2_p4_final = [a for a in asins if a in ("P2", "P4")]
        self.assertEqual(p2_p4_baseline, p2_p4_final)

    # D. Final recommendations <= top_k, even though internal depth is 50.
    def test_d_final_recommendations_never_exceed_top_k(self) -> None:
        session_id = "case_d"
        self.patched.reset(session_id, {"preference_tags": []})
        response = self.patched.respond(session_id, "I'm looking for Shoes, but I'm still exploring.", 1, 3)
        self.assertLessEqual(len(response["recommendations"]), 3)
        self.assertEqual(len(response["recommendations"]), 3)  # 10 candidates exist, so exactly 3 expected

    # E. Target outside first 50 (internal_depth) cannot enter output, even
    # with perfect term coverage.
    def test_e_target_outside_internal_depth_never_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            catalog_path = _make_depth_catalog(Path(d))
            agent = PatchedAgent(catalog_path)
            session_id = "case_e"
            agent.reset(session_id, {"preference_tags": []})
            state = agent._sessions[session_id]
            # Directly control state for a deterministic baseline-vs-active
            # split: category-only baseline query (fillers outrank DEEP on
            # it), independent active terms that only DEEP matches perfectly.
            state.category = "Shoes"
            state.active_slots = {"feature": "premium alpha"}
            response = agent.respond(session_id, "irrelevant", 1, 10)
            # Sanity: DEEP really is outside the top 50 on the baseline query alone.
            baseline_expr = agent._build_query(state)
            baseline_rows = agent.connection.execute(
                "SELECT parent_asin FROM products WHERE products MATCH ? "
                "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
                (baseline_expr, 56),
            ).fetchall()
            baseline_order = [str(r[0]) for r in baseline_rows]
            self.assertGreater(baseline_order.index("DEEP"), 49, "test setup requires DEEP to rank beyond 50")
            self.assertNotIn("DEEP", self._asins(response))

    # F. Buying behavior valid: query equivalence to baseline preserved.
    def test_f_buying_flow_query_equivalence(self) -> None:
        messages = ["I'm looking for Shoes. A key requirement is: leather."]
        response = self._replay(self.patched, "case_f", messages)
        baseline_response = self._replay(self.baseline, "case_f_baseline", messages)
        self.assertEqual(set(self._asins(response)), set(self._asins(baseline_response)))
        self.assertEqual(self._asins(response)[0], "P2")

    # G. Browsing behavior valid: no corruption when no constraint given yet.
    def test_g_browsing_flow_no_corruption(self) -> None:
        messages = ["I'm looking for Shoes, but I'm still exploring."]
        response = self._replay(self.patched, "case_g", messages)
        baseline_response = self._replay(self.baseline, "case_g_baseline", messages)
        self.assertEqual(self._asins(response), self._asins(baseline_response))

    # H. Intent Override: active-term coverage uses active_slots, not the
    # superseded historical-only term retained in slots.
    def test_h_intent_override_uses_active_slots_not_superseded_term(self) -> None:
        session_id = "case_h"
        messages = [
            "I'm looking for Shoes. Buckle closure",
            "Actually, ignore my earlier preference. What I need is: leather.",
        ]
        self.patched.reset(session_id, {"preference_tags": []})
        for turn, message in enumerate(messages, start=1):
            response = self.patched.respond(session_id, message, turn, 10)
        state = self.patched._sessions[session_id]
        active_terms = self.patched._active_terms(state)
        self.assertIn("leather", active_terms)
        self.assertNotIn("buckle", active_terms)
        self.assertNotIn("closure", active_terms)
        # Retrieval evidence (`slots`) still carries the old feature term --
        # unchanged FIX-01B0 behaviour, not reopened here.
        self.assertEqual(state.slots.get("feature"), "Buckle closure")
        asins = self._asins(response)
        self.assertEqual(asins[0], "P2")  # sole "leather" match promoted to front

    # I. Boundary behavior valid: no corruption.
    def test_i_boundary_flow_no_corruption(self) -> None:
        messages = [
            "I'm looking for Shoes, but I'm still exploring.",
            "I don't have a preference for material; please use your judgment.",
        ]
        response = self._replay(self.patched, "case_i", messages)
        baseline_response = self._replay(self.baseline, "case_i_baseline", messages)
        self.assertEqual(self._asins(response), self._asins(baseline_response))


if __name__ == "__main__":
    unittest.main()
