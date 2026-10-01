"""
citations.py
One citation a day, worked through in a fixed order, with the same NAP every
single time.

Why it works this way
---------------------
A citation is only worth having if it matches. Twenty listings that each spell
the address slightly differently are worse than five that agree, because the
disagreement is what tells Google your data is unreliable. So there is exactly
one canonical record per business — the `nap` block in data/businesses.json —
and every pack this script prints is rendered from it. Nothing is retyped, so
nothing drifts.

What the daily job does and does not do
---------------------------------------
It picks the next (business, directory) pair, renders every field that
directory asks for, and hands it over as a ready-to-paste pack (the workflow
turns it into a GitHub issue). You paste and submit.

It does NOT create accounts, solve CAPTCHAs, or submit forms on directories.
That is not a limitation of the code — those directories forbid bot submission
in their terms, and a burst of automated submissions is itself the spam
signal that gets listings removed. Done by hand at one a day, the same
listings look like a business slowly putting itself on the map, which is what
they are.

The `api` channel targets (Bing Places, Apple Business Connect, Facebook,
Foursquare) do have sanctioned APIs and bulk feeds. Those can be automated
end to end once their credentials are added; the pack marks them so you know
which ones are worth wiring up.

Usage:
  python citations.py            # today's pack
  python citations.py --status   # what is done, what is left
  python citations.py --done <business_id> <directory_id> <live_url>
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

BUSINESSES_FILE = os.path.join("data", "businesses.json")
DIRECTORIES_FILE = os.path.join("data", "directories.json")
LOG_FILE = os.path.join("data", "citations_log.json")

# Every field a directory can ask for. A business missing any of these gets
# skipped rather than submitted half-right — a wrong address on a citation is
# worse than no citation, because you then have to hunt it down and correct it.
REQUIRED_NAP = ["listing_name", "street", "area", "city", "country", "phone", "website"]

# A business that has premises and one that only covers an area are not the
# same record with a field left blank. The first is verified at a door; the
# second is verified by phone or email and names a city, a state and the
# postcodes it covers. `area` is a Dubai district and has no US counterpart,
# so it is not required of one.
REQUIRED_SERVICE_AREA = ["listing_name", "city", "state", "postal",
                         "country", "phone", "website"]


def _load(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else {}


def _save_log(log: dict):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(LOG_FILE), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(temporary, LOG_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)



def businesses() -> list[dict]:
    return [b for b in _load(BUSINESSES_FILE).get("businesses", []) if b.get("enabled", True)]


def directories() -> list[dict]:
    dirs = _load(DIRECTORIES_FILE).get("directories", [])
    return sorted(dirs, key=lambda d: (d.get("tier", 9), d["id"]))


def missing_nap(business: dict) -> list[str]:
    nap = business.get("nap") or {}
    if business.get("location_type", "premises") == "service_area":
        gaps = [f for f in REQUIRED_SERVICE_AREA if not str(nap.get(f) or "").strip()]
        # A street on a service-area record is not a bonus, it is the mistake
        # this whole distinction exists to prevent: the business has no
        # premises, so any street line on it belongs to somebody else. Report
        # it as a defect so the record is skipped instead of submitted.
        if str(nap.get("street") or "").strip():
            gaps.append("street must be empty for a service_area business")
        return gaps
    return [f for f in REQUIRED_NAP if not str(nap.get(f) or "").strip()]


_US = {"united states", "united states of america", "usa", "us"}


def full_address(nap: dict) -> str:
    """One line, in the form the country actually writes addresses in.

    "Al Barsha South - Dubai - United Arab Emirates" is right for Dubai and
    wrong everywhere else; a US listing wants "Yakima, WA 98901". A
    service-area record has no street, so the line simply starts at the city.
    """
    if (nap.get("country") or "").strip().lower() in _US:
        head = ", ".join(p for p in (nap.get("street"), nap.get("city")) if p)
        tail = " ".join(p for p in (nap.get("state"), nap.get("postal")) if p)
        return f"{head} {tail}".strip() if tail else head
    parts = [nap.get("street"), nap.get("area"), nap.get("city"),
             nap.get("postal"), nap.get("country")]
    return " - ".join(p for p in parts if p)


# ---------------------------------------------------------------
# The queue
# ---------------------------------------------------------------

def next_target(log: dict, verification: str | None = None,
                country: str = "") -> tuple[dict, dict] | None:
    """
    The next (business, directory) pair. Businesses take turns — the one with
    the fewest submissions goes next — so all five climb together instead of
    one finishing every directory while the others sit at zero.
    """
    ready = [b for b in businesses() if not missing_nap(b)]
    # Two tracks share this registry -- the Dubai listings and the US
    # pay-per-call sites -- and they are worked on at different times. Without
    # this the round-robin interleaves them and the first pack of a US push
    # comes out for Dubai.
    want = (country or "").strip().lower()
    if want and want != "all":
        groups = {"us": {"united states", "united states of america", "usa", "us"},
                  "ae": {"united arab emirates", "uae", "ae"}}
        allowed = groups.get(want, {want})
        ready = [b for b in ready
                 if str((b.get("nap") or {}).get("country", "")).lower() in allowed]
    if not ready:
        return None

    done = log.get("submitted", {})
    pending = log.get("pending", {})
    ready.sort(key=lambda b: (
        len(set(done.get(b["id"], {})) | set(pending.get(b["id"], {}))), b["id"]))

    for business in ready:
        already = done.get(business["id"], {})
        for directory in _by_effort(directories()):
            if verification and directory.get("verify", "unknown") != verification:
                continue
            if not eligible(business, directory):
                continue
            if (directory["id"] not in already
                    and directory["id"] not in pending.get(business["id"], {})):
                return business, directory
    return None


def _by_effort(dirs: list[dict]) -> list[dict]:
    """Cheapest first: a directory that needs no account before one that does.

    The one citation that went live end to end was zearches, and what made it
    work was not the recipe — it was that the site asked for no account and no
    email confirmation. Those are the ones to exhaust first: they are the only
    ones that can go from pack to live listing in a single sitting.

    A directory whose account has been made is as cheap as an open one from
    here on, so `account_ready` moves it back up. `needs_account` unknown sits
    between the two: it might be either, and finding out is itself the work.
    """
    def rank(d):
        if d.get("needs_account") is False:
            return 0
        if d.get("account_ready") is True:
            return 1
        if d.get("needs_account") is None:
            return 2
        return 3                      # needs an account, none made yet
    # TIER FIRST, then effort. Ordering by effort alone put every no-account
    # directory ahead of every good one, which is how the first live citation
    # ended up on a site that noindexes the page and nofollows the link. An
    # afternoon on Houzz is worth more than a week on the long tail, so the
    # cheapness of a directory only decides ties within a tier.
    return sorted(dirs, key=lambda d: (int(d.get("tier", 9)), rank(d), d["id"]))


def set_account_ready(directory_id: str, ready: bool = True):
    """Record that the account for this directory now exists.

    Nothing can detect this on its own: the account lives on their site and
    its password lives in a browser profile that is deliberately not in this
    repo. So it is stated once, here, and the queue stops treating that
    directory as blocked.
    """
    path = DIRECTORIES_FILE
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for d in data["directories"]:
        if d["id"] == directory_id:
            d["account_ready"] = bool(ready)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print(f"{directory_id}: account_ready = {bool(ready)}")
            print("Commit data/directories.json so the scheduled run sees it.")
            return
    raise ValueError(f"Unknown directory: {directory_id}")


def eligible(business: dict, directory: dict) -> bool:
    """Is this pair worth issuing at all?

    Two filters, both of which the registry could not express before and both
    of which produce a pack that wastes somebody's afternoon when they are
    missing.

    COUNTRY. Six of the directories are UAE-only. Nothing recorded that, and
    every enabled business was paired with every directory, so the first run
    after a US business was added would have issued "Add Yakima Electricians
    to Yalwa UAE" — and since a pending pair never expires, that pair would
    have sat in the queue permanently.

    STREET. A service-area business has no street address, on purpose: a city
    and a postcode with no street line is an incomplete address, while a
    street line that is not the business's own is a false one. A directory
    that makes the street field mandatory is therefore one to skip, not one to
    improvise in.

    Missing metadata is "skip", never "assume fine" — the same rule the
    delivery doc already applies to `verify`. You audit a directory once, by
    opening its form, before it is ever queued.
    """
    dir_country = (directory.get("country") or "").strip()
    biz_country = (business.get("nap", {}).get("country") or "").strip()
    if dir_country != "*":
        if not dir_country or dir_country.lower() != biz_country.lower():
            return False
    if business.get("location_type", "premises") == "service_area":
        street = directory.get("requires_street", "unknown")
        if street is True:
            return False
        if street == "unknown":
            # "Unknown means skip" was written for map platforms, where a wrong
            # guess costs a verification failure or a suspension. It is the
            # wrong trade on a tier-3 directory profile: finding out at the
            # form takes thirty seconds, while a separate audit pass doubles
            # the work for no safety gained. So the pack IS the audit -- it is
            # issued with a line saying what to check, and if the street field
            # turns out to be mandatory the answer gets recorded and that
            # directory drops out for good.
            return int(directory.get("tier", 1)) >= 3
    return True


def mark_done(business_id: str, directory_id: str, live_url: str = ""):
    if business_id not in {b["id"] for b in businesses()}:
        raise ValueError(f"Unknown enabled business: {business_id}")
    if directory_id not in {d["id"] for d in directories()}:
        raise ValueError(f"Unknown directory: {directory_id}")
    from urllib.parse import urlparse
    parsed = urlparse(live_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A live http(s) listing URL is required to mark a citation done")
    log = _load(LOG_FILE, {})
    log.get("pending", {}).get(business_id, {}).pop(directory_id, None)
    log.setdefault("submitted", {}).setdefault(business_id, {})[directory_id] = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "url": live_url,
    }
    _save_log(log)
    print(f"Recorded: {business_id} -> {directory_id}"
          + (f" ({live_url})" if live_url else ""))


# ---------------------------------------------------------------
# The pack
# ---------------------------------------------------------------

def descriptions(business: dict) -> dict:
    """
    Three lengths, written once and then reused for every directory forever.
    Cached in the log because consistency matters more than freshness here:
    the same business described three different ways across three directories
    reads like three different businesses.
    """
    mode = os.environ.get('CITATION_DESCRIPTION_MODE', 'registry').strip().lower()
    if mode == 'registry':
        from description_templates import registry_descriptions
        return registry_descriptions(business)
    if mode != 'claude':
        raise ValueError('CITATION_DESCRIPTION_MODE must be registry or claude')
    log = _load(LOG_FILE, {})
    cached = log.get("descriptions", {}).get(business["id"])
    if cached:
        return cached

    try:
        from llm import _call_claude
    except ImportError:
        return {}

    nap = business["nap"]
    system_prompt = (
        f"You write business directory descriptions for {nap['listing_name']}, "
        f"a {business.get('industry', 'local services')} business in "
        f"{nap.get('city', 'Dubai')}. Plain, factual, no marketing padding, no "
        "invented awards, certifications, prices or years in business."
    )
    user_prompt = f"""Business: {nap['listing_name']}
