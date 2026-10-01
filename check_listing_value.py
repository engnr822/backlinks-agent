"""Is a live listing worth anything, or is it a page nobody will ever see?

A directory that accepts a listing with no account and no CAPTCHA has no
gatekeeping — and the ones that know they are a spam target defend themselves
the only way they can: they noindex the page and nofollow the link. The
listing is real, it is just invisible, and it passes nothing.

That is not something to assume either way. It is four facts on the page:

  robots meta      noindex means Google will not keep the page at all
  rel on the link  nofollow / ugc / sponsored all say "pass no ranking signal"
  permalink        a listing that exists only inside a search-results URL has
                   no page of its own to be indexed
  sitemap          if the site's own sitemap carries no listings, it is not
                   asking anyone to index them

  python check_listing_value.py <live-listing-url> [--site yourdomain.com]

Run it once per directory, on the first listing you make there. The answer
holds for every later listing on the same site, and it is the difference
between a citation and an afternoon.
"""
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(400000).decode("utf-8", "replace")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("Usage: python check_listing_value.py <live-listing-url> [--site domain]")
    url = args[0]
    site = ""
    if "--site" in sys.argv:
        i = sys.argv.index("--site")
        site = sys.argv[i + 1] if len(sys.argv) > i + 1 else ""
    if not site and len(args) > 1:
        site = args[1]

    try:
        final, body = get(url)
    except Exception as e:
        sys.exit(f"Could not read the listing: {e}")

    print(f"listing   {final}\n")
    verdicts = []

    # 1. robots
    m = re.search(r'<meta[^>]+name=["\']robots["\'][^>]*content=["\']([^"\']+)', body, re.I)
    robots = (m.group(1) if m else "").lower()
    if "noindex" in robots:
        print(f"  robots        noindex  ->  Google will not keep this page")
        verdicts.append("noindex")
    else:
        print(f"  robots        {robots or '(none — indexable)'}")

    # 2. the outbound link
    rels = []
    if site:
        host = re.escape(site.replace("https://", "").replace("http://", "").strip("/"))
        for a in re.finditer(r"<a\b[^>]*href=[\"'][^\"']*" + host + r"[^\"']*[\"'][^>]*>", body, re.I):
            r = re.search(r'rel=["\']([^"\']+)', a.group(0), re.I)
            rels.append((r.group(1) if r else "").lower())
    if not site:
        print("  link          (pass --site yourdomain.com to check the rel)")
    elif not rels:
        print(f"  link          no link to {site} found on this page")
        verdicts.append("no link")
    else:
        worst = max(rels, key=lambda r: ("nofollow" in r) + ("ugc" in r) + ("sponsored" in r))
        blocked = [t for t in ("nofollow", "ugc", "sponsored") if t in worst]
        if blocked:
            print(f"  link          rel=\"{worst}\"  ->  passes no ranking signal")
            verdicts.append("+".join(blocked))
        else:
            print(f"  link          rel=\"{worst or '(none)'}\"  ->  followed")

    # 3. a page of its own
    q = urllib.parse.urlparse(final).query
    if q and re.search(r"\b(q|search|s|query)=", q):
        print("  permalink     none — the listing only exists inside a search URL")
        verdicts.append("no permalink")
    else:
        print("  permalink     has its own URL")

    # 4. does the site even ask for its listings to be indexed
    root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(final))
    try:
        _, sm = get(root + "/sitemap.xml", timeout=25)
        locs = re.findall(r"<loc>([^<]+)</loc>", sm)
        listingish = [l for l in locs
                      if re.search(r"/(listing|business|company|profile|place|directory)", l, re.I)
                      and not l.rstrip("/").endswith(("policy.php", "-policy"))]
        print(f"  sitemap       {len(locs)} url(s), {len(listingish)} look like listings")
        if locs and not listingish:
            verdicts.append("no listings in sitemap")
    except Exception:
        print("  sitemap       none found")

    print()
    if verdicts:
        print("VERDICT: worth ~nothing for ranking — " + ", ".join(verdicts))
        print()
        print("Not a reason to be angry at the directory. A site that takes a")
        print("listing with no account and no CAPTCHA knows what it attracts,")
        print("and this is how it protects itself. Spend the effort where the")
        print("link is followed and the page is indexed.")
    else:
        print("VERDICT: indexable page, followed link — this one counts.")


if __name__ == "__main__":
    main()
