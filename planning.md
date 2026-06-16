# FitFindr — planning.md

> Completed before writing implementation code.
> This spec + the agent diagram are what I use to direct AI tools to generate the implementation.

---

## What FitFindr does (2–3 sentences)

FitFindr is a multi-tool agent that helps a user find a secondhand clothing item and figure out how to wear it. From one natural-language request it (1) searches the mock listings dataset, (2) suggests an outfit that combines the top find with the user's existing wardrobe, and (3) writes a shareable "fit card" caption. The search step triggers everything else: if it returns no listings, the agent stops early and tells the user what to change instead of calling the later tools with empty input.

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset and returns the items that best match a free-text description, optionally filtered by size and a maximum price. Results are ranked so the most relevant item is first.

**Input parameters:**
- `description` (str): free-text keywords describing the wanted item, e.g. `"vintage graphic tee"`. Tokenised into lowercase keywords for matching.
- `size` (str | None): a size string to filter on, e.g. `"M"`. Matching is case-insensitive **substring** matching against the listing's `size` field (so `"M"` matches `"S/M"` and `"M/L"`). `None` = skip size filtering.
- `max_price` (float | None): inclusive price ceiling. A listing passes if `price <= max_price`. `None` = skip price filtering.

**What it returns:**
A `list[dict]` of full listing dicts (each with `id, title, description, category, style_tags, size, condition, price, colors, brand, platform`), sorted by a relevance score (highest first). The score = number of description keywords that appear in the listing's `title + description + style_tags + category + colors`. Listings with a score of 0 are dropped. Returns `[]` (empty list, never an exception) when nothing matches.

**What happens if it fails or returns nothing:**
Returns `[]`. The planning loop detects the empty list, sets `session["error"]` to a specific message ("No listings matched 'X' under $Y in size Z — try removing the size filter, raising the price, or using broader keywords."), and returns early **without** calling `suggest_outfit`.

---

### Tool 2: suggest_outfit

**What it does:**
Given the selected item and the user's wardrobe, asks the LLM to propose 1–2 complete, wearable outfit combinations and how to style them.

**Input parameters:**
- `new_item` (dict): the listing dict chosen by the agent (the top search result).
- `wardrobe` (dict): a wardrobe dict shaped `{"items": [ {id, name, category, colors, style_tags, notes}, ... ]}`. The list may be empty.

**What it returns:**
A non-empty `str` describing 1–2 outfits in natural language (which wardrobe pieces to pair, plus a styling tip). When the wardrobe has items, it names specific wardrobe pieces; when empty, it gives general styling advice for the item.

**What happens if it fails or returns nothing:**
- Empty wardrobe (`wardrobe["items"] == []`): a different prompt is used asking for general styling ideas (what kinds of pieces pair well, what vibe it suits) — still returns a useful string, never crashes.
- LLM call raises (network/API error): caught; returns a plain-language fallback string describing the item and a generic styling tip so the pipeline continues.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion + item details into a short, casual, shareable caption — the kind someone would post with an OOTD photo.

**Input parameters:**
- `outfit` (str): the outfit suggestion text from `suggest_outfit`.
- `new_item` (dict): the listing dict for the thrifted item (for name, price, platform).

**What it returns:**
A 2–4 sentence `str` caption that mentions the item name, price, and platform naturally (once each), captures the outfit vibe, and reads like a real post. Uses a higher LLM temperature so different inputs produce different captions.

**What happens if it fails or returns nothing:**
- Empty / whitespace-only `outfit`: returns a descriptive error string (`"Can't write a fit card without an outfit suggestion."`) — no exception.
- LLM call raises: caught; returns a simple template caption built from the item fields so the user still gets something shareable.

---

### Additional Tools (if any)

None for the required build. (Stretch: a `compare_price` tool — see Stretch section before starting.)

---

## Planning Loop

**How the agent decides which tool to call next:**

The loop is a linear pipeline with **one branch** that depends on what `search_listings` returns. It is not a fixed "always call all three" sequence — the second and third tools only run if the first produced a usable item.

1. Initialise `session` with `_new_session(query, wardrobe)`.
2. **Parse** the query into `description`, `size`, `max_price` (regex for price like `under $30` / `$30` and a size token like `size M`; the leftover text is the description). Store in `session["parsed"]`.
3. **search_listings(description, size, max_price)** → store in `session["search_results"]`.
   - **Branch:** `if not search_results:` set `session["error"]` to a specific, actionable message and **`return session` early.** (fit_card stays `None`.)
4. Else `session["selected_item"] = search_results[0]` (top-ranked).
5. **suggest_outfit(selected_item, wardrobe)** → store in `session["outfit_suggestion"]`.
6. **create_fit_card(outfit_suggestion, selected_item)** → store in `session["fit_card"]`.
7. `return session`.

The loop "knows it's done" when `fit_card` is set (success) or when `error` is set (early exit). Behaviour visibly changes with input: an impossible query exits at step 3; a normal query runs all three tools.

---

## State Management

**How information flows between tools:**

