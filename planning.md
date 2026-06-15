# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Filters the mock listings dataset by optional size and price ceiling, then scores each remaining listing by counting how many words from the user's description appear in that listing's title, style_tags, and description fields. Returns all listings with a non-zero score, sorted highest score first.

**Input parameters:**
- `description` (str): Free-text keywords the user typed (e.g., "vintage graphic tee"). The tool splits this into individual words and counts overlaps against each listing's title, style_tags list, and description field. More overlapping words = higher score.
- `size` (str | None): Size string to filter by (e.g., "M", "S/M"). Matched case-insensitively using substring matching against the listing's size field — so "M" would match "S/M" or "XL (oversized M)". Pass `None` to skip size filtering entirely.
- `max_price` (float | None): Maximum price the user will pay, inclusive. Any listing with `price > max_price` is excluded before scoring. Pass `None` to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score, highest first. Returns an empty list if nothing matches — never raises an exception. Each dict contains:
- `id` (str): unique listing identifier, e.g. `"lst_002"`
- `title` (str): short name of the item, e.g. `"Y2K Baby Tee — Butterfly Print"`
- `description` (str): full text description of the item
- `category` (str): one of `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`
- `style_tags` (list[str]): style descriptors, e.g. `["vintage", "graphic tee", "y2k"]`
- `size` (str): size label as listed, e.g. `"S/M"`, `"W30 L30"`, `"XL (oversized)"`
- `condition` (str): one of `excellent`, `good`, `fair`
- `price` (float): asking price in USD, e.g. `18.0`
- `colors` (list[str]): colors present on the item, e.g. `["white", "pink", "purple"]`
- `brand` (str | None): brand name if known, or `null`
- `platform` (str): where the listing lives, e.g. `"depop"`, `"thredUp"`

**What happens if it fails or returns nothing:**
The agent stops the chain immediately and does not call `suggest_outfit`. It tells the user: "No listings matched your search — try broader keywords or remove the size or price filter."

---

### Tool 2: suggest_outfit

**What it does:**
Sends the new thrifted item and the user's wardrobe to an LLM (via Groq) and asks it to suggest 1–2 complete outfit combinations using the item and named pieces from the wardrobe. If the wardrobe is empty, asks the LLM for general styling advice about the item instead.

**Input parameters:**
- `new_item` (dict): The top listing dict from `search_listings`. The prompt uses: `title`, `colors` (list[str]), `style_tags` (list[str]), `category`, `condition`, `price`, `platform`.
- `wardrobe` (dict): A wardrobe dict with a single key `'items'` containing a list of wardrobe item dicts. Each wardrobe item has: `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), `notes` (str | None). The `items` list may be empty — the tool must handle both cases.

**What it returns:**
A non-empty string (1–3 paragraphs). If the wardrobe has items: names 1–2 specific outfit combinations using actual wardrobe pieces by name (e.g., "pair it with your baggy straight-leg jeans and chunky white sneakers"). If the wardrobe is empty: describes what types of pieces complement this item and what style vibe it fits.

**What happens if it fails or returns nothing:**
If the LLM returns an empty or whitespace-only response, the agent returns the string `"Couldn't generate outfit suggestions — please try again."` and does not call `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Sends the outfit suggestion and item details to an LLM (via Groq) and asks it to write a 2–4 sentence caption in the style of a real OOTD social media post. Uses a higher LLM temperature (0.9+) so each caption sounds different.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. Must be non-empty — the tool checks this before calling the LLM and returns an error string immediately if it's empty or whitespace-only.
- `new_item` (dict): The listing dict for the thrifted item. Used to pull `title` (item name), `price` (float), and `platform` (str) into the caption naturally.

**What it returns:**
A 2–4 sentence string formatted as an Instagram/TikTok-style caption. The caption:
- Mentions the item name, price, and platform once each, woven in naturally (not listed like bullet points)
- Describes the outfit vibe in specific terms (not generic like "cute look")
- Sounds casual and personal, like a real person posted it — not a product description

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, returns the string `"Cannot write a fit card without outfit details."` without calling the LLM. Does not raise an exception.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

This agent runs a fixed linear pipeline. The same three tools always run in the same order. Before calling the next tool, the loop checks that the previous one returned something useful. If it did not, the loop sets an error message and returns early.

**Step 1 — Parse the query**
Extract three values from the raw query string using regex:
- `description`: the query with price/size phrases stripped out (e.g., `"vintage graphic tee"`)
- `size`: look for patterns like `"size M"`, `"in a S"`, `"size S/M"` — extract the size token or set `None`
- `max_price`: look for patterns like `"under $30"`, `"less than $30"`, `"$30 or less"` — extract as `float` or set `None`

