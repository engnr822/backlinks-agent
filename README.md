# citations-agent

Citation and NAP work for eleven businesses, split out of
`clickfrauddetection/social-media-posts-agent` so that the social poster and
the citation queue stop sharing a git history, an issue tracker and a daily
commit race.

Two kinds of business live here and they are not the same record with a field
left blank:

| | premises | service_area |
|---|---|---|
| who | the five Dubai businesses | the six US pay-per-call sites |
| has a street address | yes | **no, on purpose** |
| verified by | a door, a postcard, a call | phone or email |
| NAP source | their Google Business Profile, upstream | authored here |
| Google Business Profile | yes | **never** |

A city and a postcode with no street line is an *incomplete* address. A street
line that is not the business's own is a *false* one. That distinction is the
whole reason `location_type` exists, and it is enforced in code rather than
left to whoever is filling the form at 11pm: `missing_nap()` rejects a
`service_area` record that has a street, and `eligible()` skips any directory
whose street field is mandatory.

## What is here

| | |
|---|---|
| `citations.py` | the registry, the queue, and the pack a human submits |
| `citation_queue.py` | issues one pack a day as a GitHub issue, and recovers after a failed state commit |
| `citation_feeds.py` | the automatable half — bulk CSV feeds for Bing Places, Apple Business Connect, Yext, Uberall |
| `nap_schema.py` | each site's own LocalBusiness JSON-LD |
| `platforms.py` | what each destination accepts, and how much of it automates |
| `nap_upstream.py` | optional, manual: re-sync the Dubai listings' NAP from the poster repo |
| `llm.py` | the one function this used to import from the poster |

`sync_nap.py` and `add_business.py` did **not** come across: both stand on the
GBP OAuth stack (`gbp_business`, `poster_gmb`), which belongs to the poster
repo. `sync_nap.py` keeps running there; `nap_upstream.py` reads its output.

## This repo is self-contained

`data/businesses.json` here **is** the registry. Nothing is fetched from
another repo, the daily run needs no cross-repo token, and the poster repo is
not a dependency.

`nap_upstream.py` is kept as a manual tool only. The five Dubai listings'
addresses are synced from their Google Business Profiles by `sync_nap.py`,
which lives in the poster repo; if one of those addresses changes there and
you want it reflected here, run `python nap_upstream.py` by hand with an
`UPSTREAM_TOKEN` in the environment. It is deliberately not in the workflow —
a daily run should not fail, or quietly no-op, over a token for a repo this
one does not otherwise need.

The six US sites have no Google Business Profile at all, so nothing upstream
applies to them: their NAP is authored here and only here.

## Commands

```bash
python citations.py --status        # who is ready, what is pending, how many directories are eligible
python citations.py --audit         # which directory records still have unchecked metadata
python citation_queue.py --repo OWNER/REPO       # issue the next pack
python citations.py --done BIZ DIR https://...   # record a LIVE listing url
python citation_feeds.py --master                # rebuild feeds/nap_master.csv
python -m unittest discover -s tests -v          # 17 tests, all offline
```

## Why every US site reports 0 eligible directories today

That is the design, not a fault. `requires_street` is `"unknown"` on all
fifteen directory records, and unknown means **skip** — the same rule the
delivery doc already applies to `verify`. Open each form once, record what it
actually demands, and those sites start queueing. `--audit` prints the list.

Missing metadata is never "probably fine". A pack issued against a guess costs
somebody an afternoon and, if it publishes, a listing that has to be hunted
down and corrected.

## How much of this can actually be automated

`python platforms.py` prints the landscape grouped by the only thing that
decides the answer — how the platform takes data:

| channel | effort | free? |
|---|---|---|
| **hosted feed** | publish one URL, it re-reads it forever | yes |
| **bulk upload** | one CSV, every business at once | yes |
| **paid API** | fully automatable, and syndicates onward to dozens | no |
| **manual form** | a person, a form, a CAPTCHA, every time | yes |

Directory listings are not like social posts, and it is worth being exact
about why: social platforms publish through open APIs, and listing platforms
mostly do not. The ones that offer an API for *creating* listings charge for
it, because what you are buying is the syndication behind it.

So there are three honest routes, and they are not alternatives — do them in
this order:

1. **Bulk upload, free.** Bing Places takes all six businesses in one file
   (`citation_feeds.py --template bing_places`). Minutes, repeatable.
2. **Hosted feed, free.** Apple Business Connect can re-read one URL instead
   of being uploaded to. Set once. *Caveat below.*
3. **Paid syndication.** One record pushed to dozens of directories and kept
   corrected — Yext, Uberall, or Moz Local, which is usually the cheapest for
   a handful of locations. This is the thing that behaves like a scheduled
   poster. Price it against a single call: at a $63 payout, a month of the
   cheap tier is roughly one or two calls.

The manual-form list is the long tail. One paid_api row replaces most of it.

### The hosted-feed caveat

`nap-feeds-daily.yml` publishes the feeds to GitHub Pages, and **Pages on a
private repository needs a paid plan**. This repo is private and should stay
private: a public feed listing all six businesses under one URL ties them
together for anyone who looks, which is a footprint these sites do not want.

Options, in preference order: host the feed on a Cloudflare Pages project you
already own, or give each business its own feed URL so nothing links them, or
skip the hosted channel and use bulk upload. The `publish` job is already
`continue-on-error: true`, so a failure there never breaks the run and the
feeds stay committed and attached as an artifact either way.

## Two things the queue will not do

**It does not submit forms.** Most directories' terms forbid robot-driven
signup, and the step that stops a script is a CAPTCHA, which is a human step.
A live browser test against Brownbook reached step 2 and then hit both:
published terms restricting automation, and a reCAPTCHA. The queue's job is to
prepare a pack that takes two minutes to paste, not to pretend to be a person.

**Closing an issue is not evidence of publication.** Only
`citations.py --done` with a real listing URL moves a pair to submitted. The
usual way a citation system rots is a dashboard full of "submitted" rows that
never went live.

## Known gaps

- A pending pair never expires. `next_target` skips anything in `pending` and
  nothing re-queues it, so one stalled issue blocks that (business, directory)
  pair permanently. `record_pending` already writes `issued_at`; nothing reads
  it yet.
- `gh()` in `citation_queue.py` runs with `check=True, capture_output=True`, so
  GitHub's own error message ends up inside `CalledProcessError.stderr` and
  nothing prints it — a failed Action shows a bare traceback.
- Four of the five Dubai businesses are missing `listing_name` as well as
  their street, so only `aqua` is currently served. That is a data gap, not a
  policy one.
- `verify` is `"unknown"` on all fifteen directories, so
  `--verification email` currently selects nothing.

## Guided browser pilot

See [BROWSER_AUTOMATION.md](BROWSER_AUTOMATION.md) for the local browser runner, review steps and current live-testing limitations.

## Description generation

Daily Citation uses CITATION_DESCRIPTION_MODE=registry: factual descriptions from canonical business name, category, location and service area. No ANTHROPIC_API_KEY is required. Service-area profiles are described as referrals, with no claims that they perform contracting work. Short/medium/long limits are validated. Explicit local CITATION_DESCRIPTION_MODE=claude retains the optional API-based path and requires its key. The workflow creates issue packs, not live directory listings.
