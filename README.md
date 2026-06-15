# FitFindr 🛍️

FitFindr is a multi-tool AI agent that helps you find secondhand clothing and style it.
Describe what you're looking for — FitFindr finds a matching listing, suggests outfits
built from your existing wardrobe, and writes a share-ready caption for the find.

Under the hood it runs **three tools in a fixed sequence**, where each tool only runs if
the previous one produced something useful:

```
search_listings  ──►  suggest_outfit  ──►  create_fit_card
   (find it)            (style it)           (caption it)
```

---

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Then open the URL printed in your terminal (usually http://127.0.0.1:7860 — check the
output, the port can vary).

You can also run the agent directly:

```python
from agent import run_agent
from utils.data_loader import get_example_wardrobe

session = run_agent("vintage graphic tee under $30", wardrobe=get_example_wardrobe())
print(session["fit_card"])   # None if session["error"] is set
```

---

## Tool Inventory

FitFindr uses three tools. `search_listings` is pure Python (filtering + scoring over a
local dataset); `suggest_outfit` and `create_fit_card` each make one Groq LLM call
(`llama-3.3-70b-versatile`).

### 1. `search_listings`

**Purpose:** Find listings in the mock catalog that match the user's request, ranked by
relevance.

**Inputs:**

| Parameter | Type | Meaning |
|---|---|---|
| `description` | `str` | Free-text keywords (e.g. `"vintage graphic tee"`). Split into words; each word is matched against a listing's `title`, `style_tags`, and `description`. |
| `size` | `str \| None` | Size to filter by (e.g. `"M"`). Case-insensitive **substring** match, so `"M"` matches `"S/M"`. `None` skips the filter. |
| `max_price` | `float \| None` | Inclusive price ceiling. Listings with `price > max_price` are dropped before scoring. `None` skips the filter. |

**Output:** `list[dict]` — matching listing dicts sorted by relevance score, highest first.
Each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`,
`price`, `colors`, `brand`, `platform`. Returns `[]` when nothing matches — **never raises.**

### 2. `suggest_outfit`

**Purpose:** Turn one listing into concrete outfit ideas, grounded in what the user already
owns.

**Inputs:**

| Parameter | Type | Meaning |
|---|---|---|
| `new_item` | `dict` | The selected listing dict (top result from `search_listings`). |
| `wardrobe` | `dict` | A wardrobe dict with an `'items'` key holding a list of wardrobe-item dicts. The list **may be empty** (new user). |

**Output:** `str` (1–3 paragraphs). If the wardrobe has items, it names 1–2 outfits using
**specific wardrobe pieces by name**. If the wardrobe is empty, it gives **general styling
advice** for the item instead. Always returns a non-empty string.

### 3. `create_fit_card`

**Purpose:** Write a short, share-ready OOTD-style caption for the find.

**Inputs:**

| Parameter | Type | Meaning |
|---|---|---|
| `outfit` | `str` | The outfit suggestion from `suggest_outfit`. Must be non-empty. |
| `new_item` | `dict` | The listing dict, used to weave in `title`, `price`, and `platform`. |

**Output:** `str` — a 2–4 sentence caption that mentions the item name, price, and platform
once each, describes the vibe specifically, and reads like a real social post. Runs at a
higher LLM temperature (0.9) so captions vary. If `outfit` is empty/whitespace, returns a
descriptive error string **without calling the LLM.**

---

## How the Planning Loop Works

The whole agent lives in `run_agent(query, wardrobe)` in [agent.py](agent.py). It is a
**fixed linear pipeline with gates** — the same three tools always run in the same order,
but the loop checks the result of each tool before deciding whether the next one is allowed
to run. This is the core decision the agent makes: *not which tool to call, but whether it
is safe to continue.*

**Step 1 — Parse the query.** The raw query string is parsed with regex into three values:
`description` (keywords with price/size phrases stripped out), `size`, and `max_price`.
These go into `session["parsed"]`. Example: `"vintage graphic tee under $30"` →
`description="vintage graphic tee"`, `size=None`, `max_price=30.0`.

**Step 2 — Search, then gate.** Call `search_listings(...)`.
- **If results are empty** → set `session["error"]` to a recovery message and **return
  immediately**. `suggest_outfit` is never called with an empty item.
- **If results exist** → store them and set `session["selected_item"] = results[0]` (the
  highest-scored listing) and continue.

**Step 3 — Suggest an outfit, then gate.** Call `suggest_outfit(selected_item, wardrobe)`.
- **If the suggestion is empty/whitespace** → set `session["error"]` and **return
  immediately**. `create_fit_card` is never called with no outfit.
- **Otherwise** → store the suggestion and continue.

**Step 4 — Create the fit card.** Call `create_fit_card(outfit, selected_item)` and store
the result in `session["fit_card"]`.

**Step 5 — Return the session.** The caller checks `session["error"]` first: if it's `None`,
the run succeeded and `session["fit_card"]` holds the caption; if it's set, the run ended
early and the downstream fields are `None`.

The key design decision: **gates between tools.** An empty search result or an empty outfit
isn't passed downstream — it stops the chain with a specific, user-facing message. This
prevents the classic multi-tool failure where one empty result silently poisons everything
after it.

---

## State Management

All state for a single interaction lives in one **session dict**, created by `_new_session()`
at the start of `run_agent`. It is the single source of truth: every tool reads its inputs
from the session and writes its output back into the session. Nothing is passed between tools
through globals or side channels — the session dict *is* the channel.

| Field | Written by | Read by |
|---|---|---|
| `query` | `_new_session()` | parse step |
| `parsed` | parse step | `search_listings` call |
| `search_results` | `search_listings` result | gate check |
| `selected_item` | loop (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `_new_session()` | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` result | `create_fit_card`, gate check |
| `fit_card` | `create_fit_card` result | caller (final output) |
| `error` | loop, on any early exit | caller (to detect failure) |

