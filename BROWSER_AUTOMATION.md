# Guided browser pilot

This is a local, headed Playwright runner, separate from the existing issue queue.
It fills recorded directory fields and saves progress in SQLite. It is not yet
an unattended submission service. Zearches has an enabled Yakima recipe and a separately browser-verified live
listing. Offline tests alone do not establish live submission success.

## Run

```powershell
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python browser_submit.py --status
python browser_submit.py --business yakima --recipe recipes/directory.json --check
python browser_submit.py --business yakima --recipe recipes/directory.json
```

First audit a real directory and create its recipe using the example structure.
Record its URL, required fields, address requirement, verification method, dated
eligibility evidence, allowed hosts, observed selectors and duplicate-search URL.
Do not enable a recipe merely to bypass eligibility checks. Google Business
Profile, mandatory street addresses and phone verification are excluded.

The operator searches the directory for the exact phone and website, logs in,
and opens the listing form. The runner fills the fields, checks values, saves a
review screenshot, and waits for `SUBMIT YAKIMA`. This approves one submission.
CAPTCHA, terms and email verification remain visible human steps. After email
verification, open the public listing in the same tab. Name, phone and website
are checked before `LIVE YAKIMA` records the URL. This checks identity, not search
indexing or editorial acceptance independently; the operator confirms public access.

## Recovery and privacy

`--resume` only resumes preparing/awaiting_review tasks with unchanged data.
Before the submit click, status is saved as `submission_uncertain`; an error or
timeout cannot automatically retry the click. Use `--reconcile` to inspect an
existing public listing without another submission. Do not clear the database
to retry an uncertain attempt. A changed configuration requires manual review.

`.browser-state/` contains browser sessions, SQLite, a lock and screenshots. It
is gitignored. Never upload it, share it, or store it in Actions artifacts.
After a crash, remove runner.lock only after confirming no runner is active.
Passwords are entered in the browser, never CLI arguments or workflow inputs.

All six US profiles retain the user's exact numbers and blank street fields.
Clovis retains info@clovisnmplumbers.com by explicit user instruction. Forwarding
success is user-reported. Only Yakima can run until the pilot has been reviewed.
GitHub Actions can run offline tests; interactive sessions need an attended
desktop. There is no Gmail API requirement for this pilot.

## Tests and remaining work

`python -m unittest discover -s tests -v`

Offline tests cover eligibility, field changes, duplicate task prevention,
durable uncertain status and listing identity. They do not prove delivery or a
successful live submission. The Zearches pilot is complete; other directories still require their own live audits and recipes.


## Verified Yakima pilot — September 26, 2026

Zearches accepted the direct website. Its public Local Services & Shops search
shows Yakima Electricians, (509) 992-1165, Yakima WA 98901, the factual referral
statement and https://yakimaelectricians.com. This is a website-directory mention,
not a verified local map profile. There is no standalone listing permalink.

Public result: https://zearches.com/directory.php?slug=local-services&q=%28509%29+992-1165

Form: URL, optional title (30 chars), category, description (50–250 chars).
No address, account, email or phone verification. Terms were explicitly approved
by the user. The first attempt failed with csrf_invalid; refreshing the page and
using the fresh form succeeded. No security tokens were edited or bypassed.

```powershell
python browser_submit.py --business yakima --recipe recipes/zearches.json --check
python browser_submit.py --business yakima --recipe recipes/zearches.json --sync
```

Do not submit Yakima to Zearches again. The browser task is already recorded live.
`--sync` writes a verified local browser result into data/citations_log.json,
clearing that pair's pending status. Commit/push that log to share it with the
hosted daily queue. Sync does not close GitHub issues or push automatically.
Packs with an enabled recipe now include the browser command.

The scheduled workflow remains an issue-pack generator, Monday–Friday at
06:00 UTC. It does not run the interactive browser. Remaining directories need
individual form mappings and eligibility checks; unknown metadata permits an
audit pack, not automatic submission. Other five businesses remain pilot-gated.

## Optional Gmail verification

See [EMAIL_AUTOMATION.md](EMAIL_AUTOMATION.md). Audited email recipes can use --email-verify to read the expected email and open its verification link. OAuth setup and one live email-directory test are still required. CAPTCHA and account setup remain attended.


## List-driven discovery

`Directory discovery` inspects the next three uninspected manual-directory
entries on weekdays at 05:30 UTC, before the 06:00 pack job. It uses the same
registry, keeps a clean browser session, visits at most three same-site pages
per target and follows visible registration/listing links. It captures field
structure without input values. It never fills forms, creates accounts,
solves CAPTCHA, reads Gmail or submits listings. No Gmail secrets enter this job.

Reports are committed to `data/directory_discovery.json`. They are observations,
not approved submission recipes: client-side required flags are incomplete and
account-gated forms need further review. `requires_street: unknown` remains
unknown when no mandatory street field is visible; absence is not permission.
Review a report before promoting it to an enabled recipe. Failures also remain
in the report; remove a report entry deliberately to request another inspection.

Manual run: Actions -> Directory discovery -> Run workflow -> us / 3.
Offline preview: `python directory_discovery.py --country us --count 3 --plan`.
The daily pack generator continues independently. Discovery does not mean a
citation was created, and the hosted browser discovery workflow is not yet
live-tested. Offline tests cover selection, navigation and basic classification.

A-ZBusinessFinder is pending user registration. Its later listing form and
verification requirements remain unverified. GitHub Gmail credentials have
passed the connection check reported by the user; local browser credentials
are still separate. No email-based listing has yet been verified end to end.