Store all three in `session["parsed"]`.

**Step 2 — Call `search_listings`**
Call `search_listings(description, size, max_price)` using the parsed values. Store the result in `session["search_results"]`.

- If `session["search_results"]` is an empty list → set `session["error"] = "No listings matched your search. Try broader keywords or remove the size or price filter."` → return `session` immediately. Do not proceed.
- If not empty → set `session["selected_item"] = session["search_results"][0]` (the highest-scored result) → continue to Step 3.

**Step 3 — Call `suggest_outfit`**
Call `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`. Store the result in `session["outfit_suggestion"]`.

- If `session["outfit_suggestion"]` is empty or whitespace-only → set `session["error"] = "Couldn't generate outfit suggestions. Please try again."` → return `session` immediately. Do not proceed.
- If not empty → continue to Step 4.

**Step 4 — Call `create_fit_card`**
Call `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`. Store the result in `session["fit_card"]`.

**Step 5 — Return**
Return `session`. The caller checks `session["error"]` first — if it is `None`, the run succeeded and `session["fit_card"]` holds the final output. If it is not `None`, the run ended early.

---

## State Management

**How does information from one tool get passed to the next?**

All state for a single interaction lives in one **session dict**, created by `_new_session(query, wardrobe)` at the start of `run_agent`. This dict is the single source of truth: every tool reads its inputs from the session and writes its output back into the session. Nothing is passed between tools through globals or side channels — the session dict *is* the channel.

**What is tracked:** the original `query`, the `parsed` parameters (`description`, `size`, `max_price`), the `wardrobe`, and one field per tool output — `search_results`, `selected_item`, `outfit_suggestion`, `fit_card` — plus an `error` field for early exits.

**How it's passed:** the planning loop is the only thing that reads from and writes to the session. After each tool call it stores the result in the matching field, then reads that field back out to build the next tool's arguments. For example, `search_listings`'s result is stored in `session["search_results"]`; the loop selects `results[0]` into `session["selected_item"]`; and `suggest_outfit` is then called with `new_item=session["selected_item"]`. (See the field ownership table under Architecture for who writes and reads each field.)

**Why this shape:** every output field is initialized to a neutral value (`None` or `[]`) in `_new_session()`, so the caller can safely inspect the session no matter where the run stopped. The caller (and the Gradio `handle_query` in `app.py`) checks `session["error"]` first; if it is `None`, the run succeeded and the output fields are populated; if it is set, the run ended early and the downstream fields are still their neutral defaults.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No results match the query | Sets `session["error"]` to `"No listings matched '[description]'."` If `size` was provided, appends `"Try removing the size filter."` If `max_price` was provided, appends `"Try raising your price ceiling or removing it."` Chain stops. `suggest_outfit` is never called with an empty item. |
| `suggest_outfit` | Wardrobe is empty | Not a hard failure. The chain continues. The tool detects `wardrobe["items"] == []` and switches to a general-advice prompt. It returns something like: `"This item pairs well with wide-leg trousers or baggy denim. The vintage graphic print suits a Y2K or streetwear vibe."` `create_fit_card` is still called with that advice. |
| `create_fit_card` | `outfit` string is empty or whitespace-only | Returns the string `"Cannot write a fit card without outfit details."` immediately, without calling the LLM. The agent surfaces this message to the user and notes that the outfit step may need to be retried. |

### Milestone 5 — Failure modes verified

Each failure mode above was deliberately triggered from the terminal to confirm the agent recovers gracefully (returns a specific message instead of raising):

| Failure triggered | Input used | Result | Raised? |
|-------------------|-----------|--------|---------|
| `search_listings` returns zero results | `search_listings('designer ballgown', size='XXS', max_price=5)` | `[]` → agent sets `session["error"]` with adaptive recovery hints; `outfit_suggestion` and `fit_card` stay `None` | No |
| `suggest_outfit` with empty wardrobe | top result + `get_empty_wardrobe()` | Full general-styling string (no wardrobe pieces referenced); chain continues to `create_fit_card` | No |
| `create_fit_card` with empty outfit | `create_fit_card('', listing)` | `"Cannot write a fit card without outfit details."` (returned before any LLM call) | No |

The `search_listings` failure was traced through the full agent: the empty-result gate fires, so `suggest_outfit` and `create_fit_card` never run on empty input. Demo recording of at least one triggered failure to follow.

---

## Architecture

