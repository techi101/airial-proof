"""Export the audit results into web/data.json (and data.js for file:// use).

Every number comes from data/summary.json, data/results.jsonl, data/hand_check.csv
or the saved Chandpole fixture. Run from the repo root:  python web/export.py
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from airial_audit.checks import vet_post  # noqa: E402
from airial_audit.extract import parse_page  # noqa: E402

D = os.path.join(ROOT, "data")
summary = json.load(open(os.path.join(D, "summary.json"), encoding="utf-8"))
pages = [json.loads(l) for l in open(os.path.join(D, "results.jsonl"), encoding="utf-8")]
hand = list(csv.DictReader(open(os.path.join(D, "hand_check.csv"), encoding="utf-8")))

DROP = {"wrong_place", "not_for_visitors", "empty"}


def norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


# hand verdict per (page, title prefix)
def hand_for(page, title):
    for h in hand:
        if h["page"] == page and norm(title).startswith(norm(h["post_title"])[:25]):
            return h
    return None


def as_bool(v):
    return v is True or v == "True"


def as_list(v):
    if isinstance(v, list):
        return v
    try:
        return json.loads(v.replace("'", '"'))
    except Exception:
        return []


flagged_pages = []
queue = []
for p in pages:
    posts = []
    any_flag = False
    for post in p["posts"]:
        reasons = as_list(post.get("reasons"))
        keep = as_bool(post.get("keep"))
        h = None if keep else hand_for(p["name"], post.get("title", ""))
        item = {
            "title": post.get("title", ""),
            "url": post.get("url", ""),
            "relevance": post.get("relevance"),
            "rule": "KEEP" if keep else "DROP",
            "reasons": reasons,
            "hand": h["hand_verdict"] if h else None,
            "final": (("DROP" if h["hand_verdict"] in DROP else "KEEP") if h else None),
            "note": h["note"] if h else None,
        }
        posts.append(item)
        if not keep:
            any_flag = True
            queue.append({"page": p["name"], "locality": p.get("locality"), "country": p.get("country"),
                          "page_url": p["url"], **item})
    if any_flag:
        flagged_pages.append({"name": p["name"], "locality": p.get("locality"), "country": p.get("country"),
                              "url": p["url"], "posts": posts, "in_sample": True})

# Chandpole: found by hand outside the sample; re-run the checker on the saved page
fx = os.path.join(ROOT, "tests", "fixtures", "chandpole_2026-11-20.html")
url = "https://airial.travel/attractions/india/jaipur/chandpole-bazaar-jaipur-oAPQHQMT"
cp = parse_page(open(fx, encoding="utf-8").read(), url)
cposts = []
for post in cp["reddit_posts"]:
    v = vet_post(cp["name"], post, cp["locality"])
    cposts.append({"title": post.get("title", ""), "url": post.get("url", ""), "relevance": v["relevance"],
                   "rule": "KEEP" if v["keep"] else "DROP", "reasons": v["reasons"],
                   "hand": None if v["keep"] else "unsafe_real",
                   "final": None if v["keep"] else "DROP",
                   "note": None if v["keep"] else "drug thread in the visible preview grid; found by reading the page, not in the random sample"})
chandpole = {"name": cp["name"], "locality": cp["locality"], "country": cp["country"], "url": url,
             "posts": cposts, "in_sample": False}
for it in cposts:
    if it["rule"] == "DROP":
        queue.insert(0, {"page": cp["name"], "locality": cp["locality"], "country": cp["country"],
                         "page_url": url, "in_sample": False, **it})

verdicts = {}
for h in hand:
    verdicts[h["hand_verdict"]] = verdicts.get(h["hand_verdict"], 0) + 1

out = {
    "summary": summary,
    "hand_verdict_counts": verdicts,
    "hand_rows": len(hand),
    "queue": queue,
    "pages": [chandpole] + sorted(flagged_pages, key=lambda x: -sum(1 for q in x["posts"] if q["final"] == "DROP")),
    "unmatched_hand_rows": len(hand) - sum(1 for q in queue if q.get("hand") and q.get("in_sample", True) is not False),
}
W = os.path.join(ROOT, "web")
json.dump(out, open(os.path.join(W, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(os.path.join(W, "data.js"), "w", encoding="utf-8").write("window.DATA = " + json.dumps(out, ensure_ascii=False) + ";\n")
print("queue", len(queue), "pages", len(out["pages"]), "verdicts", verdicts, "unmatched", out["unmatched_hand_rows"])
