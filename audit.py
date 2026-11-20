"""Sample public airial.travel attraction pages and run the checks.

python audit.py --n 300 --seed 20261120     # sample, fetch (cached), score
python audit.py --rescore                    # score again from the page cache only

Writes data/sample_urls.txt, data/sample_meta.json, data/results.jsonl, data/summary.json.
Pages are cached gzipped in data/pages/ (not committed).
Polite: one page request per second; robots.txt allows / for normal agents.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request

from airial_audit.checks import coords_missing, country_matches, post_text, vet_post
from airial_audit.extract import parse_page
from airial_audit.geo import reverse_country

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) airial-proof-audit/0.1"
INDEX = "https://airial.travel/sitemap_index.xml"
CACHE = "data/pages"


def get(url, timeout=40):
    # sitemap URLs can hold raw non-ASCII letters (e.g. 'ü'); percent-encode them
    url = urllib.parse.quote(url, safe=":/?&=%#~+-._")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def sample_urls(n, seed):
    """Reuse an existing sample so reruns score the same pages."""
    if os.path.exists("data/sample_urls.txt") and os.path.exists("data/sample_meta.json"):
        with open("data/sample_urls.txt", encoding="utf-8") as f:
            urls = [u for u in f.read().split("\n") if u]
        with open("data/sample_meta.json", encoding="utf-8") as f:
            return json.load(f), urls
    idx = get(INDEX)
    maps = [u for u in re.findall(r"<loc>(.*?)</loc>", idx) if "/sitemaps/attractions_" in u]
    pool = []
    for m in maps:
        pool += re.findall(r"<loc>(.*?)</loc>", get(m))
        time.sleep(0.5)
    urls = random.Random(seed).sample(pool, n)
    meta = {"sampled_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "attraction_sitemaps": len(maps), "urls_in_sitemaps": len(pool), "n": n, "seed": seed}
    with open("data/sample_urls.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(urls) + "\n")
    with open("data/sample_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return meta, urls


def cached_page(url, offline=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:16] + ".html.gz")
    if os.path.exists(path):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read(), False
    if offline:
        raise FileNotFoundError("not cached")
    html = get(url)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(html)
    return html, True


def score(url, html, geo=True):
    p = parse_page(html, url)
    posts = []
    for post in p["reddit_posts"]:
        v = vet_post(p["name"] or "", post, p["locality"])
        posts.append({"title": post.get("title"), "url": post.get("url"),
                      "text": post_text(post)[:600], **v})
    row = {k: p[k] for k in ("url", "name", "locality", "country", "lat", "lon", "place_id")}
    row["posts"] = posts
    row["coords_missing"] = coords_missing(p)
    if geo and not row["coords_missing"]:
        names = reverse_country(p["lat"], p["lon"])
        row["geo_country"] = names
        row["country_ok"] = country_matches(p["country"], names)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20261120)
    ap.add_argument("--rescore", action="store_true", help="use cached pages only")
    ap.add_argument("--no-geo", action="store_true")
    a = ap.parse_args()
    os.makedirs("data", exist_ok=True)

    meta, urls = sample_urls(a.n, a.seed)
    print(f"{meta['attraction_sitemaps']} attraction sitemaps, {meta['urls_in_sitemaps']} URLs, sample {len(urls)}", flush=True)

    rows = []
    with open("data/results.jsonl", "w", encoding="utf-8") as out:
        for i, u in enumerate(urls, 1):
            t0 = time.time()
            fetched = False
            try:
                html, fetched = cached_page(u, offline=a.rescore)
                row = score(u, html, geo=not a.no_geo)
            except Exception as e:  # keep going, record the failure
                row = {"url": u, "error": str(e)[:200]}
            rows.append(row)
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(i, "err" if "error" in row else len(row["posts"]), flush=True)
            if fetched:
                time.sleep(max(0, 1.0 - (time.time() - t0)))

    summarize(rows, meta)


def summarize(rows, meta):
    ok = [r for r in rows if "error" not in r]
    posts = [p for r in ok for p in r["posts"]]

    def pages(pred):
        return sum(1 for r in ok if any(pred(p) for p in r["posts"]))

    unsafe = lambda p: any(x.startswith("unsafe") for x in p["reasons"])  # noqa: E731
    off = lambda p: "off_topic" in p["reasons"]  # noqa: E731
    s = {
        **meta,
        "scored_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "fetched_ok": len(ok),
        "pages_with_reddit_posts": sum(1 for r in ok if r["posts"]),
        "reddit_posts_total": len(posts),
        "posts_relevance": {lvl: sum(1 for p in posts if p["relevance"] == lvl) for lvl in ("place", "area", "none")},
        "posts_flagged_unsafe": sum(1 for p in posts if unsafe(p)),
        "pages_with_unsafe_flag": pages(unsafe),
        "posts_flagged_off_topic": sum(1 for p in posts if off(p)),
        "pages_with_off_topic_flag": pages(off),
        "pages_coords_missing": sum(1 for r in ok if r["coords_missing"]),
        "pages_country_mismatch_candidates": sum(1 for r in ok if r.get("country_ok") is False),
        "note": "Rule-based flags, before hand check. See README for hand-checked counts.",
    }
    with open("data/summary.json", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
