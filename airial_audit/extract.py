"""Pull the structured data out of a public airial.travel attraction page.

The pages are Next.js App Router pages. Two places hold what we need:
  1. a JSON-LD <script id="structured-data"> block (name, address, geo)
  2. the React flight payload pushed via self.__next_f.push([1, "..."])
     (redditPosts, place_id, coordinates, ...)
"""
import json
import re

# ---- regexes ----
_LD_RE = re.compile(r'<script type="application/ld\+json" id="structured-data">(.*?)</script>', re.S)
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)


def flight_text(html):
    """Join every flight chunk into one decoded string."""
    out = []
    for chunk in _PUSH_RE.findall(html):
        try:
            out.append(json.loads('"' + chunk + '"'))  # undo JS string escaping
        except json.JSONDecodeError:
            continue
    return "".join(out)


def _first_value(text, key):
    """Decode the JSON value that follows the first "key": in text."""
    marker = '"%s":' % key
    i = text.find(marker)
    if i < 0:
        return None
    try:
        val, _ = json.JSONDecoder().raw_decode(text, i + len(marker))
        return val
    except json.JSONDecodeError:
        return None


_TROW_RE = re.compile(rb'(?:^|\n)([0-9a-f]+):T([0-9a-f]+),')


def text_rows(text):
    """Long strings are moved out of the JSON into rows like '15:T45c,<0x45c bytes>'
    and referenced as "$15". Return {row_id: string}."""
    b = text.encode("utf-8")
    rows = {}
    for m in _TROW_RE.finditer(b):
        start = m.end()
        rows[m.group(1).decode()] = b[start:start + int(m.group(2), 16)].decode("utf-8", "replace")
    return rows


def resolve_refs(obj, rows):
    """Swap "$<id>" placeholders for the text rows they point to."""
    if isinstance(obj, str) and obj.startswith("$") and obj[1:] in rows:
        return rows[obj[1:]]
    if isinstance(obj, list):
        return [resolve_refs(x, rows) for x in obj]
    if isinstance(obj, dict):
        return {k: resolve_refs(v, rows) for k, v in obj.items()}
    return obj


def parse_page(html, url=""):
    """Return a flat dict with the fields the checks use."""
    page = {"url": url, "name": None, "locality": None, "country": None,
            "lat": None, "lon": None, "place_id": None, "reddit_posts": []}

    m = _LD_RE.search(html)
    if m:
        try:
            ld = json.loads(m.group(1))
            page["name"] = ld.get("name")
            addr = ld.get("address") or {}
            page["locality"] = addr.get("addressLocality") or None
            page["country"] = addr.get("addressCountry") or None
            geo = ld.get("geo") or {}
            page["lat"], page["lon"] = geo.get("latitude"), geo.get("longitude")
        except json.JSONDecodeError:
            pass

    text = flight_text(html)
    page["place_id"] = _first_value(text, "place_id")
    posts = _first_value(text, "redditPosts")
    if isinstance(posts, list):
        rows = text_rows(text)
        page["reddit_posts"] = [resolve_refs(p, rows) for p in posts if isinstance(p, dict)]
    if page["name"] is None:
        page["name"] = _first_value(text, "placeName")
    return page
