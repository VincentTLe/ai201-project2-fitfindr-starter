"""Deliberately trigger each failure mode (Milestone 5)."""
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_empty_wardrobe
from agent import run_agent
from utils.data_loader import get_example_wardrobe

print("=== 1. search_listings: zero results ===")
r = search_listings("designer ballgown", size="XXS", max_price=5)
print("returns:", r, "| type:", type(r).__name__)

print("\n=== 1b. full agent on impossible query ===")
s = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
print("error:", s["error"])
print("fit_card is None?", s["fit_card"] is None)

print("\n=== 2. suggest_outfit: empty wardrobe ===")
item = search_listings("vintage graphic tee", None, 50)[0]
out = suggest_outfit(item, get_empty_wardrobe())
print(out)

print("\n=== 3. create_fit_card: empty outfit ===")
print(create_fit_card("", item))
