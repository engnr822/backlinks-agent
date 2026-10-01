"""
nap_schema.py
Publishes each business's NAP as LocalBusiness JSON-LD for its own website.

Why this and not another directory
----------------------------------
Google and Bing don't count citations by adding them up. They reconcile an
entity: this name, at this address, on this phone, is the same business as
that Google profile and that Facebook page. The strongest signal in that
reconciliation is the business's OWN site saying it, in machine-readable
form, and agreeing with everything else — and that is the one surface here
nobody has to pay a platform for or ask permission to write to.

`sameAs` is the part that does the work. Every citation recorded with
`citations.py --done <business> <directory> <url>` is added to the list, so
the schema gets stronger on its own as the daily queue is worked through:
the site points at the profiles, the profiles point back at the site.

  python nap_schema.py

Writes feeds/schema/<id>.jsonld — drop it into that site's <head> inside a
<script type="application/ld+json"> tag, or have the site build read it.
"""

import json
import os

BUSINESSES_FILE = os.path.join("data", "businesses.json")
CITATIONS_LOG = os.path.join("data", "citations_log.json")
OUT_DIR = os.path.join("feeds", "schema")

# schema.org has specific types for some trades and only a general one for
# others. A specific type is worth using where it exists — it tells Google
# what the business does without relying on the text.
TYPE_BY_CATEGORY = {
    "plumber": "Plumber",
    "electrician": "Electrician",
    "handyman": "HomeAndConstructionBusiness",
    "locksmith": "Locksmith",
    "hvac contractor": "HVACBusiness",
    "house painter": "HousePainter",
    "roofing contractor": "RoofingContractor",
    "general contractor": "GeneralContractor",
    "moving company": "MovingCompany",
    "cleaning service": "HousePainter",
}
DEFAULT_TYPE = "LocalBusiness"

DAY_NAMES = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
             "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday",
             "Sun": "Sunday"}


def schema_type(business: dict) -> str:
    category = (business.get("primary_category") or "").lower()
    for key, value in TYPE_BY_CATEGORY.items():
        if key in category:
            return value
    # "Washer & dryer repair service", "Refrigerator repair service" and the
    # rest have no schema.org type of their own.
    if "repair" in category:
        return "HomeAndConstructionBusiness"
    return DEFAULT_TYPE


def opening_hours(hours: str) -> list[str]:
    """
    The stored hours line back into schema.org's openingHours strings.
    "Open 24 hours, 7 days a week" -> ["Mo-Su 00:00-23:59"].
    "Mon-Sat 08:00-20:00" -> ["Mo-Sa 08:00-20:00"].
    Anything we can't parse confidently is left out rather than guessed —
    wrong hours in structured data is worse than none.
    """
    hours = (hours or "").strip()
    if not hours:
        return []
    if "24 hours" in hours.lower() and "7 days" in hours.lower():
        return ["Mo-Su 00:00-23:59"]

    out = []
    for chunk in hours.split(";"):
        chunk = chunk.strip()
        if not chunk or "closed" in chunk.lower():
            continue
        parts = chunk.split()
        if len(parts) != 2 or "-" not in parts[1]:
            continue
        days, span = parts
        abbrev = []
        for day in days.split("-"):
            full = DAY_NAMES.get(day.strip()[:3].title())
            if not full:
                abbrev = []
                break
            abbrev.append(full[:2])
        if abbrev:
            out.append(f"{'-'.join(abbrev)} {span}")
    return out


def same_as(business_id: str, citations: dict) -> list[str]:
    """Live citation URLs recorded so far — the profiles that point back."""
    entries = citations.get("submitted", {}).get(business_id, {})
    return sorted(e["url"] for e in entries.values() if e.get("url"))


def build(business: dict, citations: dict) -> dict | None:
    nap = business.get("nap") or {}
    if not (nap.get("listing_name") and nap.get("street")):
        print(f"  skipping {business['id']}: NAP incomplete")
        return None

    doc = {
        "@context": "https://schema.org",
        "@type": schema_type(business),
        "name": nap["listing_name"],
        "url": nap.get("website", ""),
        "telephone": nap.get("phone", ""),
        "address": {
            "@type": "PostalAddress",
            "streetAddress": ", ".join(p for p in [nap.get("street"), nap.get("area")] if p),
            "addressLocality": nap.get("city", ""),
            "addressRegion": nap.get("state", ""),
            "postalCode": nap.get("postal", ""),
            "addressCountry": nap.get("country", ""),
        },
    }

    logo = (business.get("brand") or {}).get("logo_url")
    if logo:
        doc["image"] = logo
        doc["logo"] = logo
    if nap.get("latitude") and nap.get("longitude"):
        doc["geo"] = {"@type": "GeoCoordinates",
                      "latitude": nap["latitude"], "longitude": nap["longitude"]}
    hours = opening_hours(nap.get("hours", ""))
    if hours:
        doc["openingHours"] = hours
    if business.get("city"):
        doc["areaServed"] = {"@type": "City", "name": business["city"]}
    if business.get("focus"):
        doc["knowsAbout"] = business["focus"]

    links = same_as(business["id"], citations)
    if links:
        doc["sameAs"] = links

    return doc


def main():
    with open(BUSINESSES_FILE, "r", encoding="utf-8") as f:
        businesses = [b for b in json.load(f).get("businesses", [])
                      if b.get("enabled", True)]
    try:
        with open(CITATIONS_LOG, "r", encoding="utf-8") as f:
            citations = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        citations = {}

    os.makedirs(OUT_DIR, exist_ok=True)
    written = 0
    for business in businesses:
        doc = build(business, citations)
        if not doc:
            continue
        path = os.path.join(OUT_DIR, f"{business['id']}.jsonld")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        links = len(doc.get("sameAs", []))
        print(f"  {path}  ({doc['@type']}, {links} sameAs link(s))")
        written += 1

    if written:
        print(f"\n{written} file(s). Each goes in that site's <head>:")
        print('  <script type="application/ld+json"> ...file contents... </script>')
        print("\nThe sameAs list grows on its own — every citation you record "
              "with `citations.py --done` gets added the next time this runs.")


if __name__ == "__main__":
    main()
