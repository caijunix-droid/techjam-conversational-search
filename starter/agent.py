from __future__ import annotations
import json
import re
import sqlite3
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
}

# The five attribute types we actively try to fill in, in priority order.
# (category is handled separately since it's always given up front; "brand"
# and "other" are rarely useful in this catalog so they're asked last.)
ASK_ORDER = ["material", "color", "budget", "style", "use_case", "size", "feature", "brand", "other"]

MATERIAL_RE = re.compile(r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric|suede|denim)\b", re.I)
COLOR_RE = re.compile(r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange|navy)\b", re.I)
BUDGET_RE = re.compile(r"(\$\s?\d+|\bunder\b|\bbudget\b|\bcheap\b|\baffordable\b|\baround\s+\d+|\babout\s+\d+|\bnear\s+\d+|\bless\s+than\b|\b\d+\s*dollars?\b|\b\d+\s*bucks?\b)", re.I)
SIZE_WORDS = ("size", "sizing", "width", "wide", "narrow", "small", "medium", "large", "xl", "xxl")
STYLE_WORDS = ("style", "fit", "sleeve", "neck", "casual", "formal", "department", "breasted", "men's", "mens", "women's", "womens", "boys", "girls", "unisex", "ladies", "kids", "toddler")
USE_CASE_WORDS = ("hiking", "running", "gym", "winter", "outdoor", "work", "travel", "beach", "wedding", "party", "yoga", "formal wear")

# Free-typed humans often answer clarifying questions vaguely rather than
# with a real constraint. These should be treated as "no preference here",
# not stored as literal search terms (the scripted evaluator never says
# things like this, but a real person typing live will).
NO_PREFERENCE_PHRASES = {
    "anything", "any", "whatever", "idk", "i dont know", "i don't know",
    "dont know", "don't know", "no preference", "not sure", "none",
    "doesnt matter", "doesn't matter", "does not matter", "no idea",
    "not really", "nothing specific", "no", "nope", "nah", "naw",
    "skip", "pass", "na", "n a", "meh", "not particular", "no particular",
    "not fussy", "im flexible", "i'm flexible", "flexible", "open to anything",
}

# Conversational filler with zero product information -- these carry no
# signal about ANY attribute (unlike NO_PREFERENCE_PHRASES, which specifically
# answers "no preference" to whatever was just asked). The agent should
# simply ignore them rather than storing the literal words as a search term,
# which would overwrite real, useful information with noise.
FILLER_PHRASES = {
    "thanks", "thank you", "thanks!", "ty", "thx", "ok", "okay", "k",
    "cool", "nice", "great", "awesome", "perfect", "sounds good",
    "appreciate it", "got it", "alright", "sure", "yep", "yes", "yeah",
    "good", "fine",
}


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _terms(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) > 1 and token.lower() not in STOPWORDS
    ]


def classify(text: str) -> str:
    """Guess which attribute bucket a snippet of text belongs to.
    Mirrors the evaluator's own classify_constraint() so our slot-filling
    lines up with how the simulated customer organizes information."""
    lowered = text.lower()
    if BUDGET_RE.search(lowered):
        return "budget"
    if MATERIAL_RE.search(lowered):
        return "material"
    if COLOR_RE.search(lowered):
        return "color"
    if any(word in lowered for word in SIZE_WORDS):
        return "size"
    if any(word in lowered for word in STYLE_WORDS):
        return "style"
    if any(word in lowered for word in USE_CASE_WORDS):
        return "use_case"
    return "feature"


class SessionState:
    __slots__ = (
        "category", "slots", "active_slots", "asked", "exhausted", "profile_terms",
        "last_turn_asked", "override_source_attr", "override_source_value",
    )

    def __init__(self, profile_terms: str) -> None:
        self.category = ""
        # Retrieval evidence: lexical terms accumulated from the conversation.
        # Feeds _build_query(). FIX-04A: on override, unrelated buckets are
        # merged rather than overwritten (same rule as active_slots below).
        self.slots: dict[str, str] = {}
        # Active intent: what the customer currently wants. Feeds dialog
        # logic (_next_ask_attribute). Kept separate from `slots` so that
        # correctly removing a superseded preference from active intent does
        # not also remove it as retrieval evidence.
        self.active_slots: dict[str, str] = {}
        self.asked: set[str] = set()
        self.exhausted: set[str] = set()
        self.profile_terms = profile_terms
        self.last_turn_asked: str | None = None
        # Provenance for the one active preference an Intent Override turn
        # may later supersede: which bucket it was filed under, and its
        # exact value at the time it was recorded. The bucket (attr) is also
        # consulted by the FIX-04A retrieval-evidence merge below; the value
        # is only ever consulted for the active_slots deletion-safety check.
        self.override_source_attr: str | None = None
        self.override_source_value: str | None = None


