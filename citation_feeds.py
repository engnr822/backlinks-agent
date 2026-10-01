"""
citation_feeds.py
The part of citation building that IS fully automatable: bulk feeds.

Bing Places, Apple Business Connect, Yext, Uberall and the rest all accept a
spreadsheet of locations and create the listings themselves — no form, no
CAPTCHA, no per-directory account. One file, one upload, every business live
at once. That is the sanctioned path these platforms built for exactly this,
and it is the opposite of a bot filling in a signup form.

Two commands:

  python citation_feeds.py --master
      Writes feeds/nap_master.csv — every canonical field, one row per
      business. Paste columns from it into any template by hand.

  python citation_feeds.py --template bing_places
      Reads the platform's OWN header row from data/feed_templates/
      bing_places.txt and writes feeds/bing_places.csv matching it exactly,
      column for column. Download the template from the platform, paste its
      first line into that file, and this fills it.

The mapping is by column name, so a platform renaming "Zip" to "Postal code"
costs nothing. Anything it can't recognise is left blank and reported, so a
half-filled file never goes up silently.
"""

import csv
import json
import os
import sys

BUSINESSES_FILE = os.path.join("data", "businesses.json")
TEMPLATE_DIR = os.path.join("data", "feed_templates")
OUT_DIR = "feeds"

# Canonical fields, in the order they go into the master sheet.
FIELDS = [
    "business_id", "name", "street", "area", "city", "state", "postal",
    "country", "phone", "website", "category", "hours", "logo",
    "latitude", "longitude",
    "description_short", "description_medium", "description_long",
]

# Header synonyms platforms actually use. Lower-cased and stripped of
# punctuation before matching, so "Address Line 1" and "address_line1" are
# the same key.
SYNONYMS = {
    "name": ["business name", "name", "location name", "store name", "company",
             "company name", "brand name", "title"],
    "street": ["address", "address line 1", "address1", "street", "street address",
               "addressline1", "line 1"],
    "area": ["address line 2", "address2", "addressline2", "line 2", "district",
             "neighborhood", "neighbourhood", "area", "locality 2"],
    "city": ["city", "town", "locality"],
    "state": ["state", "province", "region", "state province", "emirate",
              "administrative area"],
    "postal": ["zip", "zip code", "postal", "postal code", "postcode",
               "zip postal code", "postal zip code", "zip postal"],
    "latitude": ["latitude", "lat", "geo latitude"],
    "longitude": ["longitude", "long", "lng", "lon", "geo longitude"],
    "country": ["country", "country code", "country region"],
    "phone": ["phone", "phone number", "telephone", "main phone", "primary phone",
              "contact number"],
    "website": ["website", "url", "web address", "site", "website url",
                "landing page url"],
    "category": ["category", "primary category", "business category", "categories",
                 "main category"],
    "hours": ["hours", "opening hours", "business hours", "hours of operation"],
    "logo": ["logo", "logo url", "image", "photo url"],
    "description_long": ["description", "business description", "long description",
                         "about", "summary"],
    "description_medium": ["short description", "medium description", "tagline",
                           "brief description"],
    "description_short": ["headline", "slogan", "very short description"],
    "business_id": ["store code", "location id", "store id", "external id",
                    "reference id", "code"],
}


def _norm(header: str) -> str:
    keep = [c.lower() if c.isalnum() else " " for c in header]
    return " ".join("".join(keep).split())


LOOKUP = {_norm(alias): field for field, aliases in SYNONYMS.items() for alias in aliases}


