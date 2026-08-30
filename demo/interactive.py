"""
Interactive demo for the TechJam Shopping Copilot agent.

Unlike the automated evaluator (which uses a SCRIPTED fake customer to
grade the agent 200 times for scoring), THIS script lets a real human type
free-form messages and see the actual agent respond live -- same agent.py,
same brain, just a real conversation instead of a scripted one.

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


def print_recommendations(recs: list[dict], titles: dict[str, dict], limit: int = 5) -> None:
    if not recs:
        print("   (no recommendations yet)")
        return
    for i, item in enumerate(recs[:limit], start=1):
        asin = item.get("parent_asin", "?")
        info = titles.get(asin, {})
        title = info.get("title", "(unknown product)")
        price = info.get("price")
        price_str = f"  ${price}" if price is not None else ""
        print(f"   {i}. {title}{price_str}")
    if len(recs) > limit:
        print(f"   ...and {len(recs) - limit} more (top {len(recs)} total returned)")


def main() -> None:
    print("Loading catalog and building search index...")
    agent = Agent(CATALOG_PATH)
    titles = load_titles(CATALOG_PATH)
    print(f"Ready. Loaded {len(titles)} products.\n")

    session_id = f"demo_{uuid.uuid4().hex[:8]}"
    # A generic demo profile -- in the real evaluator this comes from the
    # dataset; here we just supply a neutral placeholder since we're not
    # scoring, just demonstrating the conversation.
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
    print("Tell me what you're looking for, e.g. 'I want a black hoodie'\n")

    turn = 1
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

        response = agent.respond(session_id, user_message, turn, top_k=10)

        print(f"\nAgent: {response['message']}")
        if response.get("ask_attribute"):
            print(f"       (asking about: {response['ask_attribute']})")
        print("   Top matches:")
        # Show fewer, more targeted titles the more the agent has learned
        # about this customer -- purely a display choice (doesn't affect
        # the actual search results or scoring, just how many we print).
        known = agent.known_slot_count(session_id)
        display_limit = max(3, 9 - 2 * known)
        print_recommendations(response.get("recommendations", []), titles, limit=display_limit)
        print()

        turn += 1

    if turn > 10:
        print("Reached the 10-turn limit for this demo session.")


if __name__ == "__main__":
    main()
