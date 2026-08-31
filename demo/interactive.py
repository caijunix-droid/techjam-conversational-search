"""
Interactive demo for the TechJam Shopping Copilot agent.

Unlike the automated evaluator (which uses a SCRIPTED fake customer to
grade the agent 200 times for scoring), THIS script lets a real human type
free-form messages and see the actual agent respond live -- same agent.py,
same brain, just a real conversation instead of a scripted one.

Extra features (demo-only, do not affect scoring):
  - Type a bare number matching something in the list to "select" it.
  - Type 'show more' / 'more' / 'see all' to reveal the rest of the
    current list without spending a turn.

Usage (from the project root):
    python -m demo.interactive
"""
from __future__ import annotations
import json
import sys
import uuid
from pathlib import Path

from starter.agent import Agent

CATALOG_PATH = "data/catalog.jsonl"
SHOW_MORE_PHRASES = {"show more", "more", "see all", "see more", "show all", "list all", "full list"}


def load_titles(catalog_path: str) -> dict[str, dict]:
    """Load parent_asin -> {title, price} so we can show human-readable
    product names instead of raw ASIN codes."""
    lookup: dict[str, dict] = {}
    with Path(catalog_path).open(encoding="utf-8") as handle:
        for line in handle:
            product = json.loads(line)
            lookup[str(product["parent_asin"])] = {
                "title": product.get("title", "(no title)"),
                "price": product.get("price"),
            }
    return lookup


def format_item(index: int, asin: str, titles: dict[str, dict]) -> str:
    info = titles.get(asin, {})
    title = info.get("title", "(unknown product)")
    price = info.get("price")
    price_str = f"  ${price}" if price is not None else ""
    return f"   {index}. {title}{price_str}"


def print_recommendations(recs: list[dict], titles: dict[str, dict], limit: int) -> None:
    if not recs:
        print("   (no recommendations yet)")
        return
    for i, item in enumerate(recs[:limit], start=1):
        print(format_item(i, item.get("parent_asin", "?"), titles))
    if len(recs) > limit:
        print(f"   ...and {len(recs) - limit} more (type 'show more' to see them, or a number to pick one)")


def main() -> None:
    print("Loading catalog and building search index...")
    agent = Agent(CATALOG_PATH)
    titles = load_titles(CATALOG_PATH)
    print(f"Ready. Loaded {len(titles)} products.\n")

    session_id = f"demo_{uuid.uuid4().hex[:8]}"
    agent.reset(session_id, {
        "purchase_frequency": "a few prior purchases",
        "average_prior_rating": None,
        "rating_style": "neutral",
        "preference_tags": [],
        "summary": "Live demo session.",
    })

    print("=" * 60)
    print("  Shopping Copilot -- live demo (type 'quit' to exit)")
    print("=" * 60)
    print("Tell me what you're looking for, e.g. 'I want a black hoodie'")
    print("Tip: once you see a list, type a number to pick an item, or 'show more' to see the rest.\n")

    turn = 1
    last_recommendations: list[dict] = []  # full list from the most recent search

    while turn <= 10:
        try:
            user_message = input(f"You (turn {turn}): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEnding demo.")
            break
        if user_message.lower() in ("quit", "exit"):
            print("Ending demo.")
            break
        if not user_message:
            continue

        # --- "show more": local-only, doesn't touch the agent or spend a turn ---
        if user_message.lower() in SHOW_MORE_PHRASES:
            if not last_recommendations:
                print("\n(No results yet to show more of -- ask for something first.)\n")
                continue
            print(f"\nHere's the full list ({len(last_recommendations)} total):")
            for i, item in enumerate(last_recommendations, start=1):
                print(format_item(i, item.get("parent_asin", "?"), titles))
            print()
            continue

        # --- number selection: local-only, doesn't touch the agent or spend a turn ---
        # Only treated as a "pick item N" selection when the number is
        # actually IN RANGE of the current list. An out-of-range number
        # (e.g. "100" when only 10 items are shown) is almost certainly
        # answering a real question instead (like budget), not trying to
        # select item #100 -- so it falls through to the agent as a normal
        # message rather than erroring and wasting the turn.
        if user_message.isdigit() and last_recommendations:
            pick = int(user_message)
            if 1 <= pick <= len(last_recommendations):
                asin = last_recommendations[pick - 1].get("parent_asin", "?")
                info = titles.get(asin, {})
                title = info.get("title", "(unknown product)")
                price = info.get("price")
                price_str = f" (${price})" if price is not None else ""
                print(f"\nGreat choice! You selected: {title}{price_str}")
                print("(Type another message to keep refining, or 'quit' to end.)\n")
                continue
            # else: out of range -- fall through to the normal agent path below,
            # since this is more likely a real answer (e.g. a budget number)
            # than a selection attempt.

        # --- normal turn: goes to the real agent ---
        response = agent.respond(session_id, user_message, turn, top_k=10)
        last_recommendations = response.get("recommendations", [])

        print(f"\nAgent: {response['message']}")
        if response.get("ask_attribute"):
            print(f"       (asking about: {response['ask_attribute']})")
        print("   Top matches:")
        known = agent.known_slot_count(session_id)
        display_limit = max(3, 9 - 2 * known)
        print_recommendations(last_recommendations, titles, limit=display_limit)
        print()

        turn += 1

    if turn > 10:
        print("Reached the 10-turn limit for this demo session.")


if __name__ == "__main__":
    main()