```
User Input: "vintage graphic tee under $30"
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Planning Loop — run_agent(query, wardrobe)                     │
│                                                                 │
│  Parse query with regex                                         │
│      session["parsed"] = {                                      │
│          description: "vintage graphic tee",                    │
│          size:        None,                                     │
│          max_price:   30.0                                      │
│      }                                                          │
│       │                                                         │
│       ▼                                                         │
│  search_listings(description, size, max_price)                  │
│       │                                                         │
│       ├── results == [] ──► session["error"] = "No listings..." │
│       │                             │                           │
│       │                             └──────────────────────────►│ return session ✗
│       │                                                         │
│       └── results != []                                         │
│               │                                                 │
│               ▼                                                 │
│       session["search_results"] = [listing_dict, ...]           │
│       session["selected_item"]  = results[0]  (top score)       │
│               │                                                 │
│               ▼                                                 │
│  suggest_outfit(selected_item, wardrobe)                        │
│       │                                                         │
│       ├── suggestion == "" ──► session["error"] = "Couldn't..." │
│       │                                │                        │
│       │                                └───────────────────────►│ return session ✗
│       │                                                         │
│       └── suggestion != ""                                      │
│               │                                                 │
│               ▼                                                 │
│       session["outfit_suggestion"] = "Pair with your jeans..."  │
│               │                                                 │
│               ▼                                                 │
│  create_fit_card(outfit_suggestion, selected_item)              │
│               │                                                 │
│               ▼                                                 │
│       session["fit_card"] = "Thrifted this Y2K tee for $18..."  │
│               │                                                 │
└───────────────┼─────────────────────────────────────────────────┘
                │
                ▼
        Return session
        ├── session["error"]    → None (success)
        ├── session["fit_card"] → 2–4 sentence caption
        └── session["selected_item"] → title, price, platform, condition
```

**Session dict — fields written and read at each stage:**

