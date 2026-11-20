"""Pre-publish checks for social snippets and place data.

Every check is a plain function so it can sit in a pipeline before a page
(or an itinerary card) is rendered. No network calls in this module.
"""
import math
import re
import unicodedata
from difflib import SequenceMatcher

# ---- unsafe topic rules (word-start match, case-insensitive) ----
UNSAFE_TOPICS = {
    "drugs": [r"blaze\b", "smoke up", "chillum", "weed", "ganja", "charas", "hashish",
              "marijuana", "cannabis", "cocaine", "mdma", r"lsd\b", "get high", "stoned",
              "drug dealer", "bhang"],
    "sex_work": ["escort", "prostitut", "hooker", "brothel", "red light", "sex work",
                 "happy ending", "call girl", "social workers who can help you"],
    "violence_crime": [r"rape\b", r"raped\b", "murder", "stabb", "molest", "assault"],
    "self_harm": ["suicide", "kill myself"],
}
# each rule must start at a word start: 'weed' matches 'weed', not 'tweed'
_UNSAFE_RE = {t: re.compile("|".join(r"(?<![a-z])" + p for p in pats), re.I)
              for t, pats in UNSAFE_TOPICS.items()}

# words that say what kind of place it is, not which place it is
GENERIC = {
    "the", "of", "and", "a", "an", "de", "la", "le", "el", "di", "da", "du", "des", "del", "at", "in", "on",
    "bazaar", "bazar", "market", "temple", "beach", "park", "museum", "fort", "palace", "church",
    "cathedral", "mosque", "lake", "river", "garden", "gardens", "national", "city", "old", "town",
    "square", "street", "road", "bridge", "tower", "hill", "hills", "mount", "mountain", "falls",
    "waterfall", "island", "bay", "point", "view", "viewpoint", "centre", "center", "hall", "house",
    "gallery", "art", "memorial", "monument", "zoo", "cave", "caves", "trail", "st", "saint", "san",
    "santa", "new", "great", "little", "big", "north", "south", "east", "west", "central", "mall",
    "sand", "sands", "dune", "dunes", "rock", "rocks", "forest", "valley", "canyon", "springs",
    "spring", "harbour", "harbor", "port", "pier", "lighthouse", "castle", "ruins", "plaza",
    "district", "village", "airport", "station", "stadium", "theatre", "theater", "library",
    "university", "college", "school", "reserve", "regional", "state", "lookout", "shrine",
}


def _fold(s):
    """Lowercase and strip accents so 'Karaoğlanoğlu' matches 'karaoglanoglu'."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _words(s):
    return re.findall(r"[a-z0-9]+", _fold(s))


def post_text(post):
    """Title + body + comment text of one embedded Reddit post."""
    bits = [post.get("title") or "", post.get("text") or ""]
    for c in post.get("comments") or []:
        if isinstance(c, dict):
            bits.append(c.get("text") or "")
    return "\n".join(bits)


def distinctive_tokens(name, locality=None):
    """Tokens of the place name that identify it (drop generic words and the city)."""
    drop = GENERIC | set(_words(locality or ""))
    words = [w for w in _words(name) if len(w) >= 3]
    # fall back to the city word ('Kangerlussuaq Sand Dunes'), then to everything
    return ([w for w in words if w not in drop]
            or [w for w in words if w not in GENERIC]
            or words)


def mentions_place(name, text, locality=None, min_ratio=0.8):
    """True if any distinctive token of the name (or a close spelling) is in text.

    'Chandpole' vs 'chandpol' or 'bazar' spellings pass through the fuzzy ratio.
    """
    toks = distinctive_tokens(name, locality)
    words = set(_words(text))
    for t in toks:
        if t in words:
            return True
        for w in words:
            if abs(len(w) - len(t)) <= 2 and SequenceMatcher(None, t, w).ratio() >= min_ratio:
                return True
    return False


def unsafe_topics(text):
    """List of unsafe topic labels whose rules match text."""
    return sorted(t for t, rx in _UNSAFE_RE.items() if rx.search(text or ""))


def vet_post(place_name, post, locality=None):
    """Decide whether one social snippet should be shown on a place page.

    Returns {"keep": bool, "reasons": [...]}.
    """
    text = post_text(post)
    reasons = []
    topics = unsafe_topics(text)
    if topics:
        reasons.append("unsafe:" + ",".join(topics))
    if mentions_place(place_name, text, locality):
        level = "place"
    elif locality and mentions_place(locality, text):
        level = "area"  # about the town around it: weaker, but not wrong
    else:
        level = "none"
        reasons.append("off_topic")
    if (post.get("text") or "").strip() in ("[deleted]", "[removed]") and not post.get("comments"):
        reasons.append("deleted_empty")
    return {"keep": not reasons, "relevance": level, "reasons": reasons}


# ---- geo ----
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def coords_missing(page):
    lat, lon = page.get("lat"), page.get("lon")
    return lat is None or lon is None or (abs(lat) < 1e-6 and abs(lon) < 1e-6)


def country_matches(page_country, geocoded_names):
    """page_country is free text ('India'); geocoded_names are names/codes the
    reverse geocoder returned for the coordinates (any language variants)."""
    if not page_country or not geocoded_names:
        return None  # cannot decide
    pc = _fold(page_country).strip()
    want = {pc} | TERRITORY_PARENT.get(pc, set())
    return any(_fold(n).strip() in want for n in geocoded_names if n)


# OSM reports the sovereign state for these; the page naming the territory is fine
TERRITORY_PARENT = {
    "caribbean netherlands": {"netherlands", "nl"}, "aruba": {"netherlands", "nl"},
    "curacao": {"netherlands", "nl"}, "sint maarten": {"netherlands", "nl"},
    "hong kong": {"china", "cn"}, "macau": {"china", "cn"}, "macao": {"china", "cn"},
    "puerto rico": {"united states", "us"}, "guam": {"united states", "us"},
    "u.s. virgin islands": {"united states", "us"}, "united states virgin islands": {"united states", "us"},
    "greenland": {"denmark", "dk"}, "faroe islands": {"denmark", "dk"},
    "french polynesia": {"france", "fr"}, "reunion": {"france", "fr"}, "new caledonia": {"france", "fr"},
    "martinique": {"france", "fr"}, "guadeloupe": {"france", "fr"},
    "bermuda": {"united kingdom", "gb"}, "gibraltar": {"united kingdom", "gb"},
    "cayman islands": {"united kingdom", "gb"}, "turkiye": {"turkey", "tr"}, "turkey": {"turkiye", "tr"},
}
