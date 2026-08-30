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
ACCEPTED_B2_COMMIT = "c30c712"
ACCEPTED_B2_HASH = "e3f324caf8e6c940d44293beffd6a71df489f56564639c5af800d70d2975b9b5"


def _load_b2_agent_class():
    source = subprocess.run(
        ["git", "show", f"{ACCEPTED_B2_COMMIT}:starter/agent.py"],
        cwd=REPO_ROOT, capture_output=True, check=True, text=True,
    ).stdout
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != ACCEPTED_B2_HASH:
        raise RuntimeError(f"B2 source hash mismatch: got {digest}, expected {ACCEPTED_B2_HASH}")
    spec = importlib.util.spec_from_loader("baseline_agent_b2_ref_a2", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "baseline_agent_b2_ref_a2.py", "exec"), module.__dict__)
    sys.modules["baseline_agent_b2_ref_a2"] = module
    return module.Agent


B2Agent = _load_b2_agent_class()


def _make_override_catalog(directory: Path) -> Path:
    # Small, isolated catalog for the override-safety test (F) only -- kept
    # separate from the shared slot-coverage catalog so its "leather" match
    # isn't diluted by the other tests' deliberately leather-containing
    # products.
    rows = [
        {"parent_asin": "P1", "title": "Shoes with buckle closure design", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P2", "title": "Shoes made of leather material", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P3", "title": "Shoes in classic black color", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
    ]
    catalog_path = directory / "catalog_override.jsonl"
    catalog_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return catalog_path


def _make_slot_catalog(directory: Path) -> Path:
    # Controlled catalog for the term-coverage/slot-coverage interaction
    # tests. Active vocabulary used across tests: "leather", "color",
    # "black", "suede" -- chosen so each product matches an exact,
    # deliberately controlled subset.
    rows = [
        {"parent_asin": "P_HTLS", "title": "Shoes color black suede combo", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P_LTHS", "title": "Shoes leather color trim", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P_B1", "title": "Shoes leather color style", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P_B2", "title": "Shoes color black style", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P_C1", "title": "Shoes leather color alpha", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P_C2", "title": "Shoes leather color beta", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P_E1", "title": "Shoes leather color gamma", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P_E2", "title": "Shoes leather black delta", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P2", "title": "Shoes made of leather material", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P3", "title": "Shoes in classic black color", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P4", "title": "Shoes leather and black combo", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
        {"parent_asin": "P1", "title": "Shoes with buckle closure design", "features": [], "details": {}, "description": [], "categories": ["Clothing", "Shoes"], "store": "Ex", "price": 40.0},
    ]
    catalog_path = directory / "catalog.jsonl"
    catalog_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return catalog_path


class Fix02A2Test(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.catalog_path = _make_slot_catalog(Path(self._tmp.name))
        self.patched = PatchedAgent(self.catalog_path)
        self.b2 = B2Agent(self.catalog_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _asins(self, response: dict) -> list[str]:
        return [row["parent_asin"] for row in response["recommendations"]]

    def _set_two_slots(self, agent, session_id: str) -> None:
        # slotA ("material"): 1 term -- "leather"
        # slotB ("feature"):  3 terms -- "color", "black", "suede"
        # Flattened active_terms (4 total): leather, color, black, suede
        agent.reset(session_id, {"preference_tags": []})
        state = agent._sessions[session_id]
        state.category = "Shoes"
        state.active_slots = {"material": "leather", "feature": "color black suede"}

    # A. Higher term coverage always wins, even over lower slot coverage.
    def test_a_term_coverage_dominates_slot_coverage(self) -> None:
        session_id = "case_a"
        self._set_two_slots(self.patched, session_id)
        response = self.patched.respond(session_id, "I don't have a preference for other.", 1, 10)
        asins = self._asins(response)
        # P_HTLS: matches color+black+suede (3/4 term coverage) but not
        # leather -> slotA unsatisfied, slotB satisfied -> slot coverage 0.5.
        # P_LTHS: matches leather+color only (2/4 term coverage) -> both
        # slots satisfied -> slot coverage 1.0.
        # P_HTLS has LOWER slot coverage but must still rank first because
        # its term coverage (0.75) beats P_LTHS's (0.5).
        self.assertLess(asins.index("P_HTLS"), asins.index("P_LTHS"))

    # B. Equal term coverage: higher slot coverage wins.
    def test_b_equal_term_coverage_higher_slot_coverage_wins(self) -> None:
        session_id = "case_b"
        self._set_two_slots(self.patched, session_id)
        response = self.patched.respond(session_id, "I don't have a preference for other.", 1, 10)
        asins = self._asins(response)
        # P_B1: matches leather+color (2/4 term coverage); slotA satisfied,
        # slotB satisfied (color) -> slot coverage 1.0.
        # P_B2: matches color+black (2/4 term coverage, SAME as P_B1); slotA
        # unsatisfied (no leather), slotB satisfied -> slot coverage 0.5.
        self.assertLess(asins.index("P_B1"), asins.index("P_B2"))

    # C. Equal term coverage AND equal slot coverage: original BM25 order preserved.
    def test_c_equal_term_and_slot_coverage_preserves_baseline_order(self) -> None:
        session_id = "case_c"
        self._set_two_slots(self.patched, session_id)
        response = self.patched.respond(session_id, "I don't have a preference for other.", 1, 10)
        state = self.patched._sessions[session_id]
        baseline_expr = self.patched._build_query(state)
        baseline_rows = self.patched.connection.execute(
            "SELECT parent_asin FROM products WHERE products MATCH ? "
            "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
            (baseline_expr, 50),
        ).fetchall()
        baseline_order = [str(r[0]) for r in baseline_rows]
        asins = self._asins(response)
        # P_C1 and P_C2 both match leather+color only -- identical term
        # coverage (2/4) and identical slot coverage (both slots satisfied,
        # 1.0) -- so their relative order must match baseline BM25 exactly.
        pair_baseline = [a for a in baseline_order if a in ("P_C1", "P_C2")]
        pair_final = [a for a in asins if a in ("P_C1", "P_C2")]
        self.assertEqual(pair_baseline, pair_final)

    # D. No active terms at all (hence no matchable slots): reduces exactly
    # to B2. (A slot can only be "matchable" if its tokenized value is
    # non-empty; since active_terms is derived from the same tokenizer over
    # the union of all slot values, active_terms is empty iff every
    # individual slot's tokenization is also empty -- so the only reachable
    # instance of "no matchable slots" is "no active terms at all", which is
    # exactly this browsing-turn-1 case.)
    def test_d_no_active_terms_reduces_exactly_to_b2(self) -> None:
        session_id = "case_d"
        message = "I'm looking for Shoes, but I'm still exploring."
        self.patched.reset(session_id, {"preference_tags": []})
        response = self.patched.respond(session_id, message, 1, 10)
        self.b2.reset(f"{session_id}_b2", {"preference_tags": []})
        b2_response = self.b2.respond(f"{session_id}_b2", message, 1, 10)
        self.assertEqual(self._asins(response), self._asins(b2_response))

    # E. A slot is satisfied by matching ANY one of its terms, not all of them.
    def test_e_slot_satisfied_by_any_one_term(self) -> None:
        session_id = "case_e"
        # slotA ("material"): 1 term -- "leather"
        # slotB ("feature"):  2 terms -- "color", "black"
        self.patched.reset(session_id, {"preference_tags": []})
        state = self.patched._sessions[session_id]
        state.category = "Shoes"
        state.active_slots = {"material": "leather", "feature": "color black"}
        response = self.patched.respond(session_id, "I don't have a preference for other.", 1, 10)
        state = self.patched._sessions[session_id]
        baseline_expr = self.patched._build_query(state)
        baseline_rows = self.patched.connection.execute(
            "SELECT parent_asin FROM products WHERE products MATCH ? "
            "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
            (baseline_expr, 50),
        ).fetchall()
        baseline_order = [str(r[0]) for r in baseline_rows]
        asins = self._asins(response)
        # P_E1 matches leather+color (not black); P_E2 matches leather+black
        # (not color) -- both hit exactly one DIFFERENT term of slotB, but
        # both must be scored as fully satisfying slotB (1 term is enough),
        # giving them identical term coverage (2/3) AND identical slot
        # coverage (2/2 = 1.0), so their relative order must be the
        # untouched baseline BM25 order -- neither is penalized for which
        # specific term of the slot it happened to match.
        pair_baseline = [a for a in baseline_order if a in ("P_E1", "P_E2")]
        pair_final = [a for a in asins if a in ("P_E1", "P_E2")]
        self.assertEqual(pair_baseline, pair_final)

    # F. Slot coverage uses active_slots only, never historical/superseded slots.
    def test_f_slot_coverage_uses_active_slots_not_superseded(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            catalog_path = _make_override_catalog(Path(d))
            agent = PatchedAgent(catalog_path)
            session_id = "case_f"
            messages = [
                "I'm looking for Shoes. Buckle closure",
                "Actually, ignore my earlier preference. What I need is: leather.",
            ]
            agent.reset(session_id, {"preference_tags": []})
            response = None
            for turn, message in enumerate(messages, start=1):
                response = agent.respond(session_id, message, turn, 10)
            state = agent._sessions[session_id]
            matchable = agent._matchable_slots(state)
            flattened = [term for slot in matchable for term in slot]
            self.assertIn("leather", flattened)
            self.assertNotIn("buckle", flattened)
            self.assertNotIn("closure", flattened)
            # Retrieval evidence (`slots`) still carries the old feature term
            # -- unchanged prior behaviour, not reopened here.
            self.assertEqual(state.slots.get("feature"), "Buckle closure")
            asins = self._asins(response)
            self.assertEqual(asins[0], "P2")  # sole clean "leather" match promoted to front

    # G. Final recommendations never exceed top_k, even with the new tiebreak.
    def test_g_final_recommendations_never_exceed_top_k(self) -> None:
        session_id = "case_g"
        self._set_two_slots(self.patched, session_id)
        response = self.patched.respond(session_id, "I don't have a preference for other.", 1, 3)
        self.assertLessEqual(len(response["recommendations"]), 3)
        self.assertEqual(len(response["recommendations"]), 3)

    # H. Existing B2 term-coverage-dominance behavior remains intact (single
    # matchable slot per active term -- slot coverage collapses to a no-op
    # here, so this must reproduce B2's own documented ranking exactly).
    # Uses its own small, isolated catalog (identical vocabulary to B2's own
    # test suite's equivalent case) rather than the shared slot-coverage
    # catalog, whose extra leather/black-containing products would otherwise
    # push P2/P3 out of the top_k=10 window and contaminate this check.
    def test_h_existing_b2_term_coverage_behavior_intact(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            catalog_path = _make_override_catalog(Path(d))
            agent = PatchedAgent(catalog_path)
            session_id = "case_h"
            agent.reset(session_id, {"preference_tags": []})
            agent.respond(session_id, "I'm looking for Shoes, but I'm still exploring.", 1, 10)
            response = agent.respond(session_id, "For that, what matters is: leather; black.", 2, 10)
            asins = self._asins(response)
            # P2 matches "leather" (1/2 term coverage); P3 matches "black"
            # (1/2); P1 matches neither (0/2) -- identical dominance ordering
            # to B2's own documented behavior.
            self.assertLess(asins.index("P2"), asins.index("P1"))
            self.assertLess(asins.index("P3"), asins.index("P1"))


if __name__ == "__main__":
    unittest.main()