def rows(only: str = "") -> list[dict]:
    """One canonical row per business with a complete NAP block.

    `only` narrows by country, because one feed carrying every business is
    not always what you want to hand a platform: uploading the Dubai listing
    into a US account is noise at best, and a single public file that names
    all six US sites ties them to each other for anyone who reads it.
    """
    with open(BUSINESSES_FILE, "r", encoding="utf-8") as f:
        businesses = [b for b in json.load(f).get("businesses", [])
                      if b.get("enabled", True)]
    want = (only or "").strip().lower()
    if want and want != "all":
        groups = {"us": {"united states", "united states of america", "usa", "us"},
                  "ae": {"united arab emirates", "uae", "ae"}}
        allowed = groups.get(want, {want})
        businesses = [b for b in businesses
                      if str((b.get("nap") or {}).get("country", "")).lower() in allowed]

    try:
        with open(os.path.join("data", "citations_log.json"), "r", encoding="utf-8") as f:
            descriptions = json.load(f).get("descriptions", {})
    except (FileNotFoundError, json.JSONDecodeError):
        descriptions = {}

    out = []
    for business in businesses:
        nap = business.get("nap") or {}
        # A service-area business has no street and never will; requiring one
        # here dropped all six US sites out of every feed. Ask the registry
        # what THIS record needs instead of assuming every business has a door.
        import citations as _c
        if _c.missing_nap(business):
            print(f"  skipping {business['id']}: NAP incomplete "
                  f"(run python citations.py --status)")
            continue
        desc = descriptions.get(business["id"], {})
        out.append({
            "business_id": business["id"],
            "name": nap["listing_name"],
            "street": nap.get("street", ""),
            "area": nap.get("area", ""),
            "city": nap.get("city", ""),
            "state": nap.get("state", nap.get("city", "")),
            "postal": nap.get("postal", ""),
            "country": nap.get("country", ""),
            "phone": nap.get("phone", ""),
            "website": nap.get("website", ""),
            "category": business.get("primary_category", ""),
            "hours": nap.get("hours", ""),
            "logo": business.get("brand", {}).get("logo_url", ""),
            "latitude": nap.get("latitude", ""),
            "longitude": nap.get("longitude", ""),
            "description_short": desc.get("short", ""),
            "description_medium": desc.get("medium", ""),
            "description_long": desc.get("long", ""),
        })
    return out


def write_master(only: str = "") -> str:
    data = rows(only)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "nap_master.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(data)
    print(f"{path}: {len(data)} business(es), {len(FIELDS)} columns")
    return path


def preflight(name: str, only: str = "") -> None:
    """Stop before building a feed a platform is going to reject.

    data/platforms.json records whether a destination demands a street
    address. Six of the businesses here are service-area records with no
    street, on purpose. Building the CSV anyway produces a file that looks
    right, uploads, and fails on the far side -- or worse, invites someone to
    fill the blank in with an address that is not theirs.

    Reported, not enforced: the record may be out of date, and a stale note
    should not block a build. The point is that nobody finds out from the
    platform.
    """
    try:
        with open(os.path.join("data", "platforms.json"), encoding="utf-8") as f:
            known = {p["id"]: p for p in json.load(f)["platforms"]}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return
    rec = known.get(name)
    if not rec:
        print(f"  note: {name} is not in data/platforms.json — nothing known about it yet")
        return
    needs_street = str(rec.get("service_area_ok", "")).startswith("yes_but_address_required")         or rec.get("requires_street") is True
    if not needs_street:
        return
    blank = [r["business_id"] for r in rows(only) if not str(r.get("street") or "").strip()]
    if not blank:
        return
    print()
    print(f"  !! {rec['name']} requires a street address"
          + (f" (checked {rec['checked']})" if rec.get("checked") else ""))
    print(f"     {len(blank)} of these have none: {', '.join(blank)}")
    if rec.get("note"):
        print(f"     {rec['note']}")
    print("     The file will still be written. Expect it to be rejected, and")
    print("     do not fill the street in with an address that is not theirs.")
    print()


def write_for_template(name: str, only: str = "") -> str:
    template_path = os.path.join(TEMPLATE_DIR, f"{name}.txt")
    if not os.path.exists(template_path):
        sys.exit(
            f"No template at {template_path}.\n"
            f"Download the platform's own bulk template, copy its FIRST line "
            f"(the header row) and save it there — comma or tab separated, "
            f"exactly as the platform wrote it."
        )
    with open(template_path, "r", encoding="utf-8-sig") as f:
        line = f.readline().strip()
    delimiter = "\t" if "\t" in line else ","
    headers = [h.strip().strip('"') for h in line.split(delimiter) if h.strip()]

    preflight(name, only)
    data = rows(only)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.csv")

    unmapped = []
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(headers)
        for row in data:
            line_out = []
            for header in headers:
                field = LOOKUP.get(_norm(header))
                if field is None and header not in unmapped:
                    unmapped.append(header)
                line_out.append(row.get(field, "") if field else "")
            writer.writerow(line_out)

    mapped = len(headers) - len(unmapped)
    print(f"{path}: {len(data)} row(s), {mapped}/{len(headers)} columns filled")
    if unmapped:
        print("\nLeft blank — the platform asks for these and we have no field "
              "for them:")
        for header in unmapped:
            print(f"  - {header}")
        print("\nFill them in the sheet, or add the header to SYNONYMS in "
              "citation_feeds.py if it's one of ours under another name.")
    return path


