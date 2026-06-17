# FitFindr 🛍️

A multi-tool AI agent that helps you find secondhand clothing and figure out how to wear it. From one natural-language request, FitFindr searches a mock listings dataset, suggests an outfit built around the top find and your existing wardrobe, and writes a shareable "fit card" caption — handling failures gracefully at every step.

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (CMD)
# .venv\Scripts\Activate.ps1    # Windows (PowerShell)
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

Create a `.env` in the repo root (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

**Run the web app:**
```bash
python app.py
```
Then open the URL shown in your terminal (usually http://localhost:7860).

**Run the CLI demo / tests:**
```bash
python agent.py          # happy path + no-results branch
pytest tests/            # all tool tests
```
> On Windows, if the console errors on emoji in fit cards, set `set PYTHONIOENCODING=utf-8` (CMD) or `$env:PYTHONIOENCODING="utf-8"` (PowerShell) first. The Gradio web UI is unaffected.

---

## Tool Inventory

These signatures exactly match `tools.py`.

### 1. `search_listings(description, size, max_price) -> list[dict]`
- **Inputs:**
  - `description` (str): free-text keywords, e.g. `"vintage graphic tee"`.
  - `size` (str | None): size filter; case-insensitive **substring** match (so `"M"` matches `"S/M"`). `None` skips the filter.
  - `max_price` (float | None): inclusive price ceiling. `None` skips the filter.
- **Output:** a `list[dict]` of full listing dicts (`id, title, description, category, style_tags, size, condition, price, colors, brand, platform`), ranked by keyword-overlap relevance (best first). `[]` when nothing matches.
- **Purpose:** find candidate items to consider buying.

### 2. `suggest_outfit(new_item, wardrobe) -> str`
- **Inputs:**
  - `new_item` (dict): the listing dict chosen by the agent.
  - `wardrobe` (dict): `{"items": [...]}` — the user's closet (may be empty).
- **Output:** a non-empty `str` with 1–2 outfit ideas (names specific wardrobe pieces when available; general advice when the wardrobe is empty).
- **Purpose:** show the user how the item fits into what they already own.

### 3. `create_fit_card(outfit, new_item) -> str`
- **Inputs:**
  - `outfit` (str): the outfit text from `suggest_outfit`.
  - `new_item` (dict): the listing dict (for name, price, platform).
- **Output:** a 2–4 sentence casual caption mentioning item, price, and platform. Uses temperature 1.0 so it varies per call.
- **Purpose:** generate something shareable for an OOTD post.

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in `agent.py` is a linear pipeline with **one decision branch**, not a fixed "always run all three tools" sequence:

1. **Parse** the query with regex into `description`, `size`, `max_price` (`_parse_query`). No LLM — fast and deterministic.
2. **Search:** call `search_listings(...)`.
3. **Branch on the result:**
   - If `search_results == []` → set `session["error"]` with a specific, actionable message and **`return` early**. `suggest_outfit` and `create_fit_card` are never called, so `fit_card` stays `None`.
   - Otherwise → `selected_item = search_results[0]` and continue.
4. **Suggest outfit** using `selected_item` + `wardrobe`.
5. **Create fit card** from the outfit suggestion + `selected_item`.
6. **Return** the session.

The behaviour visibly differs by input: an impossible query exits at step 3; a normal query runs all three tools.

---

## State Management

A single `session` dict (created by `_new_session`) is the source of truth for one interaction. Each tool writes its output into the session; the next tool reads from it — the user never re-enters anything.

| Field | Set by | Consumed by |
|-------|--------|-------------|
| `parsed` | `_parse_query` | `search_listings` |
| `search_results` | `search_listings` | branch decision |
| `selected_item` | `search_results[0]` | `suggest_outfit`, `create_fit_card` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | UI |
| `error` | early-exit branch | UI (other fields stay `None`) |

The item found in step 2 flows into the outfit step; the outfit text flows into the fit-card step — all through the session, with no re-prompting.

---

## Error Handling and Fail Points

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No results match | Returns `[]`; the loop sets `session["error"]` and stops before the later tools. |
| `suggest_outfit` | Empty wardrobe (or LLM error) | Switches to a general-styling-advice prompt; on an API error, returns a safe templated tip. Never crashes. |
| `create_fit_card` | Missing/empty outfit (or LLM error) | Returns `"Can't write a fit card without an outfit suggestion."`; on an API error, returns a template caption from the item fields. |

**Concrete example (from testing):** running the impossible query `"designer ballgown size XXS under $5"` produced:

```
error: No listings matched 'designer ballgown' with size XXS and under $5.
       Try removing the size filter, raising your max price, or using broader keywords.
fit_card is None? True
```

The agent told the user exactly what to change and did **not** call `suggest_outfit` with empty input.

---

## Interaction Walkthrough

**User query:** `"looking for a vintage graphic tee under $30"` (Example wardrobe)

**Step 1 — `search_listings`**
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0` (parsed from the query)
- Why: every other tool depends on having a real item to work with.
- Output: a ranked list; top result = **Y2K Baby Tee — Butterfly Print, $18, depop**.

**Step 2 — `suggest_outfit`**
- Input: the selected tee dict + the example wardrobe.
- Why: search succeeded, so the agent moves on to styling it against owned pieces.
- Output: *"Pair the Y2K Baby Tee with your baggy straight-leg jeans and chunky white sneakers... layer the vintage black denim jacket and tuck the front for shape."*

**Step 3 — `create_fit_card`**
- Input: the outfit text + the selected tee dict.
- Why: turn the styled look into something shareable.
- Output: *"just scored this adorable y2k baby tee on depop for $18 and i'm obsessed 🦋 paired it with my baggy jeans and chunky sneakers for that effortless streetwear vibe..."*

**Final output to user:** three panels — listing details, outfit idea, and the fit card caption.

---

## Spec Reflection

**One way `planning.md` helped during implementation:**
Writing the planning loop as explicit numbered steps with the error branch *before* coding meant `run_agent` was almost a direct translation of the spec. I never had to stop and decide "what calls what" mid-implementation — the branch on empty `search_results` and the order of state writes were already settled, which kept the agent from accidentally calling all three tools unconditionally.

**One divergence from the spec, and why:**
The spec said query parsing "can use regex, string splitting, or the LLM." I planned for regex and kept it, but during implementation I added a `_STOPWORDS` set and a `_keywords` helper in `tools.py` that the spec didn't mention — without it, common words like "looking"/"for"/"under" inflated relevance scores and surfaced irrelevant listings. It was a small but necessary addition to make ranking actually relevant.

---

## AI Usage

**1. Implementing `search_listings` (Milestone 3).**
I gave Claude the Tool 1 block from `planning.md` (inputs, return value, failure mode) and asked it to implement the function using `load_listings()`. I directed it to score by keyword overlap and drop score-0 results. What I revised: the first approach scored against raw query words, so stopwords ("for", "under", "looking") polluted matches — I added the `_STOPWORDS`/`_keywords` filter and verified with three queries (normal → results, impossible → `[]`, price-filter → all `price <= max_price`).

**2. Implementing the planning loop (Milestone 4).**
I gave Claude the Architecture diagram plus the Planning Loop and State Management sections and asked it to implement `run_agent()`. I explicitly required it to branch on empty `search_results` and store every result in the session rather than calling all three tools unconditionally. I verified by running `agent.py`: the happy path populated `selected_item → outfit_suggestion → fit_card`, and the no-results query left `fit_card = None` with a specific `error`.

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/                  # listings.json (40 items), wardrobe_schema.json
├── utils/data_loader.py   # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py               # search_listings, suggest_outfit, create_fit_card
├── agent.py               # _parse_query + run_agent planning loop
├── app.py                 # Gradio UI (handle_query)
├── tests/test_tools.py    # pytest: one test per failure mode + happy paths
├── planning.md            # spec written before implementation
└── README.md
```
