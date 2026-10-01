# Handoff — what moved, what changed, and what is left

Written for whoever picks this up next, including Codex, which had been
working on the citation queue inside
`clickfrauddetection/social-media-posts-agent`.

**Nothing you wrote was discarded.** Commit `32eb714` ("Fix citation queue
advancement and recover existing issue deliveries") is the base this repo was
cut from — the delivery queue, the stable issue marker, the
closed-is-not-published rule, the recovery-after-failed-state-push, and its
seven tests all came across intact and still pass.

---

## Your unpushed work in the old repo

`32eb714` is still **local only** in `C:/Users/HP/social-media-posts-agent`,
and that checkout is `ahead 1, behind 10`. The ten commits you do not have are
all `chore: update posted log [skip ci]` from the daily poster; none of them
touches a citation file, so the rebase is clean:

```bash
cd /c/Users/HP/social-media-posts-agent
git pull --rebase origin main
git push origin main
```

Worth doing even though citations moved here: that commit also contains the
`CITATION_AUTOMATION.md` reasoning, and the old repo should not be left
carrying an unpushed commit nobody remembers.

---

## What came across, and what deliberately did not

| Came | Why |
|---|---|
| `citations.py`, `citation_queue.py` | the queue itself |
| `citation_feeds.py` | the automatable half — bulk CSV feeds |
| `nap_schema.py` | LocalBusiness JSON-LD per site |
| `tests/test_citation_queue.py` | your seven, plus ten new |
| `CITATION_AUTOMATION.md` | unchanged |

| Stayed behind | Why |
|---|---|
| `sync_nap.py` | imports `gbp_business` and `poster_gmb` — the GBP OAuth stack |
| `add_business.py` | imports `build_queue`, `gbp_business`, plus PIL |

`sync_nap.py` keeps running in the poster repo. `nap_upstream.py` here can
read its output by hand if a Dubai address ever changes, but it is NOT in the
daily workflow — this repo does not depend on that one to run.

The only code-level tie to the poster was one lazy import,
`from content_generator import _call_claude`. That is now `llm.py`.

---

## Why the split happened, in one paragraph

`data/businesses.json` is read by ten modules in the old repo, and
`gbp_business.load_businesses()` is:

```python
return [b for b in data.get("businesses", []) if b.get("enabled", True)]
```

No filter. Adding a US pay-per-call site to that file would have started
posting to Google Business Profile for six businesses that have no address and
no profile. A GBP suspension attaches to the **account**, so it would have
taken the five Dubai listings with it. Splitting removes the hazard entirely —
the US records never enter the repo where that code lives.

---

## What changed in the code you wrote

Five additions. Each names the failure it prevents, and each has a test.

### 1. `location_type` — two kinds of business

`premises` (the five Dubai businesses) and `service_area` (the six US sites).
These are different records, not one record with a field left blank.

```python
REQUIRED_NAP          = [listing_name, street, area, city, country, phone, website]
REQUIRED_SERVICE_AREA = [listing_name, city, state, postal, country, phone, website]
```

`missing_nap()` picks by `location_type`, defaulting to `premises`, so the
five existing records behave exactly as before.

**A service_area record carrying a street is reported as a defect**, not
accepted as a bonus. A city and a postcode with no street line is an
*incomplete* address; a street line that is not the business's own is a *false*
one. That is the entire distinction and it belongs in code, not in a comment.

### 2. `country` on every directory — the one that would have bitten first

Six of the fifteen directories are UAE-only and nothing recorded it, while
`next_target` paired every enabled business with every directory. The first
run after a US business was added would have issued **"Add Yakima Electricians
to Yalwa UAE"** — and since a pending pair never expires, that pair would have
sat in the queue permanently.

`"country": "*"` means any. **A missing `country` means skip, not `*`** — same
rule `CITATION_AUTOMATION.md` already applies to `verify`.

### 3. `requires_street` on every directory

A `service_area` business is skipped where the street field is mandatory.
Defaults to `"unknown"`, and unknown means skip. You audit it once by opening
the form.

### 4. `full_address()` is country-aware

`"Al Barsha - Dubai - United Arab Emirates"` is right for Dubai and wrong
everywhere else. A US record now reads `"Yakima WA 98901"`. The Dubai form is
unchanged and there is a test asserting that.

### 5. `build_pack` for a service_area business

Drops the Street and Area/district rows, adds State and Service area. An empty
Street row in a pack is an invitation to put something in it.

Also: `citation_feeds.py` required a street to include a business in a feed,
which dropped all six US sites out of every CSV. It asks `missing_nap()` now.

---

## New command

```bash
python citations.py --audit
```

Lists every directory record still carrying `unknown` metadata, with its
submit URL and which fields to fill. This exists because of the next section.

---

## Why every US site shows `0 eligible` today

```
yakima    0/0 submitted, 0 pending, 0 eligible   <- run --audit
```

**This is the design, not a fault.** `requires_street` is `"unknown"` on all
fifteen directories, and unknown means skip. Open each form once, record what
it actually demands, and those six sites start queueing.

Do not shortcut this by defaulting `requires_street` to `false`. The whole
point is that the rule does not depend on anyone remembering it.

---

## Four known gaps, in the order they will hurt

1. **A pending pair never expires.** `next_target` skips anything in
   `pending`; nothing re-queues it. One stalled issue blocks that
   (business, directory) pair permanently and silently. `record_pending`
   already writes `issued_at` — nothing reads it. This is the one that will be
   discovered three months from now.
2. **`gh()` swallows GitHub's error.** `subprocess.run(..., check=True,
   capture_output=True)` puts the real message in `CalledProcessError.stderr`
   and nothing prints it, so a failed Action shows a bare traceback. Catch it
   and print `e.stderr`.
3. **Four of the five Dubai businesses are missing `listing_name`** as well as
   their street, so only `aqua` is ever served and the round-robin in
   `next_target` can never fire. A data gap, not a policy one.
4. **`verify` is `"unknown"` on all fifteen directories**, so
   `--verification email` currently selects nothing. Per
   `CITATION_AUTOMATION.md`, email signup is not evidence a *business listing*
   can be verified without a phone call — audit the real flow, not the signup.

---

## The browser-automation question is settled

A live test against Brownbook reached step 2 and hit two things at once: its
published terms restrict robot-driven usage, and the account step is gated by
reCAPTCHA. Do not build around either. The queue's job is to prepare a pack
that takes two minutes to paste.

The genuinely automatable channel already exists here and is not a form at
all: `citation_feeds.py` builds the bulk CSV that Bing Places, Apple Business
Connect, Yext and Uberall accept. That is the path those platforms built for
this, and it is where effort pays.

---

## Repo setup

**One secret: `ANTHROPIC_API_KEY`.** That is the whole list. `GITHUB_TOKEN` is
supplied by Actions — do not create one. This repo is self-contained: the
daily run reads no other repository and needs no cross-repo token.

Optional variables: `ANTHROPIC_MODEL`, `NAP_UPSTREAM_URL`.

`nap_upstream.py` is a manual tool, not part of the automation. It only ever
touches the five `premises` records, so it has nothing to do with the US
sites.

Settings → Actions → General → Workflow permissions → **Read and write**, and
Issues must be enabled — `citation_queue.py` checks that first and stops
before spending any model calls.

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v     # 17 tests, all offline
python citations.py --status
python citations.py --audit
```

No test makes a listing, an issue, an email or a paid API call.
