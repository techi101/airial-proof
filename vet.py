"""Vet the Reddit cards on one live airial.travel attraction page.

python vet.py https://airial.travel/attractions/india/jaipur/chandpole-bazaar-jaipur-oAPQHQMT
"""
import sys

from airial_audit.checks import vet_post
from airial_audit.extract import parse_page
from audit import get

url = sys.argv[1]
p = parse_page(get(url), url)
print(f"{p['name']} | {p['locality']}, {p['country']} | {len(p['reddit_posts'])} Reddit posts")
for post in p["reddit_posts"]:
    v = vet_post(p["name"] or "", post, p["locality"])
    mark = "KEEP" if v["keep"] else "DROP"
    print(f"  {mark} [{v['relevance']:5}] {', '.join(v['reasons']) or '-':22} {post.get('title', '')[:70]}")