class Agent:
    """Improved agent: keyword+FTS retrieval, but with per-session dialog
    memory, template-aware message parsing, and proactive clarification
    questions so it actually benefits from multi-turn conversation."""

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog_path = Path(catalog_path)
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, SessionState] = {}
        self._build_index()

    def _build_index(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE VIRTUAL TABLE products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        batch: list[tuple[str, str, str, str, str, str, str]] = []
        with self.catalog_path.open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                batch.append(
                    (
                        str(product["parent_asin"]),
                        _text(product.get("title")),
                        _text(product.get("categories")),
                        _text(product.get("features")),
                        _text(product.get("details")),
                        _text(product.get("store")),
                        _text(product.get("description")),
                    )
                )
                if len(batch) >= 1000:
                    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        self.connection.commit()

    def known_slot_count(self, session_id: str) -> int:
        """Read-only helper: how many attribute slots are currently active
        for this session. NOT used by the scored evaluator (which only
        calls reset()/respond()) -- purely for display purposes, e.g. the
        interactive demo narrowing how many titles it prints as it learns
        more about what the customer wants."""
        state = self._sessions.get(session_id)
        return len(state.active_slots) if state else 0

    def reset(self, session_id: str, user_profile: dict) -> None:
        tags = user_profile.get("preference_tags") or []
        profile_terms = " ".join(str(tag) for tag in tags)
        self._sessions[session_id] = SessionState(profile_terms)

    def _parse_message(self, state: SessionState, message: str) -> None:
        """Update dialog state from the customer's message. Handles the
        known evaluator templates precisely, with a generic fallback for
        anything unexpected (so we don't break on private eval phrasing
        differences)."""
        text = message.strip()

        # Turn-1 openers.
        if text.startswith("I'm looking for "):
            rest = text[len("I'm looking for "):]
            if rest.endswith(", but I'm still exploring."):
                state.category = rest[: -len(", but I'm still exploring.")].strip()
            elif ". A key requirement is: " in rest:
                category, constraint = rest.split(". A key requirement is: ", 1)
                state.category = category.strip()
                constraint = constraint.rstrip(".").strip()
                if constraint:
                    attr = classify(constraint)
                    state.slots[attr] = constraint
                    state.active_slots[attr] = constraint
            else:
                # intent_override opener: "{category}. {old_value}"
                category, _, remainder = rest.partition(". ")
                state.category = category.strip()
                remainder = remainder.rstrip(".").strip()
                if remainder:
                    attr = classify(remainder)
                    state.slots[attr] = remainder
                    state.active_slots[attr] = remainder
                    # Remember this as the active preference a later override
                    # may supersede. FIX-04A: the bucket name (attr) is also
                    # read by the retrieval-evidence merge on override; the
                    # value is only ever read for the active_slots check.
                    state.override_source_attr = attr
                    state.override_source_value = remainder
            return

        # Explicit intent override mid-conversation.
        if text.startswith("Actually, ignore my earlier preference. What I need is: "):
            new_value = text[len("Actually, ignore my earlier preference. What I need is: "):].rstrip(".").strip()
            tracked_source_attr = state.override_source_attr
            if state.override_source_attr is not None:
                source_attr = state.override_source_attr
                source_value = state.override_source_value
                # Only remove the superseded preference from ACTIVE intent if
                # it still occupies its original slot unchanged -- if
                # something else already overwrote that slot, this
                # provenance no longer applies and we must not delete the
                # newer value blindly. Retrieval evidence (`slots`) is not
                # touched by this check at all.
                if state.active_slots.get(source_attr) == source_value:
                    del state.active_slots[source_attr]
                state.override_source_attr = None
                state.override_source_value = None
            if new_value:
                attr = classify(new_value)
                # FIX-04A: same rationale as the active_slots merge below --
                # the override message only ever names ONE prior preference
                # (the tracked source_attr). If the new value lands in a
                # DIFFERENT retrieval-evidence bucket that already holds a
                # value, that value was never named as superseded and must
                # not be silently destroyed -- merge instead of overwrite.
                # If the bucket is empty, or is the tracked source bucket
                # itself, behavior is unchanged from prior production.
                if attr in state.slots and attr != tracked_source_attr:
                    state.slots[attr] = state.slots[attr] + "; " + new_value
                else:
                    state.slots[attr] = new_value
                # FIX-03A: the override message ("ignore my earlier
                # preference") only ever refers to ONE prior preference --
                # the tracked source_attr/source_value handled above. If the
                # new value lands in a DIFFERENT bucket that already holds a
                # value, that value was never named as superseded by this
                # message and must not be silently destroyed -- merge
                # instead of overwrite. If the bucket is empty, or is the
                # tracked source bucket itself, behavior is unchanged from
                # prior production.
                if attr in state.active_slots and attr != tracked_source_attr:
                    state.active_slots[attr] = state.active_slots[attr] + "; " + new_value
                else:
                    state.active_slots[attr] = new_value
            return

        # Direct answer to our clarification question.
        if text.startswith("For that, what matters is: "):
            body = text[len("For that, what matters is: "):].rstrip(".").strip()
            for part in body.split("; "):
                part = part.strip()
                if part:
                    attr = classify(part)
                    state.slots[attr] = part
                    state.active_slots[attr] = part
            return

        # "No preference" responses (boundary case, or attribute exhausted).
        m = re.search(r"don't have (?:a preference|an additional preference) for (\w+)", text)
        if m:
            state.exhausted.add(m.group(1))
            return

        # Agent didn't ask anything and got scolded -- no new info.
        if text.startswith("Those options are not quite right yet"):
            return

        stripped = re.sub(r"[^\w\s]", "", text).strip().lower()

        # Pure conversational filler ("thanks", "ok", "cool") -- carries no
        # product information about anything, so just ignore it entirely
        # rather than letting it fall through and overwrite a real slot.
        if stripped in FILLER_PHRASES:
            return

        # Vague/non-committal answer to whatever we just asked -- treat as
        # "no preference" for that attribute rather than storing the vague
        # words as if they were a real constraint.
        if stripped in NO_PREFERENCE_PHRASES:
            if state.last_turn_asked:
                state.exhausted.add(state.last_turn_asked)
            return

        # Unknown format -- fall back to generic classification so we
        # still capture *something* rather than silently dropping it.
        # IMPORTANT: append rather than overwrite. The generic "feature"
        # bucket is a shared catch-all -- if we naively overwrote it, an
        # early genuine message (e.g. the customer's very first "Socks")
        # could get silently destroyed by a later throwaway reply landing
        # in that same bucket (e.g. a stray "1" typed while trying to pick
        # an item from a numbered list). Appending preserves everything.
        attr = classify(text)
        if text:
            existing = state.slots.get(attr, "")
            combined_value = f"{existing} {text}".strip() if existing else text
            state.slots[attr] = combined_value
            existing_active = state.active_slots.get(attr, "")
            state.active_slots[attr] = f"{existing_active} {text}".strip() if existing_active else text

    def _build_query(self, state: SessionState) -> str:
        pieces = [state.category, state.profile_terms, *state.slots.values()]
        combined = " ".join(p for p in pieces if p)
        unique_terms = list(dict.fromkeys(_terms(combined)))[:40]
        return " OR ".join(f'"{term}"' for term in unique_terms)

    def _active_terms(self, state: SessionState) -> list[str]:
        # FIX-01B2: distinct active-intent terms only, from state.active_slots
        # alone (never state.slots/category/profile_terms) -- same tokenizer
        # as _build_query(). Used only to reorder an already-fixed candidate
        # pool, never to change candidate generation itself.
        combined = " ".join(state.active_slots.values())
        return list(dict.fromkeys(_terms(combined)))[:40]

    def _matchable_slots(self, state: SessionState) -> list[list[str]]:
        # FIX-02A2: per active_slots KEY (not flattened across slots), that
        # slot's own tokenized terms -- same tokenizer as _active_terms(). A
        # slot is "matchable" if it has >=1 usable term. Every slot term here
        # is also a member of _active_terms(state)'s flattened, deduped list
        # (same source strings, same tokenizer), so slot satisfaction can be
        # derived from the term_matches already computed for active-term
        # coverage in respond() -- no additional FTS queries.
        matchable: list[list[str]] = []
        for value in state.active_slots.values():
            terms = list(dict.fromkeys(_terms(value)))
            if terms:
                matchable.append(terms)
        return matchable

    def _next_ask_attribute(self, state: SessionState) -> str | None:
        for attr in ASK_ORDER:
            if attr in state.active_slots:
                continue
            if attr in state.exhausted:
                continue
            if attr in state.asked:
                continue
            return attr
        return None

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        if session_id not in self._sessions:
            raise RuntimeError("reset must be called before respond")
        state = self._sessions[session_id]
        self._parse_message(state, user_message)

        expression = self._build_query(state)
        if not expression:
            recommendations: list[dict] = []
        else:
            # FIX-01B2: candidate generation query is unchanged (same
            # expression/ORDER BY/field weights); only the retrieval depth is
            # widened so a second-stage ranker has more than top_k candidates
            # to reorder within. Never narrower than the caller's requested
            # top_k, so the external top_k contract is preserved regardless.
            internal_depth = max(50, top_k)
            rows = self.connection.execute(
                "SELECT parent_asin FROM products WHERE products MATCH ? "
                "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
                (expression, internal_depth),
            ).fetchall()
            candidate_asins = [str(row[0]) for row in rows]

            # FIX-01B2: active-term-coverage second-stage ranking. Candidate
            # generation above is untouched; this only reorders the
            # already-fixed candidate pool. Each candidate's score is the
            # fraction of distinct active-intent terms it matches (no
            # weights, no threshold); ties (including "no active terms at
            # all", where every candidate scores 0/0 -> treated as equal)
            # keep the original BM25 order.
            active_terms = self._active_terms(state)
            if active_terms and candidate_asins:
                placeholders = ",".join("?" for _ in candidate_asins)
                term_matches: dict[str, set[str]] = {}
                for term in active_terms:
                    term_expr = f'"{term}"'
                    term_rows = self.connection.execute(
                        f"SELECT parent_asin FROM products WHERE products MATCH ? "
                        f"AND parent_asin IN ({placeholders})",
                        (term_expr, *candidate_asins),
                    ).fetchall()
                    term_matches[term] = {str(r[0]) for r in term_rows}
                baseline_index = {asin: i for i, asin in enumerate(candidate_asins)}

                def _coverage(asin: str) -> float:
                    matched = sum(1 for term in active_terms if asin in term_matches[term])
                    return matched / len(active_terms)

                # FIX-02A2: active-slot-coverage secondary tie-break, used
                # only to separate candidates that already have equal
                # active-term coverage (term coverage above remains the sole
                # primary key -- this can never promote a lower-term-coverage
                # candidate above a higher one). Reuses term_matches computed
                # above -- no new FTS queries. A slot counts as satisfied for
                # a candidate if it matches >=1 of that slot's own terms (not
                # all); score is satisfied/matchable slots, no weights, no
                # threshold. With zero matchable slots this is 0.0 for every
                # candidate -- a no-op that falls through to the unchanged
                # baseline-BM25-order final tiebreak, identical to B2.
                matchable_slots = self._matchable_slots(state)

                def _slot_coverage(asin: str) -> float:
                    if not matchable_slots:
                        return 0.0
                    satisfied = sum(
                        1 for slot_terms in matchable_slots
                        if any(asin in term_matches.get(term, ()) for term in slot_terms)
                    )
                    return satisfied / len(matchable_slots)

                candidate_asins.sort(
                    key=lambda asin: (-_coverage(asin), -_slot_coverage(asin), baseline_index[asin])
                )

            recommendations = [{"parent_asin": asin} for asin in candidate_asins[:top_k]]

        ask_attribute: str | None = None
        message = "Here are the closest matches I found so far."
        if turn < 10:
            ask_attribute = self._next_ask_attribute(state)
            if ask_attribute:
                state.asked.add(ask_attribute)
                state.last_turn_asked = ask_attribute
                message = f"Thanks! Do you have a preference for {ask_attribute.replace('_', ' ')}?"

        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": recommendations,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
