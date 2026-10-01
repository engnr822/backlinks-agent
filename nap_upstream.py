"""Keep the premises businesses' NAP identical to the poster repo's copy.

Splitting citations into its own repo creates exactly one hazard: two copies
of the same address. Directories are reconciled on an entity — this name, at
this address, on this phone — so a registry that drifts from the one the
Google Business Profile syncs into is worse than no registry at all.

So it is not copied. `sync_nap.py` stays in the poster repo, where the GBP
OAuth credentials live, and keeps writing that repo's data/businesses.json
from each Business Profile every morning. This pulls the `nap` block back out
of that file for every business present in BOTH registries, and writes only
the fields that already exist here.

  premises businesses (Dubai)     -> upstream is the source of truth
  service_area businesses (US)    -> authored here; there is no GBP to sync

Never adds or removes a business, never touches a service_area record, never
writes anything if the fetch fails. A bad morning leaves yesterday's correct
addresses in place rather than half of today's.
"""
import argparse
import json
import os
import sys
import urllib.request

# The contents API, not raw.githubusercontent.com: the poster repo is
# private, and raw ignores a Bearer token and answers 404. With
# `Accept: application/vnd.github.raw` this endpoint returns the file itself.
DEFAULT_UPSTREAM = (
    "https://api.github.com/repos/clickfrauddetection/"
    "social-media-posts-agent/contents/data/businesses.json?ref=main"
)
LOCAL = os.path.join("data", "businesses.json")


def fetch(url, token=""):
    req = urllib.request.Request(url, headers={
        "User-Agent": "citations-agent",
        "Accept": "application/vnd.github.raw",
    })
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def merge(local, upstream):
    up = {b["id"]: b for b in upstream.get("businesses", [])}
    changes = []
    for business in local.get("businesses", []):
        if business.get("location_type", "premises") == "service_area":
            continue
        source = up.get(business["id"])
        if not source:
            continue
        nap, src_nap = business.setdefault("nap", {}), source.get("nap") or {}
        for field, new in src_nap.items():
            if field.startswith("_"):
                continue
            old = nap.get(field)
            # Only fields this registry already tracks, and only real values:
            # an upstream blank must not wipe an address that is correct here.
            if field in nap and str(new or "").strip() and old != new:
                nap[field] = new
                changes.append(f"{business['id']}.{field}: {old!r} -> {new!r}")
    return changes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=os.environ.get("NAP_UPSTREAM_URL", DEFAULT_UPSTREAM))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(LOCAL, encoding="utf-8") as f:
        local = json.load(f)

    try:
        upstream = fetch(args.url, os.environ.get("UPSTREAM_TOKEN", ""))
    except Exception as err:
        # Non-fatal on purpose: the queue can run all day on the addresses it
        # already has. Failing the workflow here would stop citations over a
        # network blip.
        print(f"upstream unreachable ({str(err)[:90]}) — keeping the local registry")
        return 0

    changes = merge(local, upstream)
    if not changes:
        print("every premises business already matches upstream")
        return 0

    for line in changes:
        print("  " + line)
    if args.dry_run:
        print(f"\nDRY RUN — {len(changes)} field(s) would change")
        return 0

    with open(LOCAL, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(local, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{len(changes)} field(s) updated from upstream")
    return 0


if __name__ == "__main__":
    sys.exit(main())
