"""Triage a pasted list of directories before anyone spends an evening on it.

A citation list that has been passed around loses entries quietly: sites die,
domains get parked, some were never directories, and a "USA" list picks up
UK-only and single-trade sites nobody notices until they are on the form.
Working through 130 of those by hand is hours, and the dead ones cost the same
as the live ones.

  python check_directories.py directories.txt

Fetches each one, records what came back, and flags the entries that are not
worth opening:

  DEAD        nothing answered, or the name does not resolve
  ERROR-4xx   answered, but not with a page
  PARKED      answered with a for-sale or registrar holding page
  OFF-TRADE   a real site, for a trade that is not yours
  NOT-A-DIR   a publishing or file-sharing tool, not a business directory
  WRONG-GEO   a country-specific site that is not the US

Nothing is removed. The verdict and the evidence are written next to each row
so a wrong call can be seen and overruled.
"""
import concurrent.futures as cf
import json
import re
import sys
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# Sites that are real but are for a different trade, or are not directories at
# all. Judged by domain, because the name is the giveaway on every one of them.
OFF_TRADE = re.compile(
    r"billiard|photographer|counseling|holistictherap|antiques|bedandbreakfast"
    r"|selfcatering|lotusguide|gospelgrid|financialadvisor|thebluebook"
    r"|topdesignfirms|engnetglobal|macraesbluebook|getmowed|local-roofing"
    r"|greatautodealers|shopstratford|quponing|health-local|allaboutcounseling"
    r"|bestplumbers", re.I)

NOT_A_DIR = re.compile(r"justpaste\.it|issuu\.com|zeemaps|linkcentre|number\.com", re.I)

WRONG_GEO = re.compile(r"egypt-business|\.co\.uk|houzz\.in|citiservi|cataloxy", re.I)

PARKED = re.compile(
    r"this domain (is|may be) for sale|buy this domain|domain for sale"
    r"|parked (free )?courtesy|godaddy\.com/domainsearch|hugedomains"
    r"|sedoparking|afternic|namecheap.*parking|under construction"
    r"|website coming soon", re.I)


def normalise(line):
    line = line.strip().strip(",")
    if not line or line.startswith("#"):
        return None
    # The list carries markdown links and bare hostnames side by side.
    m = re.search(r"\((https?://[^)]+)\)", line)
    if m:
        line = m.group(1)
    line = re.sub(r"^\[|\]$", "", line).strip()
    if not line.startswith(("http://", "https://")):
        line = "https://" + line
    return line


def check(url):
    out = {"url": url, "status": None, "final": "", "title": "", "verdict": "", "why": ""}
    host = re.sub(r"^https?://", "", url).split("/")[0]
    if NOT_A_DIR.search(host):
        out.update(verdict="NOT-A-DIR", why="a publishing or mapping tool, not a business directory")
        return out
    if WRONG_GEO.search(url):
        out.update(verdict="WRONG-GEO", why="country-specific, not US")
        return out
    if OFF_TRADE.search(host):
        out.update(verdict="OFF-TRADE", why="real site, different trade")
        # still fetch it, so the note carries evidence
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=25) as r:
            out["status"] = r.status
            out["final"] = r.geturl()
            body = r.read(120000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        out["status"] = e.code
        out["verdict"] = out["verdict"] or ("ERROR-%d" % e.code)
        out["why"] = out["why"] or "answered with an error page"
        return out
    except Exception as e:
        out["verdict"] = out["verdict"] or "DEAD"
        out["why"] = out["why"] or str(e)[:70]
        return out

    t = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    out["title"] = re.sub(r"\s+", " ", t.group(1)).strip()[:90] if t else ""
    if PARKED.search(body) or PARKED.search(out["title"]):
        out.update(verdict="PARKED", why="registrar or for-sale holding page")
    elif not out["verdict"]:
        out["verdict"] = "OK"
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python check_directories.py <file-with-one-url-per-line>")
    urls, seen = [], set()
    for line in open(sys.argv[1], encoding="utf-8"):
        u = normalise(line)
        if not u:
            continue
        host = re.sub(r"^https?://(www\.)?", "", u).split("/")[0].lower()
        if host in seen:
            continue
        seen.add(host)
        urls.append(u)
    print(f"{len(urls)} unique host(s) to check\n")

    results = []
    with cf.ThreadPoolExecutor(12) as ex:
        for i, r in enumerate(ex.map(check, urls), 1):
            results.append(r)
            print(f"  [{i}/{len(urls)}] {r['verdict']:10} {r['url'][:58]}")

    order = ["OK", "OFF-TRADE", "WRONG-GEO", "NOT-A-DIR", "PARKED", "DEAD"]
    print("\n" + "=" * 74)
    for v in order + sorted({r["verdict"] for r in results} - set(order)):
        group = [r for r in results if r["verdict"] == v]
        if group:
            print(f"{v:12} {len(group)}")
    json.dump(results, open("directory_check.json", "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print("\nwrote directory_check.json")
    usable = [r for r in results if r["verdict"] == "OK"]
    print(f"\n{len(usable)} worth opening. The rest are dead, parked, not "
          f"directories, or for another trade —\nand every one of those would "
          f"have cost the same evening as a live one.")


if __name__ == "__main__":
    main()