Category: {business.get('primary_category', business.get('industry'))}
Services: {', '.join(business.get('focus', [])) or business.get('industry', '')}
Area served: {nap.get('area')}, {nap.get('city')}
Website: {nap.get('website')}

Write three descriptions of the SAME business, each self-contained:
  short  - max 150 characters
  medium - max 300 characters
  long   - max 750 characters

Rules: no phone number, no email, no URL inside the text. No superlatives you
cannot support ("best in Dubai", "award-winning"). Name the actual services.
Respond with ONLY valid JSON: {{"short": "...", "medium": "...", "long": "..."}}"""

    raw = _call_claude(system_prompt, user_prompt, max_tokens=700).strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print("Description JSON unusable — leaving the pack without them.")
        return {}

    log.setdefault("descriptions", {})[business["id"]] = result
    _save_log(log)
    return result


def build_pack(business: dict, directory: dict) -> str:
    nap = business["nap"]
    desc = descriptions(business)
    hours = nap.get("hours", "")
    channel_note = (
        "This platform has a sanctioned API or bulk feed — worth wiring up once "
        "so it updates itself."
        if directory.get("channel") == "api" else
        "Use the audited browser recipe below when available; otherwise inspect "
        "the directory form and fill it manually. Directory eligibility and "
        "verification requirements must be checked before submission."
    )

    lines = [
        f"# Add **{nap['listing_name']}** to **{directory['name']}**",
        "",
        f"Submit at: {directory['submit_url']}",
        "",
        f"_{directory.get('notes', '')}_",
        "",
        f"> {channel_note}",
        "",
        # The audit and the submission are the same visit. Anything learned at
        # the form gets recorded, so the next business on this directory does
        # not re-learn it.
        *(["**This directory has not been audited yet. While you are on the "
           "form, note three things and put them in `data/directories.json`:**",
           "",
           "- `requires_street` — is the street field mandatory? If yes, set it "
           "`true` and this directory drops out for every service-area "
           "business. **Do not fill it in with an address that is not theirs.**",
           "- `verify` — `email`, `phone` or `none`.",
           "- `submit_url` — the real add-a-business URL, not the home page.",
           ""]
          if directory.get("requires_street", "unknown") == "unknown" else []),
        "## Copy these exactly — character for character",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Business name | `{nap['listing_name']}` |",
    ]
    # A service-area business has no street and no district. Printing those
    # rows empty invites whoever is filling the form to put something in them,
    # which is the one thing that turns an incomplete address into a false one.
    if business.get("location_type", "premises") == "service_area":
        lines += [
            f"| Street | _leave blank — this business has no premises_ |",
            f"| City | `{nap['city']}` |",
            f"| State | `{nap.get('state', '')}` |",
            f"| Postal code | `{nap.get('postal', '')}` |",
        ]
        area = nap.get("service_area") or business.get("service_area") or []
        if area:
            lines.append("| Service area | `" + ", ".join(str(z) for z in area) + "` |")
    else:
        lines += [
            f"| Street | `{nap['street']}` |",
            f"| Area / district | `{nap['area']}` |",
            f"| City | `{nap['city']}` |",
            f"| Postal code | `{nap.get('postal', '')}` |",
        ]
    lines += [
        f"| Country | `{nap['country']}` |",
        f"| Full address (single line) | `{full_address(nap)}` |",
        f"| Phone | `{nap['phone']}` |",
        f"| Website | `{nap['website']}` |",
        f"| Category | `{business.get('primary_category', '')}` |",
        f"| Hours | `{hours}` |",
    ]
    if nap.get("email"):
        lines.append(f"| Email | `{nap['email']}` |")
    from pathlib import Path
    recipe_path = Path(__file__).resolve().parent / 'recipes' / (directory['id'] + '.json')
    if business['id'] == 'yakima' and recipe_path.is_file():
        recipe = _load(str(recipe_path), {})
        if recipe.get('enabled') is True:
            lines += ["", "## Browser-assisted submission", "",
                      "Run locally from the repository. Review the form before submitting; this is not an unattended Action.",
                      "```powershell",
                      f"python browser_submit.py --business yakima --recipe recipes/{directory['id']}.json",
                      "```", "After the runner verifies the public listing, run the same command with `--sync`.",
                      "Commit the resulting citation log to share completion with the daily queue."]
    if business.get("brand", {}).get("logo_url"):
        lines.append(f"| Logo | {business['brand']['logo_url']} |")

    if desc:
        lines += [
            "",
            "## Description — use the one that fits the field limit",
            "",
            f"**Short (≤150)**\n\n> {desc.get('short', '')}",
            "",
            f"**Medium (≤300)**\n\n> {desc.get('medium', '')}",
            "",
            f"**Long (≤750)**\n\n> {desc.get('long', '')}",
        ]

    lines += [
        "",
        "## The one rule",
        "",
        "Do not improve the name, shorten the street, or reformat the phone. "
        "Whatever a directory shows has to match the Business Profile exactly — "
        "a citation that disagrees is worse than no citation at all.",
        "",
        "## When it's live",
        "",
        "```bash",
        f"python citations.py --done {business['id']} {directory['id']} <live-url>",
        "```",
        "",
        "Then commit `data/citations_log.json`. Close this issue.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------
# Status
# ---------------------------------------------------------------

def print_status():
    log = _load(LOG_FILE, {})
    done = log.get("submitted", {})
    all_dirs = directories()
    print(f"{len(all_dirs)} directories configured\n")
    for business in businesses():
        gaps = missing_nap(business)
        if gaps:
            print(f"  {business['id']:13} NAP incomplete — missing: {', '.join(gaps)}")
            continue
        count = len(done.get(business["id"], {}))
        waiting = len(log.get("pending", {}).get(business["id"], {}))
        usable = sum(1 for d in all_dirs if eligible(business, d))
        note = "" if usable else "   <- 0 eligible directories, run --audit"
        print(f"  {business['id']:13} {count}/{usable} submitted, "
              f"{waiting} pending, {usable} eligible{note}")
    pending = [b["id"] for b in businesses() if missing_nap(b)]
    if pending:
        print(f"\nFill the `nap` block in data/businesses.json for: {', '.join(pending)}")
        print("Nothing is submitted for a business until its address is complete —"
              " a wrong citation takes longer to clean up than it took to make.")


def print_audit():
    """Which directory records still have metadata nobody has checked.

    A service-area business is paired with nothing until `requires_street` is
    an actual false, so on a fresh registry every US site reports 0 eligible
    directories and the queue looks broken. It is not: it is refusing to guess
    on your behalf. This prints the exact list to go and look at, once.
    """
    rows = []
    for d in directories():
        gaps = [k for k in ("country", "requires_street", "verify")
                if d.get(k, "unknown") in (None, "", "unknown")]
        if gaps:
            rows.append((d["id"], d.get("submit_url") or d.get("url", ""), gaps))
    if not rows:
        print("Every directory record is audited.")
        return
    print(f"{len(rows)} directory record(s) still carry unchecked metadata.")
    print("Open each form once and record what it actually demands:\n")
    for did, url, gaps in rows:
        print(f"  {did:18} {', '.join(gaps)}")
        print(f"  {'':18} {url}")
    print("\n  country          the country this directory serves, or * for any")
    print("  requires_street  true if the street field is mandatory. A")
    print("                   service-area business is skipped where it is —")
    print("                   that field is the line between an incomplete")
    print("                   address and a false one.")
    print("  verify           email | phone | none")
    print("\nUnknown means skip, never 'probably fine'.")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--status":
        return print_status()
    if args and args[0] == "--account-ready":
        if len(args) < 2:
            sys.exit("Usage: python citations.py --account-ready <directory_id> [no]")
        return set_account_ready(args[1], (args[2].lower() not in ("no", "false", "0"))
                                 if len(args) > 2 else True)
    if args and args[0] == "--audit":
        return print_audit()
    if args and args[0] == "--done":
        if len(args) < 3:
            sys.exit("Usage: python citations.py --done <business_id> <directory_id> <url>")
        return mark_done(args[1], args[2], args[3] if len(args) > 3 else "")

    log = _load(LOG_FILE, {})
    target = next_target(log)
    if not target:
        print("Nothing to submit today — every ready business is on every "
              "directory, or no business has a complete `nap` block yet.")
        print_status()
        return

    business, directory = target
    pack = build_pack(business, directory)
    print(pack)

    # The workflow reads these to title and file the issue.
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"title=Citation: add {business['nap']['listing_name']} "
                    f"to {directory['name']}\n")
            f.write(f"business={business['id']}\n")
            f.write(f"directory={directory['id']}\n")
    with open("citation_pack.md", "w", encoding="utf-8") as f:
        f.write(pack)


if __name__ == "__main__":
    main()