Because every output field is initialized to a neutral value (`None`, `[]`), the caller can
inspect the session safely no matter where the run stopped. The UI layer in
[app.py](app.py) (`handle_query`) relies on exactly this: it checks `session["error"]`
first, and otherwise maps `selected_item`, `outfit_suggestion`, and `fit_card` to the three
output panels.

---

## Error Handling

Each tool has a defined failure mode and a graceful response — no tool raises an exception
on bad/empty input. The three modes were **deliberately triggered from the terminal** to
confirm the recovery actually works (Milestone 5). One concrete example is included for each.

### `search_listings` — no results match

The chain stops and the user gets an adaptive recovery message that names the filters that
might be too narrow (size, price). `suggest_outfit` is never called.

> **Tested:** `search_listings('designer ballgown', size='XXS', max_price=5)` returned `[]`
> (no exception). Run through the full agent, the gate fired:
> ```
> error    : "No listings matched your search — try broader keywords or
>             remove the size filter or raise your price ceiling."
> results  : []
> outfit   : None        # suggest_outfit never ran
> fit_card : None        # create_fit_card never ran
> ```

### `suggest_outfit` — empty wardrobe

**Not a hard failure.** An empty wardrobe is the normal new-user state, so the tool switches
to a general-advice prompt and the chain continues all the way to a fit card.

> **Tested:** calling `suggest_outfit(listing, get_empty_wardrobe())` returned a full styling
> string ("...pairs well with low-rise jeans, a chunky belt..." etc.) with no references to
> a saved wardrobe and no exception. `create_fit_card` still ran afterward.

### `create_fit_card` — empty outfit string

