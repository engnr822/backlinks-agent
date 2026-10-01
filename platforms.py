"""What can actually be automated, and what only looks like it can.

`python platforms.py` answers the question the directory list never did: of
everywhere a listing could go, which ones take a feed or a file, and which
ones need a person at a form. That distinction is the whole cost model.

A platform that reads a hosted feed is set up once and then maintains itself.
A bulk upload is one file for every business at once. A paid API syndicates to
dozens of directories and keeps them corrected, which is why ONE of those
replaces most of the manual rows. A form with a CAPTCHA is an afternoon per
listing, forever, and it is the least valuable of the four.
"""
import argparse
import json
import os

PLATFORMS_FILE = os.path.join("data", "platforms.json")

ORDER = ["hosted_feed", "bulk_upload", "paid_api", "manual_form", "excluded"]

# The question that decides whether a platform is usable at all for a business
# with no premises. "hide" is not the same as "not needed": most sites let you
# keep the address off the public page, but still make you type one in.
ADDRESS = {
    "no_address_needed": "NONE needed — usable today",
    "service_area_only": "no address field; service area only",
    "enter_then_hide":   "you must ENTER one, then it can be hidden",
}

EFFORT = {
    "hosted_feed": "publish one url  ->  maintains itself",
    "bulk_upload": "one file, every business  ->  repeat in minutes",
    "paid_api":    "costs money  ->  fully automatable AND syndicates onward",
    "manual_form": "a person, a form, a CAPTCHA  ->  every time",
    "excluded":    "deliberately not attempted",
}


def load():
    with open(PLATFORMS_FILE, encoding="utf-8") as f:
        return json.load(f)["platforms"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--channel", choices=ORDER, help="show only this channel")
    ap.add_argument("--todo", action="store_true",
                    help="only platforms nobody has checked yet")
    ap.add_argument("--no-address", action="store_true",
                    help="only platforms that need no address at all")
    ap.add_argument("--purpose", choices=["map_listing", "directory_profile"],
                    help="map_listing = a pin, needs an address and verification. "
                         "directory_profile = a public page with the NAP and a link.")
    args = ap.parse_args()

    rows = load()
    if args.channel:
        rows = [p for p in rows if p["channel"] == args.channel]
    if args.todo:
        rows = [p for p in rows if not p.get("checked")]
    if args.purpose:
        rows = [p for p in rows if p.get("purpose") == args.purpose]
    if args.no_address:
        rows = [p for p in rows if p.get("address_mode") in
                ("no_address_needed", "service_area_only")]

    for channel in ORDER:
        group = [p for p in rows if p["channel"] == channel]
        if not group:
            continue
        print(f"\n{channel.upper()}  —  {EFFORT[channel]}")
        print("-" * 78)
        for p in group:
            flag = "" if p.get("checked") else "   [unchecked]"
            print(f"  {p['name']}{flag}")
            print(f"      cost    {p['cost']}")
            print(f"      reaches {p['reaches']}")
            if p.get("purpose"):
                print(f"      purpose {p['purpose']}  ({p.get('value','?')})")
            if p.get("address_mode"):
                print(f"      address {ADDRESS[p['address_mode']]}")
            print(f"      service-area ok: {p.get('service_area_ok')}"
                  + (f"   (checked {p['checked']})" if p.get("checked") else ""))
            if p.get("how"):
                print(f"      how     {p['how']}")
            if p.get("note"):
                print(f"      note    {p['note']}")
            print()

    checked = sum(1 for p in load() if p.get("checked"))
    total = len(load())
    print("=" * 78)
    print(f"{checked}/{total} platform records verified.")
    print()
    print("Unchecked means SKIP, not 'probably fine'. Open the form once,")
    print("set service_area_ok and the date, and it stops being a question.")
    print()
    print("If the goal is automation rather than listings, the order that")
    print("matters is the one above: a hosted feed and a bulk upload cover")
    print("more ground in an afternoon than the whole manual_form list covers")
    print("in a month — and one paid_api replaces most of that list outright.")


if __name__ == "__main__":
    main()
