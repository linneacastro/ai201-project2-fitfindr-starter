from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import load_listings, get_example_wardrobe, get_empty_wardrobe


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_empty_results():
    # No match for this query + tight filters — must return [] not raise
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)

def test_search_size_filter():
    results = search_listings("jeans", size="XL", max_price=None)
    assert all("xl" in item["size"].lower() for item in results)

def test_search_sorted_by_relevance():
    # The first result should score at least as high as the second
    results = search_listings("vintage denim jacket", size=None, max_price=None)
    assert len(results) >= 2  # need at least two to compare order


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    item = load_listings()[1]  # Y2K Baby Tee
    suggestion = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion.strip()) > 0

def test_suggest_outfit_empty_wardrobe():
    # Empty wardrobe is a graceful fallback, not an error — must return advice not crash
    item = load_listings()[1]
    suggestion = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion.strip()) > 0


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_guard():
    # Must return the error string immediately — no LLM call, no exception
    item = load_listings()[1]
    result = create_fit_card("", item)
    assert result == "Cannot write a fit card without outfit details."

def test_create_fit_card_whitespace_outfit_guard():
    item = load_listings()[1]
    result = create_fit_card("   ", item)
    assert result == "Cannot write a fit card without outfit details."

def test_create_fit_card_returns_caption():
    item = load_listings()[1]
    outfit = "Tuck the butterfly tee into baggy straight-leg jeans with chunky white sneakers."
    result = create_fit_card(outfit, item)
    assert isinstance(result, str)
    assert len(result.strip()) > 0

def test_create_fit_card_varies_on_same_input():
    item = load_listings()[1]
    outfit = "Tuck the butterfly tee into baggy straight-leg jeans with chunky white sneakers."
    results = {create_fit_card(outfit, item) for _ in range(3)}
    # At temperature=0.9 at least 2 of 3 runs should differ
    assert len(results) > 1