A single `session` dict is the source of truth for one interaction. Each tool writes its output into the session, and the next tool reads from the session — the user never re-enters anything.

- `query` → parsed into `parsed = {description, size, max_price}`
- `search_results` ← `search_listings(...)`
- `selected_item` ← `search_results[0]` → **passed into** `suggest_outfit`
- `outfit_suggestion` ← `suggest_outfit(selected_item, wardrobe)` → **passed into** `create_fit_card`
- `fit_card` ← `create_fit_card(outfit_suggestion, selected_item)`
- `error` → set only on early exit; when set, downstream fields stay `None`

So the item found in step 3 flows into step 5, and the outfit text from step 5 flows into step 6 — all via the session dict, no re-prompting.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Returns `[]`; planning loop sets `session["error"]`: *"No listings matched '<desc>'<size/price filters> — try removing the size filter, raising your max price, or using broader keywords."* and stops before the next tools. |
| suggest_outfit | Wardrobe is empty | Detects `items == []`, switches to a "general styling advice" prompt and returns useful, item-specific advice (no crash). If the LLM call errors, returns a safe templated styling tip. |
| create_fit_card | Outfit input missing/incomplete | Guards empty/whitespace `outfit` → returns *"Can't write a fit card without an outfit suggestion."* If the LLM call errors, returns a template caption built from item name/price/platform. |

---

## Architecture

```
User query + wardrobe choice
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ Planning Loop (run_agent)                                    │
│                                                              │
│  parse query ──► Session: parsed{description,size,max_price} │
│        │                                                     │
│        ▼                                                     │
│  search_listings(description, size, max_price)               │
│        │ results == []                                       │
│        ├──► Session: error="No listings found..." ──► return │  ◄── ERROR BRANCH
│        │                                                     │
│        │ results == [item, ...]                              │
│        ▼                                                     │
│  Session: selected_item = results[0]                         │
│        │                                                     │
│        ▼                                                     │
│  suggest_outfit(selected_item, wardrobe)                     │
│        │   (empty wardrobe ──► general-advice prompt)        │
│        ▼                                                     │
│  Session: outfit_suggestion = "..."                          │
│        │                                                     │
│        ▼                                                     │
│  create_fit_card(outfit_suggestion, selected_item)           │
│        │   (empty outfit ──► error string)                   │
│        ▼                                                     │
│  Session: fit_card = "..."                                   │
│        │                                                     │
└────────┼─────────────────────────────────────────────────────┘
         ▼
   Return session  ──►  app.py maps to 3 panels
                        (listing / outfit / fit card)
```

State store = the `session` dict, read+written at every step.

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**
I'll use Claude (Claude Code). For each tool I paste that tool's block from this file (inputs, return value, failure mode) and ask for the function in `tools.py`.
- `search_listings`: I'll require it to use `load_listings()` (not re-read files), filter by all three params, score by keyword overlap, drop score-0, and return `[]` on no match. Verify: run 3 queries — a normal one (returns results), an impossible one (returns `[]`), and a price-filter one (every result `price <= max_price`).
- `suggest_outfit` / `create_fit_card`: I'll require the empty-wardrobe branch and the empty-outfit guard, and a try/except around the Groq call. Verify by calling each directly with example wardrobe, empty wardrobe, and empty outfit, plus running `create_fit_card` twice to confirm output varies.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the Architecture diagram + the Planning Loop and State Management sections, and ask it to implement `run_agent()` matching the numbered steps. Verify: it must branch on the empty `search_results` (not call all three unconditionally), store each result in the session, and the no-results query must leave `fit_card = None` with `error` set.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse:** Extract `max_price = 30.0` (from "under $30"), `size = None` (none given), `description = "vintage graphic tee"`. Stored in `session["parsed"]`.

**Step 2 — Search:** `search_listings("vintage graphic tee", None, 30.0)` filters to price ≤ 30 and scores by keyword overlap. Top matches include *Graphic Tee — 2003 Tour Bootleg ($24)*, *Y2K Baby Tee ($18)*, *Vintage Band Tee ($19)*. `session["search_results"]` = that ranked list; `session["selected_item"]` = the top one.

**Step 3 — Suggest outfit:** `suggest_outfit(selected_item, example_wardrobe)` → e.g. *"Pair the bootleg tee with your baggy straight-leg jeans and chunky white sneakers for a 90s streetwear look; layer the vintage black denim jacket and tuck the front hem for shape."* Stored in `session["outfit_suggestion"]`.

**Step 4 — Fit card:** `create_fit_card(outfit_suggestion, selected_item)` → e.g. *"thrifted this bootleg graphic tee off depop for $24 and it was MADE for my baggy jeans 🖤 layered the denim jacket over for that 90s look — full fit in my stories."* Stored in `session["fit_card"]`.

**Final output to user:** Three panels — the listing details (title, price, platform, condition), the outfit idea, and the fit card caption.

---

## Stretch Features (update before starting each)

- [ ] Price comparison tool — `compare_price(item)` vs same-category listings.
- [ ] Retry with loosened constraints when `search_listings` returns `[]`.
- [ ] Style profile memory across sessions.
