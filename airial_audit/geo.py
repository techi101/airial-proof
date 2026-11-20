"""Free reverse geocoding with OpenStreetMap Nominatim (1 request/second, cached).

Usage policy: https://operations.osmfoundation.org/policies/nominatim/
"""
import json
import os
import time
import urllib.parse
import urllib.request

UA = "airial-proof-audit/0.1 (student research script)"
_last = [0.0]


def reverse_country(lat, lon, cache_path="data/geocode_cache.json"):
    """Return a list of country names/codes for the coordinates, or [] if none."""
    key = "%.4f,%.4f" % (lat, lon)
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    if key in cache:
        return cache[key]

    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    q = urllib.parse.urlencode({"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 3,
                                "accept-language": "en", "namedetails": 1})
    req = urllib.request.Request("https://nominatim.openstreetmap.org/reverse?" + q,
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception:
        return []  # do not cache failures
    finally:
        _last[0] = time.time()

    names = []
    addr = data.get("address") or {}
    if addr.get("country"):
        names.append(addr["country"])
    if addr.get("country_code"):
        names.append(addr["country_code"].upper())
    nd = data.get("namedetails") or {}
    for k in ("name", "name:en", "official_name:en", "short_name:en"):
        if nd.get(k):
            names.append(nd[k])
    cache[key] = names
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    return names
