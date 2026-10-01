# Citation automation

## Implemented: reliable delivery queue

`python citation_queue.py --repo clickfrauddetection/social-media-posts-agent`
reconciles existing GitHub issues, issues one new pack, and records it as
pending. It does not submit directory forms. It requires an authenticated `gh`
CLI with repository Issues access. The workflow supplies GITHUB_TOKEN.

Existing issues are identified by a stable body marker or the two historical
title formats. Closed issues remain pending until a live listing is recorded;
closing an issue is not evidence of publication. Previously created duplicate
issues are not automatically closed. A failed state push is recovered from
GitHub issues on the next run. The scheduled workflow serializes runs; do not
run a local delivery concurrently with it or use multiple delivery workers.

`python citations.py --status` shows pending and submitted counts.
`python citations.py --done BUSINESS DIRECTORY https://directory.example/listing`
records a live URL and clears pending state. Commit the resulting state file.
URL format is validated; this command does not independently verify publication.

`python citation_queue.py --repo OWNER/REPO --verification email` restricts
selection to directory records with `"verify": "email"`. Missing metadata is
treated as `unknown`, never presumed email-only. Supported values: email,
phone, none, unknown. Audit the actual signup and business verification flows
before setting this field: email account signup does not establish that a
business listing can be verified without a phone call.

Tests: `python -m unittest discover -s tests -p test_citation_queue.py -v`
All tests are offline; no listing, issue, email, or paid API call is made.

## Submission rollout: not yet implemented or activated

1. Confirm the first business and canonical NAP. Aqua is the only currently
   complete record. Do not invent street addresses for the remaining four.
2. Restore private GitHub access and inspect the failing Actions run. The
   handoff's suggested failure cause remains unconfirmed without those logs.
3. Audit one target directory's current signup, duplicate lookup, submission,
   and verification flow. Check actual API eligibility; `channel: api` in the
   old catalog is not proof of provisioned API access.
4. Implement and test that directory's recipe using a persistent browser on
   the chosen VPS. Store profiles outside Git, restrict permissions, and run
   one worker. First prove it against a local fixture, then the chosen account.
5. Add a dedicated verification mailbox. Correlate by recipient, expected
   sender, message timestamp and task; reject stale messages. Allow verification
   links only for the expected directory host, never arbitrary email URLs.
   Keep mailbox passwords in environment variables, and never log OTPs.
6. Add Telegram assistance only after the user supplies the bot and authorized
   chat. Correlate replies by task, accept only the authorized sender, expire
   requests, redact screenshots, and persist pauses across restarts. CAPTCHA
   handling is a human step. After 30 minutes, save the task for later.
7. Separate `awaiting_submission`, `awaiting_verification`, `submitted`, and
   `live` states. Before retrying after an uncertain submission, look for an
   existing listing; do not resubmit blindly. Record evidence and listing URLs.
8. Once one directory works end to end, add further audited recipes. Move
   scheduling to the VPS/self-hosted runner only after persistent state,
   locking, credentials, and restart recovery have been verified.

For referral/pay-per-call brands, keep the handoff's separate approach:
brand profiles with accurate referral descriptions and no invented physical
address. This queue currently requires a complete physical-business NAP.

GitHub authentication, VPS/account details, mailbox setup, live recipes and
verification metadata are outstanding. Nothing here claims a citation is live
merely because an issue was opened.
