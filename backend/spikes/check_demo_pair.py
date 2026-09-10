"""WI-0.0 — verify a candidate demo profile URL before committing to it.

Usage:
    python spikes/check_demo_pair.py https://some.university.edu/~person

Checks, in order:
  1. the page fetches and yields usable text
  2. a researcher name is extractable
  3. the institution domain resolves in ROR
  4. the author resolves in OpenAlex from (name, ROR)
  5. that author has >= 20 indexed works
  6. their top topic still has live literature (>= 15 works from 2022+)

Needs only OPENALEX_API_KEY. No Gemini key required.
"""
import math, os, re, sys, html, pathlib, urllib.parse
import httpx

for line in pathlib.Path(".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

KEY = os.environ.get("OPENALEX_API_KEY", "")
UA = {"User-Agent": f"ROIA-spike/0.1 (mailto:{os.environ.get('OPENALEX_MAILTO','')})"}
ok = lambda m: print(f"  \033[32mPASS\033[0m {m}")
no = lambda m: (print(f"  \033[31mFAIL\033[0m {m}"), sys.exit(1))
warn = lambda m: print(f"  \033[33mWARN\033[0m {m}")

def oa(path, **params):
    params["api_key"] = KEY
    r = httpx.get(f"https://api.openalex.org/{path}", params=params, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()

url = sys.argv[1] if len(sys.argv) > 1 else no("pass a profile URL")
print(f"\nChecking {url}\n")

# 1. fetch
print("1. page fetch")
try:
    r = httpx.get(url, headers=UA, follow_redirects=True, timeout=30)
except Exception as e:
    no(f"could not fetch: {e}")
if r.status_code != 200: no(f"HTTP {r.status_code}")
text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S | re.I)
text = html.unescape(re.sub(r"<[^>]+>", " ", text))
text = re.sub(r"\s+", " ", text).strip()
if len(text) < 600:
    no(f"only {len(text)} chars of text — likely JS-rendered. The demo has no renderer; pick another page.")
ok(f"{len(text)} chars extracted")

# 2. name
print("2. name extraction")
m = (re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', r.text, re.I)
     or re.search(r"<h1[^>]*>(.*?)</h1>", r.text, re.S | re.I)
     or re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I))
if not m: no("no name found in og:title / h1 / title")
name = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
name = re.split(r"\s*[|\-–—]\s*", name)[0].strip()
name = re.sub(r"^(Prof\.?|Professor|Dr\.?|A/Prof\.?)\s+", "", name, flags=re.I)
affil_hint = " ".join(re.findall(r"\(([^)]*)\)", name))      # "(CFAR, IHPC, NTU)" -> affiliation
name = re.sub(r"\s*\([^)]*\)", "", name).strip()
ok(f"name = {name!r}")

# 3. ROR
print("3. institution (scoring signal, not a gate)")
domain = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
ror = disp = None

def ror_lookup(**params):
    j = httpx.get("https://api.ror.org/v2/organizations", params=params, headers=UA, timeout=30).json()
    if not j.get("number_of_results"): return None
    it = j["items"][0]
    return it["id"], next((n["value"] for n in it["names"] if "ror_display" in n.get("types", [])), "?")

for d in [domain, ".".join(domain.split(".")[-3:]), ".".join(domain.split(".")[-2:])]:
    hit = ror_lookup(**{"query.advanced": f'domains:"{d}"'})
    if hit: ror, disp = hit; ok(f"domain {d} -> {ror} ({disp})"); break

if not ror and affil_hint:
    # personal domains (github.io, netlify.app, a vanity domain) have no ROR record.
    # Fall back to any affiliation named on the page itself.
    for cand in sorted((c.strip() for c in re.split(r"[,;/|]", affil_hint) if len(c.strip()) > 2),
                       key=len, reverse=True):
        hit = ror_lookup(query=cand)
        if hit:
            ror, disp = hit
            ok(f"page affiliation {cand!r} -> {ror} ({disp})")
            if len(cand) <= 5 and cand.lower() not in disp.lower():
                warn(f"{cand!r} is an acronym and ROR matched it by full-text, so this may be "
                     f"the wrong organisation. Low harm — institution is only 15% of the ranking.")
            break

if not ror:
    disp = ""
    warn(f"no ROR match for {domain} or the page text. Not fatal — institution is only a "
         f"scoring signal — but identity ranking loses one of its three signals.")

print("4. OpenAlex author")
# Query by NAME ONLY, then score. The institution filter must NOT be a hard gate:
# many real author records have last_known_institutions == NONE, so filtering on it
# silently excludes the correct person and returns stub duplicates instead.
j = oa("authors", filter=f"display_name.search:{name}",
       select="id,display_name,works_count,cited_by_count,topics,last_known_institutions",
       sort="works_count:desc", per_page=25)
if not j["results"]: no(f"no OpenAlex author named {name!r}")

page_words = set(re.findall(r"[a-z]{4,}", text.lower()))
STOP = {"research", "university", "professor", "science", "student", "paper", "group"}

def score(c):
    """Works count dominates. OpenAlex fragments author records: a real researcher
    typically has ONE canonical record with hundreds of works plus several stub
    duplicates with 1-3 works, and the canonical one often has NO institution at all.
    So institution must never be a hard filter, and must not outweigh volume.
    Topic overlap guards the remaining case: a genuine namesake in another field."""
    topic_toks = {w for t in (c.get("topics") or [])[:8]
                    for w in re.findall(r"[a-z]{4,}", t["display_name"].lower())} - STOP
    topic = len(topic_toks & page_words) / max(len(topic_toks), 1)
    inst = " ".join(i["display_name"] for i in (c.get("last_known_institutions") or [])).lower()
    inst_hit = bool(inst) and any(w in inst for w in disp.lower().split() if len(w) > 4)
    works = min(math.log10(c["works_count"] + 1) / math.log10(500), 1.0)
    return round(55 * works + 30 * topic + 15 * inst_hit, 1)

ranked = sorted(j["results"], key=score, reverse=True)
a = ranked[0]
inst_a = [i["display_name"] for i in (a.get("last_known_institutions") or [])]
ok(f"{a['display_name']} — {a['works_count']} works, {a['cited_by_count']} citations")
print(f"     institution on record: {inst_a or 'NONE (common; not an error)'}")
print(f"     {a['id']}")
if len(ranked) > 1:
    margin = score(a) - score(ranked[1])
    if margin < 10:
        warn(f"thin margin ({margin:.0f}) over runner-up "
             f"({ranked[1]['works_count']} works) — open both records and check by hand")
    else:
        ok(f"clear winner (margin {margin:.0f} over {len(ranked)-1} others)")

print("5. works threshold")
(ok if a["works_count"] >= 20 else no)(f"{a['works_count']} works (need >= 20)")

# 6. live literature
print("6. field is active")
topics = [t["display_name"] for t in (a.get("topics") or [])[:3]]
if not topics: no("no topics on this author — literature search will be weak")
best = 0
for t in topics:
    c = oa("works", filter=f"title_and_abstract.search:{t},from_publication_date:2022-01-01",
           select="id", per_page=1)["meta"]["count"]
    print(f"     {t}: {c} works since 2022")
    best = max(best, c)
(ok if best >= 15 else no)(f"top topic has {best} recent works (need >= 15)")

print(f"\n\033[32mGOOD DEMO PAIR.\033[0m Put this in .env:\n  ROIA_DEMO_PROFILE_URL={url}\n")
