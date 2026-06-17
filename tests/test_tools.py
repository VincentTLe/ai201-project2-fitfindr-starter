"""
Tests for the three FitFindr tools — one test per failure mode plus happy paths.
Run with:  pytest tests/
"""

import sys
import os

# Make the project root importable when pytest runs from anywhere.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Impossible query → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=40)
    assert all(item["price"] <= 40 for item in results)


def test_search_size_filter_substring():
    # "M" should match listings whose size contains M (e.g. "S/M", "M/L").
    results = search_listings("top", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_ranks_by_relevance():
    results = search_listings("vintage denim jeans", size=None, max_price=None)
    # Top result should clearly be a denim/jeans item.
    assert results, "expected at least one result"
    top = results[0]
    text = (top["title"] + " " + " ".join(top["style_tags"])).lower()
    assert "denim" in text or "jeans" in text


# ── suggest_outfit ─────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str) and len(out.strip()) > 0


def test_suggest_outfit_empty_wardrobe():
    # Empty wardrobe must not crash — returns useful general advice.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str) and len(out.strip()) > 0


# ── create_fit_card ────────────────────────────────────────────────────────────

def test_fit_card_empty_outfit_returns_message():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert "without an outfit" in card.lower()


def test_fit_card_happy_path():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("Pair with baggy jeans and chunky sneakers.", item)
    assert isinstance(card, str) and len(card.strip()) > 0
