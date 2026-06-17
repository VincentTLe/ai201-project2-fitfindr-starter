"""
Tests for the planning loop and the stretch retry-with-fallback logic.
Run with:  pytest tests/
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent import _parse_query, _search_with_fallback, run_agent
from utils.data_loader import get_example_wardrobe


# ── query parsing ──────────────────────────────────────────────────────────────

def test_parse_extracts_price_and_size():
    p = _parse_query("vintage graphic tee under $30 size M")
    assert p["max_price"] == 30.0
    assert p["size"] == "M"
    assert "graphic" in p["description"] and "$" not in p["description"]


# ── retry / fallback (no LLM needed) ───────────────────────────────────────────

def test_fallback_relaxes_impossible_size():
    # No listing's size string contains "XXL", so attempt 1 is empty;
    # dropping the size filter should surface tees, with an explanatory note.
    parsed = {"description": "vintage graphic tee", "size": "XXL", "max_price": None}
    results, note = _search_with_fallback(parsed)
    assert len(results) > 0
    assert note is not None and "removed the size filter" in note


def test_fallback_no_note_when_first_attempt_works():
    parsed = {"description": "vintage graphic tee", "size": None, "max_price": 50}
    results, note = _search_with_fallback(parsed)
    assert len(results) > 0
    assert note is None


def test_fallback_truly_impossible_returns_empty():
    parsed = {"description": "designer ballgown", "size": "XXS", "max_price": 5}
    results, note = _search_with_fallback(parsed)
    assert results == []
    assert note is None


# ── full planning loop with retry (calls LLM) ──────────────────────────────────

def test_run_agent_retry_sets_note_and_completes():
    session = run_agent("vintage graphic tee size XXL", get_example_wardrobe())
    assert session["error"] is None
    assert session["search_note"] is not None
    assert session["fit_card"]  # pipeline completed after the retry


def test_run_agent_no_results_still_errors():
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert session["error"] is not None
    assert session["fit_card"] is None
