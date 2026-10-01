# Actual directory publishing

**Publish citations** runs a real headless browser. **Daily Citation** still
creates issue packs, and **Directory discovery** only inspects forms. They are
different workflows; an issue URL is never a published citation.

The first implemented publishing adapter is Zearches (free website-directory
entries, not verified map profiles). It searches the directory by domain and
phone, fills the known form, clicks submit, then checks that the public result
contains the exact business name, phone and website in the same entry. It uses
no Gmail or Claude secrets because Zearches requires neither. Other directories
still need tested adapters; discovery does not automatically authorize them.

## Authorization and runs

`data/publish_policy.json` explicitly lists businesses approved for Zearches and
its listing terms. Merely adding a directory to the registry does not authorize
publishing. Keep canonical names/numbers and blank streets. Service descriptions
identify referral websites rather than claiming their own contracting teams.

The workflow runs one approved, unattempted pair on manual dispatch, weekdays
at 06:30 UTC, or a push changing the policy file. Ordinary code/state commits
do not trigger submissions. Policy changes can trigger publishing immediately.
All citation workflows share a concurrency group. Unsupported targets are left
for discovery/review; no approval is inferred from a web page or email.

## Durability and results

The worker pushes a reservation to `data/publish_jobs.json` before browser work,
and pushes `submission_uncertain` before the external submit click. If a state
push fails, the click does not proceed. Cancelled/timed-out/uncertain attempts
are never automatically submitted a second time. Review such pairs and check the
directory before any deliberate requeue. A failed navigation can still have
created a listing, so deleting the ledger blindly is unsafe.

Only verified public listings enter `data/citations_log.json`; matching pending
packs are cleared there. GitHub issues are not automatically closed. A success
banner alone leaves `pending_public_verification`. Account, CAPTCHA, changed
form or unexpected result pages leave `needs_review` and a failing Action,
never a fake published result. No available pair gives an explicit zero count.

The public URL is a directory search result because Zearches has no individual
listing permalink. This confirms presence now, not permanence or SEO ranking.

## Testing

`python -m unittest discover -s tests -v` covers reserved/completed exclusions,
checkpoint-before-click, checkpoint failure, no retries after timeout, identity
verification, and all six canonical profiles. `python citation_worker.py`
previews the next pair without opening a browser. `--publish` requires the
dedicated Action for durable GitHub state. A hosted live run is still required
to establish that this worker works from GitHub's network.