def _header_of(downloaded: str) -> str:
    if not os.path.exists(downloaded):
        sys.exit(f"No such file: {downloaded}")

    # Bing hands out an .xlsx, not a CSV -- their bulk template is a workbook.
    # Telling someone to open it and Save As CSV first puts the whole thing
    # back behind a desktop spreadsheet, which is the wall this command exists
    # to remove. Read the workbook.
    if downloaded.lower().endswith((".xlsx", ".xlsm", ".xls")):
        try:
            import openpyxl
        except ImportError:
            sys.exit("Reading an .xlsx needs openpyxl:  pip install openpyxl")
        sheet = openpyxl.load_workbook(downloaded, read_only=True,
                                       data_only=True).worksheets[0]
        cells = []
        for row in sheet.iter_rows(min_row=1, max_row=1, values_only=True):
            cells = ["" if c is None else str(c).strip() for c in row]
        while cells and not cells[-1]:
            cells.pop()
        if not cells:
            sys.exit(f"{downloaded}: the first sheet's first row is empty.\n"
                     f"Is the header on a different sheet? Open it and check.")
        header = ",".join(f'"{c}"' if ("," in c or '"' in c) else c for c in cells)
    else:
        with open(downloaded, "r", encoding="utf-8-sig", newline="") as f:
            header = f.readline().strip("\r\n")
    if not header or "," not in header:
        sys.exit(f"{downloaded} does not start with a comma-separated header row.\n"
                 f"Read: {header[:120]!r}\n"
                 f"Is it an .xlsx? Open it and save as CSV first.")
    return header


def read_header(downloaded: str) -> str:
    """The platform's column names, out of whatever file it handed you."""
    return _header_of(downloaded)


def adopt_template(name: str, downloaded: str, only: str = "") -> str:
    """Take the header row straight out of the file the platform gave you.

    The manual step was: open the download, select the first line, do not
    accidentally include the second, save it in the right folder under the
    right name. That is four chances to produce a header nobody at the
    platform ever wrote, and the upload then fails or -- worse -- lands the
    wrong data in the wrong columns. Point this at the download instead.
    """
    header = _header_of(downloaded)
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    out = os.path.join(TEMPLATE_DIR, f"{name}.txt")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n")
    cols = [c.strip() for c in header.split(",")]
    print(f"{out}: {len(cols)} column(s) taken from {downloaded}")
    print("  " + " | ".join(cols[:8]) + (" | ..." if len(cols) > 8 else ""))
    return write_for_template(name, only)


def main():
    args = sys.argv[1:]
    only = ""
    if "--only" in args:
        i = args.index("--only")
        only = args[i + 1] if len(args) > i + 1 else ""
        del args[i:i + 2]
    if not args or args[0] == "--master":
        return write_master(only)
    if args[0] == "--template" and len(args) > 1:
        return write_for_template(args[1], only)
    if args[0] == "--from-template" and len(args) > 2:
        return adopt_template(args[1], args[2], only)
    if args[0] == "--header-only" and len(args) > 2:
        # Used by the Actions workflow: read the platform's column names out of
        # an uploaded file and write just that line, without building a feed.
        with open(args[2], "w", encoding="utf-8", newline="\n") as f:
            f.write(read_header(args[1]) + "\n")
        print(f"header written to {args[2]}")
        return None
    sys.exit("Usage:\n"
             "  python citation_feeds.py --master\n"
             "  python citation_feeds.py --template <name>\n"
             "  python citation_feeds.py --from-template <name> <downloaded.csv>\n"
             "\nAdd --only us (or ae, or all) to narrow which businesses go in.")


if __name__ == "__main__":
    main()
