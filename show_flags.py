"""Print every flagged post and country mismatch so a person can hand check them.

python show_flags.py > data/flags_for_hand_check.txt
"""
import json

rows = [json.loads(line) for line in open("data/results.jsonl", encoding="utf-8")]
for r in rows:
    if "error" in r:
        continue
    for p in r["posts"]:
        if p["reasons"]:
            print("=" * 80)
            print("PAGE :", r["name"], "|", r["locality"], "|", r["url"])
            print("FLAGS:", p["reasons"], "| relevance:", p["relevance"])
            print("POST :", p["title"], "|", p["url"])
            print("TEXT :", p["text"][:400].replace("\n", " / "))
    if r.get("country_ok") is False:
        print("=" * 80)
        print("COUNTRY MISMATCH CANDIDATE:", r["name"], "| page says", r["country"],
              "| coords", r["lat"], r["lon"], "| geocoder", r.get("geo_country"), "|", r["url"])
