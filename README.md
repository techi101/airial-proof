# airial-proof: a pre-publish check for the Reddit cards on Airial's place pages

Airial publishes public attraction pages (title pattern "Best of TikTok, Instagram & Reddit Travel Guide") and each one embeds Reddit threads about the place. This repo is a small checker that decides, per thread, whether it belongs on that page, plus an audit of a random sample of live pages.

Snapshot: pages fetched 20 Nov 2026 (16:58 to 17:12 UTC). Everything below is from that snapshot.

## Why this problem

- Airial's own pitch is grounding and trust. The business site promises a guide that answers "from your own content and as per your guidelines" and shows "the page each answer came from shown underneath", and lists "SEO pages: Targeted inbounds 24/7" as a product ([airial.travel/travel-businesses](https://airial.travel/travel-businesses)).
- The JD asks for exactly this kind of work: "Solve hard applied-AI problems: reasoning over many constraints, and improving latency, accuracy and cost" ([LinkedIn job 4492512984](https://www.linkedin.com/jobs/view/4492512984)).
- Outside reviews say the same thing about accuracy: "recommendations still need a human sanity-check" ([Look4AI review, July 2026](https://look4ai.net/tool/airial-travel)).

## What I found

**1. A drug thread on the Chandpole Bazaar (Jaipur) page.** Found while reading the page by hand, not part of the random sample. The third Reddit card is titled "Safe place to blaze in Jaipur? Any cafe where you can smoke up ( in chillums )" and its quoted comment is in the same vein. It is in the visible preview grid.
Page: https://airial.travel/attractions/india/jaipur/chandpole-bazaar-jaipur-oAPQHQMT · thread: https://www.reddit.com/r/jaipur/comments/14f3lmh/
A saved copy of the page is in `tests/fixtures/chandpole_2026-11-20.html` and a test checks that the card gets dropped.

**2. The Kangerlussuaq Sand Dunes (Greenland) page carries Colorado threads.** 5 of its 7 Reddit posts are about other places: four are about Great Sand Dunes National Park in Colorado, and one is a general r/4x4 dune-driving post. The r/4x4 one ("Tips for Off-Roading at the Sand Dunes ... Get a Whip Flag") shows in the visible preview. The four Colorado threads are in the page's data payload (I did not confirm which UI view shows them).
Page: https://airial.travel/attractions/greenland/kangerlussuaq/kangerlussuaq-sand-dunes-G77rpYIz
The likely cause is that retrieval matched the words "sand dunes" and not the place.

**3. Random sample audit.** 300 pages, drawn with seed 20261120 from the 270,995 URLs listed in the 29 attraction sitemaps. All 300 fetched.

| Measure | Count |
|---|---|
| Pages with Reddit posts | 151 of 300 |
| Reddit posts on those pages | 491 |
| Posts that name the place | 395 |
| Posts that name only the town around it | 73 |
| Posts that name neither (flagged `off_topic`) | 23, on 17 pages |
| After a hand check of those 23 | 5 wrong place, 2 housing threads with no use to a visitor, 1 deleted post, 11 regional but fine, 4 where my rule was wrong |
| Posts flagged by the unsafe-topic rules | 5. Hand check: 0 serious, 2 mildly sensitive, 3 false hits ("weed lines" in fishing, seaweed, a history of executions) |
| Coordinates missing or in the wrong country | 0 (after mapping territories such as Hong Kong and Puerto Rico to their parent country) |

The hand check is in `data/hand_check.csv`. So in this sample, 8 posts on 3 of the 151 pages with posts (about 2%) should not be there. That is a rough rate from a small sample. I only hand checked the flagged posts, so I do not know how many bad posts the rules missed.

What this says: most cards are fine and the coordinates are solid. The failures that do exist are the kind a reader notices (a Colorado hike on a Greenland page, a drug thread on a family market page), and a cheap check catches them before publishing.

## What the tool does

`airial_audit/checks.py` → `vet_post(place_name, post, locality)` returns `{"keep", "relevance", "reasons"}`:

- **Relevance:** does the thread name the place? It drops generic words ("bazaar", "sand", "dunes", "beach") and the city name, then fuzzy-matches what is left (so "Chandpole" matches "chandpol", and accents are stripped so "Karaoğlanoğlu" matches "karaoglanoglu"). If the place is not named it checks the town, and marks the post `area`. If neither is named, it flags `off_topic`.
- **Unsafe topics:** word-start rules for drugs, sex work, violence and self-harm.
- **Empty posts:** `[deleted]` or `[removed]` with no comments.

`airial_audit/extract.py` reads a page: JSON-LD for name, address and coordinates, and the Next.js flight payload for `redditPosts` and `place_id`. Long strings in that payload are stored as separate rows (`15:T45c,...`) and referenced as `"$15"`. The extractor resolves them, because without that, 136 of the 1,704 post and comment texts in the sample (8%) read as a bare `$16`.

`airial_audit/geo.py` reverse-geocodes the coordinates with OpenStreetMap Nominatim (free, one request a second, cached) and compares the country to the page's address.

Inside a real pipeline the same `vet_post` call would run before a card is published. A small LLM judge could replace the keyword rules for the borderline `area` cases.

## Run it

```
pip install pytest
python -m pytest -q                     # 22 tests, no network
python vet.py <airial attraction url>   # KEEP / DROP for each card on one live page
python audit.py --n 300 --seed 20261120 # sample, fetch (1 req/s), score -> data/summary.json
python audit.py --rescore               # rescore from the local page cache
python show_flags.py                    # print flagged items for a hand check
```

Standard library only, apart from pytest. No API keys.

Example (live, 20 Nov 2026):

```
Kangerlussuaq Sand Dunes | Kangerlussuaq, Greenland | 7 Reddit posts
  KEEP [place] -            What to do on 8hr  Kangerlussuaq layover
  DROP [none ] off_topic    Tips for Off-Roading at the Sand Dunes
  KEEP [place] -            Kangerlussuaq, Greenland by local guide Adam Lyberth
  DROP [none ] off_topic    Advice for backpacking Great Sand Dunes this weekend?
  DROP [none ] off_topic    Great Sand Dunes advice?
  DROP [none ] off_topic    The most unique and difficult hike I've ever done. Great Sand Dunes Na
  DROP [none ] off_topic    Visiting Sand Dune National Park - Any Tips?
```

## Limits

- 300 pages out of about 271k. The rates are rough and only describe this snapshot.
- The rules are keyword based. On the hand check, about a third of `off_topic` flags (8 of 23) were real problems. That is fine for queueing items for review but too noisy to auto-delete. The unsafe rules hit 3 false positives out of 5 in the sample.
- Only flagged posts were hand checked, so recall is unknown.
- I read only public pages. robots.txt allows `/` for normal agents. Pages are cached locally in `data/pages/` and not committed.
- I could not find where the "4.6 (491k reviews)" on the Chandpole page comes from. The page payload's own `rating` field is `{"reviews":0,"score":0}`, so the number may come from a server-only field. I make no claim about it.