| Field | Written by | Read by |
|---|---|---|
| `session["parsed"]` | Planning loop (parse step) | `search_listings` call |
| `session["search_results"]` | `search_listings` result | Planning loop (gate check) |
| `session["selected_item"]` | Planning loop (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | `_new_session()` on init | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` result | `create_fit_card`, gate check |
| `session["fit_card"]` | `create_fit_card` result | Caller (final output) |
| `session["error"]` | Planning loop on any early exit | Caller (to detect failure) |

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**`search_listings`**
I'll give Claude the Tool 1 block from planning.md (what it does, all three input parameters with types and meaning, the full return value field list, and the failure mode). I'll also paste in the `load_listings()` call signature from `utils/data_loader.py` so it knows what function to use. I'll ask it to implement `search_listings()` in `tools.py` — no LLM calls, pure Python filtering and scoring.

Before running it, I'll check the generated code for these five things:
1. Does it call `load_listings()` (not read the file directly)?
2. Does it filter by `max_price` when provided, and skip the filter when `None`?
3. Does it filter by `size` using case-insensitive substring matching, and skip when `None`?
4. Does it score by word overlap across `title`, `style_tags`, and `description`?
5. Does it return an empty list (not raise) when nothing matches?

Then I'll test with three queries before trusting it: `"vintage graphic tee"` (should return results), `"vintage graphic tee"` with `max_price=10.0` (should filter some out), and `"designer ballgown"` with `max_price=5.0` (should return empty list).

---

**`suggest_outfit`**
I'll give Claude the Tool 2 block from planning.md (inputs, return value description, failure mode) plus the `wardrobe_schema.json` structure so it knows the shape of `wardrobe["items"]`. I'll ask it to implement `suggest_outfit()` in `tools.py`, making one Groq LLM call — with two prompt branches: one that names wardrobe pieces when `items` is non-empty, and one that gives general styling advice when it is empty.

Before running it, I'll check:
1. Does it check `wardrobe["items"]` for emptiness before building the prompt?
2. Does the non-empty prompt include the wardrobe item names (not just categories or tags)?
3. Does it return a string, never raise?

Then I'll test twice: once with `get_example_wardrobe()` (should name specific pieces), once with `get_empty_wardrobe()` (should return general advice, not crash).

---

**`create_fit_card`**
I'll give Claude the Tool 3 block from planning.md (inputs, the four caption style requirements, the failure mode). I'll ask it to implement `create_fit_card()` in `tools.py`, calling Groq with a higher temperature.

Before running it, I'll check:
1. Is the temperature set to 0.9 or higher?
2. Does it guard against an empty `outfit` string and return the error string immediately without calling the LLM?
3. Does the prompt tell the LLM to mention item name, price, and platform once each?

Then I'll test twice: once with a real outfit string and item dict (caption should read like a social post, not a product description), and once with an empty outfit string (should return the error message, not crash).

---

**Milestone 4 — Planning loop and state management:**

I'll give Claude three things together: the Planning Loop section of planning.md (all five steps with the exact conditionals), the Architecture diagram (the ASCII flow and the session field table), and the `_new_session()` function from `agent.py` so it knows the exact field names to use. I'll ask it to implement `run_agent()` in `agent.py` only, not `tools.py`.

Before running it, I'll check:
1. Does it call `_new_session()` first?
2. Does it parse `description`, `size`, and `max_price` from the raw query (not just pass the whole query string to `search_listings`)?
3. After `search_listings`, does it check for an empty list and return early with `session["error"]` set?
4. Does it set `session["selected_item"] = results[0]` before calling `suggest_outfit`?
5. After `suggest_outfit`, does it check for an empty/whitespace result and return early?
6. Does it return `session` at the end (not just the fit card string)?

Then I'll run the two test cases already in `agent.py`'s `__main__` block: the happy path (should print a fit card) and the no-results path (should print the error message with `session["error"]` set and `session["fit_card"]` as `None`).

---

## A Complete Interaction (Step by Step)

FitFindr takes a user's request and runs three tools in order: search for a listing, suggest an outfit, then write a caption. Each tool only runs if the one before it worked. If the search comes back empty, the agent tells the user and stops — it doesn't pass empty data into the next tool.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

---

**Step 1 — Parse the query**

The planning loop parses the query with regex and extracts:
- `description = "vintage graphic tee"` (price phrase stripped)
- `size = None` (no size mentioned)
- `max_price = 30.0` (detected "under $30")

`session["parsed"]` is set to these three values.

---

**Step 2 — `search_listings("vintage graphic tee", size=None, max_price=30.0)`**

The tool loads all listings and filters out anything with `price > 30.0`. No size filter is applied. It then scores each remaining listing by counting overlapping words between `"vintage graphic tee"` and each listing's `title`, `style_tags`, and `description`.

The top scorer is `lst_002` ("Y2K Baby Tee — Butterfly Print"):
- Matches on: `"vintage"` (in `style_tags`), `"graphic"` (in `style_tags` as part of `"graphic tee"`), `"tee"` (in `title` and `style_tags`)
- Price: `$18.00` ✓ under max
- Size: `"S/M"` (no filter applied)

`search_listings` returns a list with `lst_002` first. The planning loop checks: list is not empty, so it sets:
- `session["search_results"] = [lst_002, ...]`
- `session["selected_item"] = lst_002`

---

**Step 3 — `suggest_outfit(new_item=lst_002, wardrobe=example_wardrobe)`**

The tool builds a prompt using:
- New item: `"Y2K Baby Tee — Butterfly Print"`, colors `["white", "pink", "purple"]`, style tags `["y2k", "vintage", "graphic tee", "cottagecore"]`
- Wardrobe items by name: `"Baggy straight-leg jeans, dark wash"`, `"Wide-leg khaki trousers"`, `"Chunky white sneakers"`, `"Black combat boots"`, etc.

The LLM returns something like:
> "Outfit 1: Tuck the butterfly tee into your baggy straight-leg jeans and finish with your chunky white sneakers. Very early 2000s. Outfit 2: Wear it loose over your wide-leg khaki trousers with your black crossbody bag for a softer, more cottagecore take."

The planning loop checks: string is not empty, so it sets:
- `session["outfit_suggestion"] = <that string>`

---

**Step 4 — `create_fit_card(outfit=<suggestion>, new_item=lst_002)`**

The tool builds a prompt giving the LLM the outfit suggestion and the item's `title`, `price`, and `platform`. It calls Groq at temperature 0.9. The LLM returns something like:

> "Found this Y2K butterfly tee on Depop for $18 and it immediately went into rotation. Tucked into my baggy straight-legs with chunky white sneakers, it's giving early 2000s Delia's catalog in the best way. The fit is more cropped than the tag suggests, which honestly makes it even better."

The planning loop sets:
- `session["fit_card"] = <that caption>`

---

**Final output to user:**

```
Y2K Baby Tee — Butterfly Print
$18.00 · depop · condition: excellent

Found this Y2K butterfly tee on Depop for $18 and it immediately went into
rotation. Tucked into my baggy straight-legs with chunky white sneakers —
it's giving early 2000s Delia's catalog in the best way. The fit is more
cropped than the tag suggests, which honestly makes it even better.
```

The caller reads `session["fit_card"]` for the caption and `session["selected_item"]` for the listing details (`title`, `price`, `platform`, `condition`). `session["error"]` is `None`, confirming a successful run.
