import os

import pytest

from airial_audit.checks import (country_matches, coords_missing, distinctive_tokens,
                                 haversine_km, mentions_place, unsafe_topics, vet_post)
from airial_audit.extract import parse_page

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "chandpole_2026-11-20.html")


# ---- extraction on a real page snapshot (fetched 20 Nov 2026) ----
@pytest.fixture(scope="module")
def chandpole():
    with open(FIX, encoding="utf-8") as f:
        return parse_page(f.read(), "https://airial.travel/attractions/india/jaipur/chandpole-bazaar-jaipur-oAPQHQMT")


def test_parse_real_page(chandpole):
    assert chandpole["name"] == "Chandpole Bazaar Jaipur"
    assert chandpole["country"] == "India"
    assert chandpole["place_id"].startswith("ChIJ")
    assert abs(chandpole["lat"] - 26.92) < 0.01
    assert len(chandpole["reddit_posts"]) == 3


def test_real_page_unsafe_post_is_dropped(chandpole):
    verdicts = {p["title"][:20]: vet_post(chandpole["name"], p, chandpole["locality"])
                for p in chandpole["reddit_posts"]}
    blaze = verdicts["Safe place to blaze "]
    assert not blaze["keep"]
    assert any(r.startswith("unsafe:") and "drugs" in r for r in blaze["reasons"])
    # the 'hidden gems' thread does name chandpole bazar, so it stays
    assert verdicts["Please suggest some "]["keep"]


def test_parse_page_without_data():
    p = parse_page("<html><body>nothing</body></html>")
    assert p["name"] is None and p["reddit_posts"] == []


# ---- relevance ----
def test_distinctive_tokens_drop_generic_and_city():
    assert distinctive_tokens("Chandpole Bazaar Jaipur", "Jaipur") == ["chandpole"]


def test_mentions_place_fuzzy_spelling():
    assert mentions_place("Chandpole Bazaar Jaipur", "went to chandpol bazar yesterday", "Jaipur")


def test_mentions_place_accents():
    assert mentions_place("Karaoğlanoğlu Martyrs Cemetery", "the karaoglanoglu memorial was quiet")


def test_off_topic_post():
    post = {"title": "Best biryani near the station?", "text": "", "comments": [{"text": "Paradise"}]}
    v = vet_post("Charminar", post, "Hyderabad")
    assert v == {"keep": False, "relevance": "none", "reasons": ["off_topic"]}


# ---- safety ----
@pytest.mark.parametrize("text,topic", [
    ("Any cafe where you can smoke up?", "drugs"),
    ("where to buy weed near the beach", "drugs"),
    ("red light area near the station", "sex_work"),
    ("a tourist was murdered here", "violence_crime"),
])
def test_unsafe_topics_hit(text, topic):
    assert topic in unsafe_topics(text)


@pytest.mark.parametrize("text", [
    "Harris Tweed shop is lovely",          # 'weed' inside a word
    "the grape juice stall",                 # 'rape' inside a word
    "blazers and jackets on sale",           # 'blaze' only as a whole word
])
def test_unsafe_topics_no_false_hit_inside_words(text):
    assert unsafe_topics(text) == []


def test_deleted_empty_post():
    post = {"title": "Chandpole?", "text": "[deleted]", "comments": []}
    assert "deleted_empty" in vet_post("Chandpole Bazaar", post)["reasons"]


# ---- geo ----
def test_haversine_delhi_mumbai():
    assert 1100 < haversine_km(28.61, 77.21, 19.08, 72.88) < 1200


def test_coords_missing():
    assert coords_missing({"lat": 0.0, "lon": 0.0})
    assert coords_missing({"lat": None, "lon": 3})
    assert not coords_missing({"lat": 26.9, "lon": 75.8})


def test_country_matches():
    assert country_matches("India", ["India", "IN"]) is True
    assert country_matches("Türkiye", ["Turkey", "TR", "Türkiye"]) is True
    assert country_matches("India", ["Nepal", "NP"]) is False
    assert country_matches(None, ["India"]) is None


def test_wrong_place_with_shared_generic_words():
    # Greenland dunes page, post about a Colorado park: only 'sand dunes' overlaps
    post = {"title": "Great Sand Dunes advice?", "text": "Going to the national park in Colorado"}
    v = vet_post("Kangerlussuaq Sand Dunes", post, "Kangerlussuaq")
    assert v["relevance"] == "none" and "off_topic" in v["reasons"]


def test_area_level_post_is_kept():
    post = {"title": "Best low key areas of Folly Beach?", "text": ""}
    v = vet_post("Coquina Rocks Folly Beach", post, "Folly Beach")
    assert v["keep"] and v["relevance"] == "area"


def test_long_text_rows_are_resolved():
    from airial_audit.extract import resolve_refs, text_rows
    flight = '0:{"a":1}\n15:T5,héllo1:{"b":2}\n'  # 'héllo' is 6 bytes, so cut at 5 bytes -> 'h\xc3\xa9ll'
    rows = text_rows(flight)
    assert rows["15"].startswith("h")
    post = {"title": "x", "text": "$15", "comments": [{"text": "$15"}, {"text": "$99"}]}
    out = resolve_refs(post, rows)
    assert out["text"] == rows["15"] and out["comments"][1]["text"] == "$99"


def test_country_matches_territories():
    assert country_matches("Hong Kong", ["China", "CN"]) is True
    assert country_matches("Caribbean Netherlands", ["Netherlands", "NL"]) is True
    assert country_matches("Puerto Rico", ["United States", "US"]) is True
