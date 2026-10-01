"""Find each directory's real add-a-business URL, and whether it needs an account.

Two of the three things a pack asks you to record can be answered without
opening a browser, and answering them for 65 directories by hand is most of an
evening:

  submit_url       guessing it does not work -- /add-business, /AddBusiness.aspx
                   and /addbusiness.aspx are all somebody's convention and all
                   404 on the others. The link is on the home page; follow it.
  needs_account    a submit page that redirects to a login, or answers with a
                   password field, cannot be reached until somebody signs up.
                   That is a human step, so those directories are worth doing
                   in a separate batch from the ones that take a listing
                   straight away.

  python find_submit_urls.py            # every directory missing a submit_url
  python find_submit_urls.py --all      # re-check all of them
  python find_submit_urls.py --write    # save what it finds into directories.json

What it cannot answer is the third thing -- whether the street field is
mandatory -- because that is only visible on the form itself, and on the sites
behind a login it is not visible at all until you are in. Nothing here signs
up for anything.
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
DIRS = os.path.join("data", "directories.json")

# The link text these sites use for the same thing.
ADD_TEXT = re.compile(
    r"add\s+(a\s+|your\s+|new\s+)?(business|listing|company|site)"
    r"|list\s+(your\s+)?business|submit\s+(a\s+)?(business|listing|site|url)"
    r"|free\s+listing|claim\s+(your\s+)?business|get\s+listed|register\s+(your\s+)?business",
    re.I)


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.read(200000).decode("utf-8", "replace")


def looks_like_login(final_url, body):
    return (bool(re.search(r"type=[\"']?password", body, re.I))
            or re.search(r"/(login|signin|sign-in|account|register|signup|sign-up)\b",
                         final_url, re.I) is not None)


def form_size(body):
    fields = len(re.findall(r"<input[^>]+type=[\"']?(?:text|email|url|tel)", body, re.I))
    fields += len(re.findall(r"<textarea", body, re.I))
    return fields, len(re.findall(r"<select", body, re.I))


def examine(directory):
    out = {"id": directory["id"], "submit_url": "", "needs_account": None,
           "fields": 0, "note": ""}
    home = directory.get("url") or directory.get("submit_url") or ""
    if not home:
        out["note"] = "no url on the record"
        return out
    try:
        _, final, body = fetch(home)
    except urllib.error.HTTPError as e:
        out["note"] = f"home page answered HTTP {e.code}"
        return out
    except Exception as e:
        out["note"] = f"home page unreachable: {str(e)[:50]}"
        return out

    # Every anchor whose text OR href looks like the add-a-business link.
    best = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.S | re.I):
        href, text = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        if ADD_TEXT.search(text) or ADD_TEXT.search(href.replace("-", " ").replace("_", " ")):
            best.append(urllib.parse.urljoin(final, href))
    # Prefer the shortest: /add beats /add-business-to-our-directory-free.
    best = sorted(dict.fromkeys(best), key=len)
    if not best:
        out["note"] = "no add-a-business link found on the home page"
        return out

    for candidate in best[:3]:
        try:
            _, cfinal, cbody = fetch(candidate)
        except Exception:
            continue
        out["submit_url"] = cfinal
        out["needs_account"] = looks_like_login(cfinal, cbody)
        n, sel = form_size(cbody)
        out["fields"] = n
        out["note"] = ("redirects to a login — sign up first" if out["needs_account"]
                       else f"{n} text field(s), {sel} dropdown(s)" if n >= 3
                       else "reachable, but no obvious form on it")
        if not out["needs_account"] and n >= 3:
            break          # a real form: stop looking
    return out


def main():
    write = "--write" in sys.argv
    every = "--all" in sys.argv
    with open(DIRS, encoding="utf-8") as f:
        data = json.load(f)
    todo = [d for d in data["directories"]
            if every or not d.get("submit_url") or d["submit_url"] == d.get("url")]
    print(f"{len(todo)} directory record(s) to look at\n")

    found = {}
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(examine, todo):
            found[r["id"]] = r
            flag = ("LOGIN " if r["needs_account"] else
                    "OPEN  " if r["submit_url"] and r["fields"] >= 3 else "      ")
            print(f"  {flag}{r['id']:26} {r['submit_url'][:52] or '-'}")
            if r["note"] and not r["submit_url"]:
                print(f"        {r['note']}")

    openable = [r for r in found.values() if r["submit_url"] and not r["needs_account"] and r["fields"] >= 3]
    walled = [r for r in found.values() if r["needs_account"]]
    print("\n" + "=" * 70)
    print(f"{len(openable):3} take a listing without signing in  <- start here")
    print(f"{len(walled):3} need an account first")
    print(f"{len(found) - len(openable) - len(walled):3} no form found from the home page")

    if not write:
        print("\n(nothing written — add --write to save these into directories.json)")
        return
    for d in data["directories"]:
        r = found.get(d["id"])
        if not r or not r["submit_url"]:
            continue
        d["submit_url"] = r["submit_url"]
        d["needs_account"] = bool(r["needs_account"])
    with open(DIRS, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"\nwrote {DIRS}")


if __name__ == "__main__":
    main()