Returns a descriptive error string **before** making any LLM call. (In the live agent this
is also guarded upstream by the Step 3 gate, so it's defense-in-depth.)

> **Tested:** `create_fit_card('', listing)` returned the string
> `"Cannot write a fit card without outfit details."` — no LLM call, no exception.

---

## Spec Reflection

Building from the spec in [planning.md](planning.md), most of the implementation matched the
plan closely — the three-tool sequence, the gates, and the session-dict design all landed as
designed. A few things shifted or surfaced during implementation and testing:

- **State management was under-specified up front.** The planning doc described the session
  dict in the Architecture diagram but left the dedicated "State Management" prose blank. In
  practice the field-ownership table (who writes / who reads each field) turned out to be the
  most important artifact — it's what made the gates and the UI mapping unambiguous.

- **The first price parser was narrower than the spec.** planning.md lists `"$30 or less"`
  as a target pattern, but the AI's initial regex only matched the *"under $X" / "less than
  $X"* phrasing (price word before the number), so `"$25 or under"` silently parsed to
  `max_price=None`. End-to-end testing caught this, and I widened the regex to handle the
  reversed phrasing (see AI Usage, Instance 2). The lesson: the spec listed the *patterns* to
  support, but only running real queries revealed that one of them had been dropped.

- **The spec's "keyword overlap" was under-specified about filler words.** planning.md said to
  score by "counting how many words from the description appear" — it didn't say to remove
  stopwords, and the AI's substring implementation matched filler words like `"or"` / `"under"`
  inside unrelated descriptions, surfacing an irrelevant top result. I added stopword filtering
  (see AI Usage, Instance 1). This was the clearest case of a spec that *looked* complete but
  left a gap that only testing exposed.

- **Error messages are more adaptive than first specced.** The plan wrote one fixed
  no-results string; the implementation builds the message conditionally, appending hints only
  for the filters the user actually set (size and/or price). This made the recovery advice
  more relevant and is the version kept.

### Known limitations

- Price filtering understands `"under $X"` and `"$X or under/less"`, but not every phrasing
  (e.g. `"max $X"`, `"around $X"`).
- The catalog is 40 mock items; very specific queries may match on a partial keyword (e.g. a
  color) when the exact garment isn't present.
- Keyword search has no stopword removal, so unrelated items can occasionally rank highly.

---

## AI Usage

This project was implemented with AI assistance (Claude), directed by the spec in
[planning.md](planning.md). The plan for each part — what spec sections to hand the model
and what checks to run before trusting the output — is documented in the "AI Tool Plan"
section of planning.md. Two specific instances:

### Instance 1 — Implementing `search_listings` (Milestone 3)

- **Input given to the AI:** the Tool 1 block from planning.md (purpose, all three input
  parameters with types and meaning, the full return-value field list, and the no-results
  failure mode), plus the `load_listings()` call signature from `utils/data_loader.py`.
  I asked for a **pure-Python** implementation — no LLM calls — that filters then scores.
- **What it produced:** a `search_listings()` that applies the `max_price` and `size`
  filters, then scores each listing by lowercasing the description, splitting it on spaces,
  and counting how many of those tokens appear as substrings of each listing's combined
  `title` + `style_tags` + `description` text.
- **What I changed / overrode:** during end-to-end testing I searched `"jeans, size S, $25
  or under"` and the top result was a **black mesh top** — clearly wrong. Tracing it back,
  the scorer was matching filler words: `"or"` and `"under"` appear as substrings inside the
  mesh top's description ("layering **under** a graphic tee **or** over a bralette"), so an
  unrelated item outscored the real jeans. I overrode the tokenizing step to **strip
  punctuation off each keyword and drop a stopword set** (`or`, `under`, `the`, `with`, …)
  before scoring. After the change that query no longer surfaces the mesh top.

### Instance 2 — Implementing query parsing in `run_agent` (Milestone 4)

- **Input given to the AI:** the **Planning Loop** section of planning.md (all five steps
  with the exact gate conditionals), the **Architecture diagram** (the ASCII flow plus the
  session-field ownership table), and the `_new_session()` function so the model used the
  exact session field names. I scoped it to `agent.py` only.
- **What it produced:** a `run_agent()` that initializes the session, parses `description` /
  `size` / `max_price` from the raw query with regex, then calls the three tools in order with
  gates after `search_listings` and `suggest_outfit`. Its price regex matched only the
  *"under $X" / "less than $X"* phrasing (the price word **before** the number).
- **What I changed / overrode:** testing the same `"$25 or under"` query showed the price
  parser silently returned `max_price=None` — the "$25 or under" phrase was never recognized,
  so no price ceiling was applied and the leftover words leaked into the search keywords. I
  overrode the price regex to also match the **reversed phrasing** (`"$25 or under"`,
  `"$25 or less"`, `"below $30"`) and updated the description-stripping regex to remove that
  phrase too. Now `"$25 or under"` correctly parses to `max_price=25.0`.

## Project Layout

```
ai201-project2-fitfindr-starter/
├── agent.py                 # run_agent() — the planning loop + session state
├── tools.py                 # search_listings, suggest_outfit, create_fit_card
├── app.py                   # Gradio UI — handle_query() wires the agent to 3 panels
├── planning.md              # design spec: tool contracts, loop, architecture
├── data/
│   ├── listings.json        # 40 mock secondhand listings
│   └── wardrobe_schema.json # wardrobe format + example/empty wardrobes
├── utils/
│   └── data_loader.py       # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
└── tests/
    └── test_tools.py        # tool test suite
```
