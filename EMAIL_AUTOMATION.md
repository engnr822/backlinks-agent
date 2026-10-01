# Gmail verification setup

Email reading is implemented but NOT connected or live-tested yet. Zearches
needs no email. No real email-based directory recipe is enabled until its
sender, subject and exact verification endpoint have been observed and audited.

## One-time account setup

Use a Google Cloud project with Gmail API enabled. Configure OAuth consent for
your own application and authorize engnr822@gmail.com using only
`https://www.googleapis.com/auth/gmail.readonly` with offline access to obtain
a refresh token. A Google login password, an API key, and an OAuth client secret
alone are not substitutes for the user-authorized refresh token.

### Getting the three values

```bash
python get_gmail_refresh_token.py
```

That script's header lists the Google Cloud Console steps and it refuses to
run until the first two are set. It opens a browser, you sign in as the
mailbox owner, and it prints the refresh token. Nothing is written to disk.

Two things that trip this up:

- **Add yourself as a Test user** on the OAuth consent screen. An app left in
  testing works indefinitely for its own test users, so there is no need to
  publish it or submit it for verification.
- **No refresh_token in the response** means the account already approved this
  client. Revoke it at https://myaccount.google.com/permissions and run again;
  Google only issues one on first consent.

Official setup: https://developers.google.com/identity/protocols/oauth2/web-server
Gmail scope/query reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list

In GitHub: repository Settings -> Secrets and variables -> Actions -> Secrets:

| Secret | Value |
| --- | --- |
| GMAIL_CLIENT_ID | OAuth application's client ID |
| GMAIL_CLIENT_SECRET | Matching OAuth client secret |
| GMAIL_REFRESH_TOKEN | Refresh token authorized by the target Gmail account |

Under Variables, optionally set `GMAIL_MAILBOX` to `engnr822@gmail.com` (default).
Never put credentials in Variables, workflow inputs, chat, screenshots or commits.
Then run **Actions -> Check Gmail connection -> Run workflow**. It checks OAuth
and mailbox identity only; it does not read messages, send mail or submit listings.

GitHub Secrets are injected into Actions and cannot be retrieved by the local
runner. For local browser operation, provide the same names through your secure
process environment. Do not upload browser profiles or email/verification URLs
as Actions artifacts. The daily issue workflow still does not launch a browser.

## Audited email recipes

Add this section to an existing audited directory recipe only after examining a
real verification email. Values below are EXAMPLES, not working directory data:

```json
{
  "email_verification": {
    "audited": true,
    "senders": ["verify@directory.example"],
    "hosts": ["directory.example"],
    "paths": ["/verify-email"],
    "subject_contains": ["verify", "email"]
  }
}
```

With `verify: email`, use the usual runner command plus `--email-verify`. OAuth
is checked before submission. The runner records the submission timestamp,
polls Inbox and Spam for up to two minutes, and accepts exactly one matching
HTTPS verification URL. Recipient must be the site's info@ address. Sender,
subject, timestamp, hostname and path must all match. This is conservative
matching, not independent proof of sender authenticity. Mail instructions are
never executed. Attachment links, unrelated domains and password-reset paths
are not followed. A legitimate unrecognized sender/path needs a recipe audit.

The exact host/path must implement email verification only: never configure a
link which also accepts new terms, changes credentials or grants broader access.
The runner blocks off-host main-frame redirects and records a one-time link
attempt before navigating. Errors do not print email contents or token URLs.
An interrupted link is handed to the operator instead of automatically retried.
Use `--reconcile --email-verify` to check a delayed email for an existing attempt.

Email confirmation does NOT mark the listing live. Public name/phone/website
verification remains required. CAPTCHA, new passwords, new legal terms and
unrecognized forms still require human handling. Login and form mappings remain
directory-specific; adding secrets does not automate all 49 directories.

## Validation status

Offline tests cover recipient/sender/time filtering, attachments, URL boundaries,
ambiguous emails and non-retry after a failed one-time-link navigation. No real
Gmail inbox has been accessed in developing this change. Live validation needs
OAuth credentials and a pending submission to an audited email directory.
