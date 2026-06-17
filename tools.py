"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

LLM_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_llm(prompt: str, temperature: float = 0.7) -> str:
    """Send a single user prompt to Groq and return the text response."""
    client = _get_groq_client()
    completion = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return completion.choices[0].message.content.strip()


# Words that carry no matching signal — ignored when scoring relevance.
_STOPWORDS = {
    "a", "an", "the", "for", "with", "and", "or", "of", "to", "in", "on",
    "i", "im", "looking", "want", "need", "some", "thrift", "thrifted",
    "secondhand", "find", "piece", "under", "size",
}


def _keywords(text: str) -> list[str]:
    """Lowercase, strip punctuation, drop stopwords — used for scoring."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    query_keywords = _keywords(description)

    scored = []
    for item in listings:
        # 1. Price filter (inclusive).
        if max_price is not None and item["price"] > max_price:
            continue

        # 2. Size filter — case-insensitive substring so "M" matches "S/M".
        if size is not None and size.strip():
            if size.strip().lower() not in item["size"].lower():
                continue

        # 3. Score by keyword overlap against the searchable text fields.
        haystack = " ".join([
            item["title"],
            item["description"],
            " ".join(item["style_tags"]),
            item["category"],
            " ".join(item["colors"]),
        ]).lower()

        score = sum(1 for kw in query_keywords if kw in haystack)

        # 4. Drop listings with no relevant match.
        if score > 0:
            scored.append((score, item))

    # 5. Sort by score, highest first.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item['title']} (category: {new_item['category']}, "
        f"colors: {', '.join(new_item['colors'])}, "
        f"style: {', '.join(new_item['style_tags'])})"
    )

    items = wardrobe.get("items", []) if wardrobe else []

    if not items:
        # Empty wardrobe → general styling advice (no specific pieces to name).
        prompt = (
            "You are a thoughtful personal stylist. The user just found this "
            f"secondhand item:\n  {item_desc}\n\n"
            "They have not entered a wardrobe yet. In 3-4 sentences, suggest one "
            "or two complete outfit ideas built around this item — describe the "
            "kinds of pieces (bottoms, shoes, layers) that pair well and the vibe "
            "it suits. Be specific and practical, not generic."
        )
    else:
        wardrobe_lines = "\n".join(
            f"  - {it['name']} ({it['category']}; "
            f"{', '.join(it.get('style_tags', []))})"
            for it in items
        )
        prompt = (
            "You are a thoughtful personal stylist. The user just found this "
            f"secondhand item:\n  {item_desc}\n\n"
            f"Their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair this new item with specific "
            "pieces from their wardrobe (name the pieces). Add a short styling tip "
            "(how to layer, tuck, roll, etc.). Keep it to 3-5 sentences, casual and "
            "specific."
        )

    try:
        return _call_llm(prompt, temperature=0.7)
    except Exception as exc:  # network/API failure — degrade gracefully
        return (
            f"Style the {new_item['title'].split('—')[0].strip()} as the focal "
            f"piece and keep the rest simple in neutral tones. "
            f"(Styling service was unavailable: {exc})"
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty or whitespace-only outfit.
    if not outfit or not outfit.strip():
        return "Can't write a fit card without an outfit suggestion."

    name = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "thrift")

    prompt = (
        "Write a short, casual OOTD-style caption (2-4 sentences) for a "
        "thrifted-fashion social post. Make it sound like a real person's "
        "Instagram/TikTok caption, NOT a product description.\n\n"
        f"Item: {name}\n"
        f"Price: ${price}\n"
        f"Platform: {platform}\n"
        f"The outfit: {outfit}\n\n"
        "Mention the item, price, and platform naturally (once each). Capture the "
        "outfit's vibe in specific terms. Lowercase casual tone and a tasteful "
        "emoji or two are welcome. Return only the caption."
    )

    # 2 & 3. Higher temperature → varied captions for varied inputs.
    try:
        return _call_llm(prompt, temperature=1.0)
    except Exception:
        # Fallback template so the user still gets something shareable.
        return (
            f"thrifted this {name.split('—')[0].strip().lower()} off {platform} "
            f"for ${price} and i'm obsessed ✨ styled it exactly how i wanted — "
            f"full look soon!"
        )
