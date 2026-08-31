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
ACCEPTED_FIX04A_COMMIT = "cd03f19"
ACCEPTED_FIX04A_HASH = "fc85aa59b5865458da45c9c51d6bb206b385fb44105c2a0d6c5dbf344dabed23"


def _load_fix04a_agent_class():
    source = subprocess.run(
        ["git", "show", f"{ACCEPTED_FIX04A_COMMIT}:starter/agent.py"],
        cwd=REPO_ROOT, capture_output=True, check=True, text=True,
    ).stdout
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != ACCEPTED_FIX04A_HASH:
        raise RuntimeError(f"FIX-04A source hash mismatch: got {digest}, expected {ACCEPTED_FIX04A_HASH}")
    spec = importlib.util.spec_from_loader("baseline_agent_fix04a_ref_fix05", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "baseline_agent_fix04a_ref_fix05.py", "exec"), module.__dict__)
    sys.modules["baseline_agent_fix04a_ref_fix05"] = module
    return module.Agent


FIX04AAgent = _load_fix04a_agent_class()


def _row(asin, title="Shoes", categories="Clothing Shoes", features="", details="", store="Ex", price=40.0):
    return {
        "parent_asin": asin, "title": title, "categories": [categories], "features": [features] if features else [],
        "details": {"info": details} if details else {}, "store": store,
        "description": [], "price": price,
    }


def _make_catalog(directory: Path, rows: list[dict]) -> Path:
    catalog_path = directory / "catalog.jsonl"
    catalog_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return catalog_path


