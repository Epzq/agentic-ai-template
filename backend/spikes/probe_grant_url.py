"""Probe a grant URL and report exactly what a plain (browser-free) fetch can recover.

    python spikes/probe_grant_url.py https://www.rgp.gov.sg/nrf-ar/crp

Reference implementation for WI-1.4's ingest_grant. Three recovery layers, all
deterministic — no Playwright, no hosted reader:

  1. trafilatura over the fetched HTML                    (the normal case)
  2. Next.js RSC flight data in <script>self.__next_f...  (SPA content)
  3. linked documents, incl. PDFs inside ZIPs            (the real call sheet)

Layer 2 exists because rgp.gov.sg is a Next.js App Router app: its grant-call
dates are in the flight payload, not the DOM text. trafilatura returns 2,287
chars and none of them are the deadline. The bytes ARE in the response, so this
is a parsing problem, not a rendering problem.
"""
import io, json, re, sys, zipfile
import html as H
import httpx, lxml.html, trafilatura

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"}
DOC_HINT = re.compile(r"guide|call|proposal|apply|eligib|faq|term|annex|appendix|information sheet", re.I)


def flight_text(raw: str) -> tuple[str, list[str]]:
    """Recover text and links from Next.js RSC flight data. ('', []) if not a Next.js page."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)', raw)
    if not chunks:
        return "", []
    payload = "".join(json.loads('"' + c + '"') for c in chunks)
    out = []
    for w in re.findall(r'"wysiwyg":"((?:[^"\\]|\\.)*)"', payload):
        t = H.unescape(re.sub(r"<[^>]+>", " ", json.loads('"' + w + '"')))
        if (t := re.sub(r"\s+", " ", t).strip()):
            out.append(t)
    links = sorted(set(re.findall(r'https?://[^\\"\s]+\.(?:pdf|zip|docx?)(?:\?[^\\"\s]*)?', payload)))
    return "\n".join(out), links


def documents(url: str, links: list[str], limit: int = 6) -> list[tuple[str, int, bytes]]:
    """Fetch candidate documents. Detect by Content-Type, never by extension:
    these hrefs end in '?download=' and one anchor's text is just 'here'.

    Ranking note: these URLs are opaque UUIDs, so scoring the URL string finds
    nothing — DOC_HINT only helps on sites with readable paths. ZIPs first,
    because on rgp.gov.sg the actual Call Information Sheet is inside one."""
    def rank(u: str) -> tuple:
        stem = u.split("?")[0].lower()
        return (0 if stem.endswith(".zip") else 1 if stem.endswith(".pdf") else 2,
                not DOC_HINT.search(u), len(u))
    got = []
    for u in sorted(links, key=rank)[:limit]:
        try:
            r = httpx.get(u, headers=UA, follow_redirects=True, timeout=90)
            ct = r.headers.get("content-type", "").split(";")[0]
            if ct == "application/pdf":
                got.append((u.rsplit("/", 1)[-1][:40], len(r.content), r.content))
            elif ct in ("application/zip", "application/x-zip-compressed"):
                z = zipfile.ZipFile(io.BytesIO(r.content))
                for n in z.namelist():
                    if n.lower().endswith(".pdf"):          # the call sheet lives in here
                        got.append((n.rsplit("/", 1)[-1], z.getinfo(n).file_size, z.read(n)))
        except Exception as e:
            print(f"   ! {u[:70]}: {type(e).__name__}")
    return got


def main(url: str) -> None:
    r = httpx.get(url, headers=UA, follow_redirects=True, timeout=40)
    print(f"HTTP {r.status_code}  {len(r.text)} bytes of HTML\n")

    doc = lxml.html.fromstring(r.text)
    doc.make_links_absolute(str(r.url))                    # trafilatura fabricates URLs without this
    md = trafilatura.extract(doc, output_format="markdown", include_links=True,
                             include_tables=True, favor_recall=True) or ""
    print(f"1. trafilatura        {len(md):>6} chars")

    flight, flinks = flight_text(r.text)
    print(f"2. Next.js flight     {len(flight):>6} chars, {len(flinks)} document links")
    if flight:
        for line in flight.splitlines():
            if re.search(r"\b(period|deadline|closes?|20\d\d)\b", line, re.I):
                print(f"     > {line[:150]}")

    html_links = [a.get("href") for a in doc.xpath("//a[@href]") if a.get("href", "").startswith("http")]
    docs = documents(url, list({*flinks, *html_links}))
    print(f"3. documents          {len(docs)} PDF(s)")
    for name, size, _ in docs:
        print(f"     {size // 1024:>5} KB  {name}")

    print(f"\nTOTAL recoverable without a browser: {len(md) + len(flight)} chars of page text "
          f"+ {len(docs)} document(s)")
    if flight and len(flight) > len(md) * 0.2:
        print("NOTE: this page hides real content in flight data — layer 2 is not optional here.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "https://www.rgp.gov.sg/nrf-ar/crp")
