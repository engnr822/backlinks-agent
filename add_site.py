"""Put a newly built site into the citation queue, in one command.

The registry was hand-edited JSON, which is the step that quietly stops a
pipeline: a site goes live, the queue does not know about it, and three weeks
later nobody remembers to add it. A new site should enter the system the day
it ships.

    python add_site.py \\
        --id yakima --name "Yakima Electricians" \\
        --site https://yakimaelectricians.com \\
        --phone "(509) 992-1165" --city Yakima --state WA --zip 98901 \\
        --category Electrician \\
        --zips 98901,98902,98903,98904,98907,98908,98909

Everything it writes is either given on the command line or derived from it.
Nothing is invented: no street address (these are service-area businesses and
that is the whole point), no hours, no guessed category.

The description follows the same sentence every other site here uses, and it
says what the business is: a referral service that does not do the work. That
line is not decoration -- it is the sentence that keeps a directory listing
honest about a site with no premises and no licence.

  --dry-run   print the record and change nothing
  --check     validate against the live site: does the phone actually appear
              on it, does the domain resolve
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.request

BUSINESSES = os.path.join("data", "businesses.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def e164(phone, country="US"):
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return ""


def display(phone):
    d = re.sub(r"\D", "", phone)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else phone.strip()


def check_live(site, phone_display, phone_e164_):
    """The two mistakes worth catching before a number reaches 20 directories.

    A citation carries the phone to places that are slow to correct, so it is
    worth thirty seconds to confirm the site actually shows that number. The
    Clovis site publishes an email at a domain that was never registered; the
    same class of mistake with a phone number is far more expensive.
    """
    try:
        req = urllib.request.Request(site, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read(400000).decode("utf-8", "replace")
    except Exception as e:
        print(f"  ! could not read {site}: {str(e)[:60]}")
        return False
    ok = True
    if phone_display in body or phone_e164_ in body or re.sub(r"\D", "", phone_display) in re.sub(r"\D", "", body):
        print(f"  ok  {phone_display} appears on the live site")
    else:
        print(f"  !   {phone_display} does NOT appear on {site}")
        print("      A citation puts this number somewhere slow to correct.")
        ok = False
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']+)', body, re.I)
    if m:
        print(f"  ok  meta description: {m.group(1)[:70]}")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="short key, e.g. yakima")
    ap.add_argument("--name", required=True, help="exact listing name")
    ap.add_argument("--site", required=True)
    ap.add_argument("--phone", required=True)
    ap.add_argument("--city", required=True)
    ap.add_argument("--state", required=True, help="two letters, e.g. WA")
    ap.add_argument("--zip", required=True, dest="postal",
                    help="ONE primary postcode — the same one everywhere. "
                         "Rotating it makes aggregators read two entities.")
    ap.add_argument("--category", required=True, help="e.g. Electrician, Plumber")
    ap.add_argument("--zips", default="", help="the service-area postcodes, comma separated")
    ap.add_argument("--email", default="")
    ap.add_argument("--owner", default="Muhammad Naseem Aslam")
    ap.add_argument("--country", default="United States")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    site = a.site.rstrip("/")
    domain = re.sub(r"^https?://(www\.)?", "", site)
    phone_d = display(a.phone)
    phone_e = e164(a.phone)
    if not phone_e:
        sys.exit(f"{a.phone!r} is not a 10-digit US number.")

    record = {
        "id": a.id,
        "enabled": True,
        "location_type": "service_area",
        "primary_category": a.category,
        "site": site,
        "contact_person": a.owner,
        "citation_description": (
            f"{a.name} connects customers in {a.city}, {a.state} with independent "
            f"local service providers. This website is a referral service and does "
            f"not perform contracting work."),
        "nap": {
            "_comment": ("Pay-per-call referral site. Street and area stay empty on "
                         "purpose: a city and a postcode with no street line is an "
                         "incomplete address, a street line that is not ours is a "
                         "false one."),
            "listing_name": a.name,
            "street": "",
            "area": "",
            "city": a.city,
            "state": a.state.upper(),
            "postal": a.postal,
            "country": a.country,
            "phone": phone_d,
            "phone_e164": phone_e,
            "website": site,
            "email": a.email or f"info@{domain}",
            "hours": "",
            "service_area": [z.strip() for z in a.zips.split(",") if z.strip()],
        },
    }

    print(json.dumps(record, indent=2, ensure_ascii=False))
    print()

    if a.check:
        print(f"checking {site} ...")
        check_live(site, phone_d, phone_e)
        print()

    if a.dry_run:
        print("DRY RUN — nothing written.")
        return

    with io.open(BUSINESSES, encoding="utf-8") as f:
        data = json.load(f)
    if any(b["id"] == a.id for b in data["businesses"]):
        sys.exit(f"'{a.id}' is already in {BUSINESSES}. Edit it there instead.")
    data["businesses"].append(record)
    with io.open(BUSINESSES, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    import citations
    n = sum(1 for d in citations.directories() if citations.eligible(record, d))
    print(f"added to {BUSINESSES} — {n} eligible directories, queued from tomorrow.")
    print("Commit data/businesses.json so the scheduled run picks it up.")
    print(f"\nFirst, confirm the number rings:  {phone_e}")
    print("A citation puts it where it is slow to correct.")


if __name__ == "__main__":
    main()