class Fix05PhraseTiebreakTest(unittest.TestCase):
    def _agent(self, rows: list[dict]) -> PatchedAgent:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        catalog_path = _make_catalog(Path(tmp.name), rows)
        return PatchedAgent(catalog_path)

    def _replay(self, agent, session_id: str, messages: list[str], top_k: int = 10):
        agent.reset(session_id, {"preference_tags": []})
        response = None
        for turn, message in enumerate(messages, start=1):
            response = agent.respond(session_id, message, turn, top_k)
        return response

    def _ranked_asins(self, response) -> list[str]:
        return [r["parent_asin"] for r in response["recommendations"]]

    # A. Phrase tier breaks a double-coverage (term + slot) tie: the
    # candidate with the full contiguous phrase ranks first.
    def test_a_phrase_breaks_double_coverage_tie(self):
        rows = [
            _row("CONTIG", features="This item has a wrap around strap for comfort"),
            _row("SCATTERED", features="strap included; wrap style; sold around the world"),
        ]
        agent = self._agent(rows)
        response = self._replay(agent, "case_a", ["I'm looking for Shoes. wrap around strap"])
        ranked = self._ranked_asins(response)
        self.assertEqual(ranked[0], "CONTIG")

    # B. Phrase score must NEVER let lower term coverage outrank higher
    # term coverage, even when the lower-coverage candidate has the phrase.
    def test_b_term_coverage_dominates_phrase(self):
        rows = [
            # Matches all 4 active terms (cotton, wrap, around, strap) --
            # term_coverage=1.0 -- but the phrase words are NOT contiguous.
            _row("FULL_TERMS", features="cotton blend", details="wrap style, sold around, strap included"),
            # Matches only wrap/around/strap (misses "cotton") --
            # term_coverage=0.75 -- but DOES have the full contiguous
            # phrase.
            _row("PARTIAL_TERMS_WITH_PHRASE", features="wrap around strap design"),
        ]
        agent = self._agent(rows)
        response = self._replay(agent, "case_b", [
            "I'm looking for Shoes. cotton",
            "For that, what matters is: wrap around strap.",
        ])
        ranked = self._ranked_asins(response)
        self.assertEqual(ranked[0], "FULL_TERMS")

    # C. Phrase score must NEVER let lower slot coverage outrank higher
    # slot coverage when term coverage ties.
    def test_c_slot_coverage_dominates_phrase(self):
        rows = [
            # Matches cotton (material slot satisfied) + wrap/around
            # (2 of 3 feature-slot terms -- feature slot still satisfied,
            # since satisfaction only needs >=1 hit). Both slots satisfied
            # -> slot_coverage=1.0. term_coverage = 3/4 = 0.75 (misses
            # "strap"). No contiguous phrase possible (missing "strap").
            _row("BOTH_SLOTS_SATISFIED", features="cotton fabric, wrap style, around edge"),
            # Matches wrap/around/strap (all 3 feature-slot terms, full
            # contiguous phrase!) but misses "cotton" entirely -- material
            # slot UNSATISFIED (0 hits) -> slot_coverage = 1/2 = 0.5.
            # term_coverage = 3/4 = 0.75 (tied with the other candidate).
            _row("ONE_SLOT_UNSATISFIED_WITH_PHRASE", features="wrap around strap design"),
        ]
        agent = self._agent(rows)
        response = self._replay(agent, "case_c", [
            "I'm looking for Shoes. cotton",
            "For that, what matters is: wrap around strap.",
        ])
        ranked = self._ranked_asins(response)
        self.assertEqual(ranked[0], "BOTH_SLOTS_SATISFIED")

    # D. Equal phrase score (both candidates have the identical phrase)
    # preserves the original (coverage/slot/BM25) order -- the phrase tier
    # cannot invent discrimination it wasn't given. Verified against the
    # accepted FIX-04A reference agent (which has no phrase key at all) run
    # on the IDENTICAL messages -- an apples-to-apples comparison, since
    # `baseline_index` is specific to the query expression actually used
    # (which depends on the active slots), not a universal "pure BM25"
    # ordering independent of them.
    def test_d_equal_phrase_preserves_prior_order(self):
        # Both contain the exact contiguous phrase, so phrase_coverage
        # ties for both -- whatever FIX-04A alone would have ranked first
        # (via coverage/slot_coverage/baseline BM25) must still rank first.
        rows = [
            _row("CANDIDATE_A", title="Wrap Around Strap Sandal wrap around strap"),
            _row("CANDIDATE_B", title="Item", features="wrap around strap"),
        ]
        agent = self._agent(rows)
        reference = FIX04AAgent(agent.catalog_path)
        messages = ["I'm looking for Shoes. wrap around strap"]
        response = self._replay(agent, "case_d", messages)
        ref_response = self._replay(reference, "case_d_ref", messages)
        self.assertEqual(self._ranked_asins(response), self._ranked_asins(ref_response))

    # E. Boilerplate phrase no-op: when the target and MULTIPLE competitors
    # all contain the same exact phrase, the phrase tier cannot invent
    # discrimination among them -- their relative order must match exactly
    # what the FIX-04A reference agent (no phrase key) produces for the
    # same messages.
    def test_e_boilerplate_phrase_shared_by_all_is_a_noop(self):
        rows = [
            _row("BOILER_1", title="Pull On closure Shoe pull on closure", features="pull on closure"),
            _row("BOILER_2", title="Item", features="pull on closure"),
            _row("BOILER_3", title="Another", details="pull on closure"),
        ]
        agent = self._agent(rows)
        reference = FIX04AAgent(agent.catalog_path)
        messages = ["I'm looking for Shoes. pull on closure"]
        response = self._replay(agent, "case_e", messages)
        ref_response = self._replay(reference, "case_e_ref", messages)
        self.assertEqual(self._ranked_asins(response), self._ranked_asins(ref_response))

    # F. No multi-token active slot -> matchable_phrases is empty -> ranking
    # reduces exactly to the accepted FIX-04A behavior (identical
    # recommendations to the unmodified FIX-04A reference agent).
    def test_f_no_multi_token_slot_matches_fix04a_reference(self):
        rows = [
            _row("RED_A", features="red shoes design", details="red color everywhere"),
            _row("RED_B", features="red shoes design"),
        ]
        agent = self._agent(rows)
        reference = FIX04AAgent(agent.catalog_path)
        messages = ["I'm looking for Shoes. red"]  # single-token slot only
        response = self._replay(agent, "case_f", messages)
        ref_response = self._replay(reference, "case_f_ref", messages)
        self.assertEqual(self._ranked_asins(response), self._ranked_asins(ref_response))

    # G. Contiguous means contiguous -- and means the correct order, not
    # just adjacency of the same token set. A candidate with the phrase
    # tokens present but in the WRONG order, or scattered, must not get
    # phrase credit.
    def test_g_contiguous_requires_exact_order(self):
        rows = [
            _row("CORRECT_ORDER", features="wrap around strap"),
            _row("REVERSED_ORDER", features="strap around wrap"),
        ]
        agent = self._agent(rows)
        response = self._replay(agent, "case_g", ["I'm looking for Shoes. wrap around strap"])
        ranked = self._ranked_asins(response)
        self.assertEqual(ranked[0], "CORRECT_ORDER")

    # H. Field scope: phrase occurrence is recognized in exactly
    # title/features/details/description, and NOT in categories/store,
    # even though those fields are indexed for plain term matching.
    def test_h_field_scope_excludes_categories_and_store(self):
        for allowed_field, field_kwarg in [
            ("title", {"title": "wrap around strap"}),
            ("features", {"features": "wrap around strap"}),
            ("details", {"details": "wrap around strap"}),
            ("description", None),  # handled specially below (list field)
        ]:
            with self.subTest(field=allowed_field):
                if allowed_field == "description":
                    in_scope_row = {
                        "parent_asin": "IN_SCOPE", "title": "Shoes", "categories": ["Clothing Shoes"],
                        "features": [], "details": {}, "store": "Ex",
                        "description": ["wrap around strap"], "price": 40.0,
                    }
                else:
                    in_scope_row = _row("IN_SCOPE", **field_kwarg)
                # Out-of-scope: exact phrase placed ONLY in `categories`
                # (indexed for term matching, but not an allowed phrase
                # field) -- term_coverage/slot_coverage still tie at 1.0
                # since FTS matches the words regardless of column.
                out_of_scope_row = _row("OUT_OF_SCOPE", categories="wrap around strap", features="", title="Shoes")
                agent = self._agent([in_scope_row, out_of_scope_row])
                response = self._replay(agent, f"case_h_{allowed_field}", ["I'm looking for Shoes. wrap around strap"])
                ranked = self._ranked_asins(response)
                self.assertEqual(ranked[0], "IN_SCOPE")

    # I. top_k contract holds on the phrase-tiebreak path.
    def test_i_recommendations_never_exceed_top_k(self):
        rows = [_row(f"P{i}", features="wrap around strap") for i in range(15)]
        agent = self._agent(rows)
        for top_k in (1, 2, 5, 10):
            with self.subTest(top_k=top_k):
                response = self._replay(agent, f"case_i_{top_k}", ["I'm looking for Shoes. wrap around strap"], top_k=top_k)
                self.assertLessEqual(len(response["recommendations"]), top_k)

    # J. Existing FIX-04A retrieval-evidence-preservation behavior (the
    # override merge on `state.slots`/`state.active_slots`) is untouched --
    # FIX-05 only changes ranking, never state/slot logic. Reproduces the
    # exact public-style example from the FIX-04A authorization.
    def test_j_fix04a_override_merge_behavior_intact(self):
        rows = [_row("ANY", features="filler")]
        agent = self._agent(rows)
        messages = [
            "I'm looking for Shoes. Pull On closure",
            "For that, what matters is: Cotton, Rayon.",
            "Actually, ignore my earlier preference. What I need is: cotton.",
        ]
        self._replay(agent, "case_j", messages)
        state = agent._sessions["case_j"]
        self.assertEqual(state.slots.get("material"), "Cotton, Rayon; cotton")
        self.assertEqual(state.slots.get("feature"), "Pull On closure")


if __name__ == "__main__":
    unittest.main()
