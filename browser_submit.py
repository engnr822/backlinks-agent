"""Guided browser submissions. Run locally; Gmail/CAPTCHA are human handoffs."""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def validate_url(url, hosts):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in hosts
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('URL must be HTTPS on an explicitly allowed directory host')
    return url


def payload(business):
    nap = business['nap']
    if business['id'] != 'yakima':
        raise ValueError('Only Yakima is enabled during the first pilot')
    if business.get('location_type') != 'service_area' or nap.get('street'):
        raise ValueError('Pilot requires a service-area profile with no street')
    fields = dict(nap)
    fields['contact'] = business.get('contact_person', 'Muhammad Naseem Aslam')
    fields['category'] = business['primary_category']
    fields['service_area'] = ', '.join(nap.get('service_area', []))
    fields['location'] = f"{nap['city']}, {nap['state']} {nap['postal']}"
    fields['description'] = business.get('citation_description', '')
    for name in ['listing_name', 'phone', 'website', 'email', 'description']:
        if not fields.get(name):
            raise ValueError(f'Missing reviewed business field: {name}')
    return fields


def validate_recipe(recipe):
    if recipe.get('enabled') is not True:
        raise ValueError('Recipe is not enabled: complete the live directory audit first')
    if recipe.get('requires_street') is not False:
        raise ValueError('Directory must explicitly accept no street address')
    if recipe.get('accepts_referrals') is not True:
        raise ValueError('Referral business eligibility has not been established')
    if recipe.get('verify') not in ['email', 'none']:
        raise ValueError('Phone/unknown verification is not supported')
    if recipe.get('country') not in ['United States', '*']:
        raise ValueError('Directory does not cover the United States')
    if not recipe.get('audit_evidence') or not recipe.get('duplicate_check_url'):
        raise ValueError('Directory audit and duplicate-check URL are required')
    if recipe.get('id') == 'google_business_profile':
        raise ValueError('Google Business Profile is excluded')
    hosts = recipe['allowed_hosts']
    for key in ['submit_url', 'duplicate_check_url']:
        validate_url(recipe[key], hosts)
    if not recipe.get('fields') or not recipe.get('submit_selector'):
        raise ValueError('Recorded form fields and submit selector are required')
    for field in recipe['fields']:
        if field['source'] in ['street', 'area']:
            raise ValueError('Street/address input must remain blank')
        if field.get('action', 'fill') not in ['fill', 'select']:
            raise ValueError('Only fill/select actions are allowed before review')


def recipe_payload(business, recipe):
    fields = payload(business)
    fields['directory_category'] = recipe.get('category_label', fields['category'])
    if recipe.get('description_template'):
        fields['description'] = recipe['description_template'].format_map(fields)
    limits = recipe.get('description_length', {})
    if not limits.get('min', 0) <= len(fields['description']) <= limits.get('max', 10000):
        raise ValueError('Description is outside the audited directory length limit')
    return fields


def sync_live_task(store, key, business_id, directory_id):
    row = store.get(key)
    if not row or row[0] != 'live' or not row[2]:
        raise ValueError('Only a verified live task can update the citation queue')
    import citations
    citations.mark_done(business_id, directory_id, row[2])


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=1)
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, status TEXT, digest TEXT, listing_url TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS email_attempts (task_id TEXT PRIMARY KEY, since REAL, opened INTEGER)')
        self.db.commit()

    def reserve(self, key, digest):
        with self.db:
            self.db.execute('INSERT INTO tasks VALUES (?, ?, ?, ?)', (key, 'preparing', digest, ''))

    def get(self, key):
        return self.db.execute('SELECT status, digest, listing_url FROM tasks WHERE id=?', (key,)).fetchone()

    def transition(self, key, old, new, url=''):
        with self.db:
            result = self.db.execute('UPDATE tasks SET status=?, listing_url=? WHERE id=? AND status=?',
                                     (new, url, key, old))
            if result.rowcount != 1:
                raise ValueError('Task changed or already attempted; inspect state before continuing')

    def start_email_window(self, key):
        import time
        with self.db:
            self.db.execute('INSERT INTO email_attempts VALUES (?, ?, 0)', (key, time.time()))


def verify_email(page, store, key, client, recipient, rule):
    from gmail_verification import wait_for_link
    attempt = store.db.execute('SELECT since,opened FROM email_attempts WHERE task_id=?', (key,)).fetchone()
    if not attempt or attempt[1]:
        print('No unused email window. Inspect verification manually; no link retried.')
        return
    link = wait_for_link(client, recipient, rule, attempt[0])
    if not link:
        print('Expected verification email has not arrived. Resume with --reconcile --email-verify later.')
        return
    # Persist BEFORE opening a one-time link; an interrupted navigation is not retried.
    with store.db:
        changed = store.db.execute('UPDATE email_attempts SET opened=1 WHERE task_id=? AND opened=0', (key,))
        if changed.rowcount != 1:
            raise ValueError('Verification link was already attempted')
    def guard(route):
        request = route.request
        if request.is_navigation_request() and request.frame == page.main_frame:
            try:
                validate_url(request.url, rule['hosts'])
            except ValueError:
                route.abort(); return
        route.continue_()
    page.route('**/*', guard)
    try:
        page.goto(link)
        print('Expected verification link opened. Confirm the directory result; this is not proof of a live listing.')
    except Exception:
        # Playwright exceptions may contain the complete secret verification URL.
        print('Verification navigation interrupted. Inspect browser manually; no automatic retry.')
    finally:
        page.unroute('**/*', guard)


def fill_form(page, fields, mapping):
    for entry in mapping:
        locator = page.locator(entry['selector'])
        if locator.count() != 1:
            raise ValueError(f"Field selector must match exactly once: {entry['source']}")
        value = fields[entry['source']]
        if entry.get('action', 'fill') == 'select':
            locator.select_option(label=value)
            actual = locator.locator('option:checked').inner_text()
        else:
            locator.fill(value)
            actual = locator.input_value()
        if actual != value:
            raise ValueError(f"Directory changed canonical field: {entry['source']}")


def listing_matches(page, fields, recipe):
    validate_url(page.url, recipe['allowed_hosts'])
    text = page.locator('body').inner_text()
    # Require website href and full normalized phone, not a substring of another number.
    phones = [re_digits(m) for m in re.findall(r'(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)', text)]
    phone = re_digits(fields['phone'])
    website = urlsplit(fields['website']).hostname
    links = page.locator('a[href]').evaluate_all('(nodes) => nodes.map(n => n.href)')
    return (fields['listing_name'] in text
            and any(p in [phone, '1' + phone] for p in phones)
            and any(urlsplit(link).hostname == website for link in links))


def re_digits(value):
    return ''.join(c for c in value if c.isdigit())


def main():
    import os
    os.chdir(ROOT)  # Existing citation registry paths are repository-relative.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--business', default='yakima')
    parser.add_argument('--recipe', type=Path)
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--check', action='store_true', help='Validate recipe/config without browser or state writes')
    parser.add_argument('--reconcile', action='store_true', help='Inspect an attempted task; never submit it again')
    parser.add_argument('--resume', action='store_true', help='Resume only a task that has never attempted submission')
    parser.add_argument('--sync', action='store_true', help='Copy an already verified live result into the local citation queue')
    parser.add_argument('--email-verify', action='store_true', help='Read and open a matching link using an audited Gmail recipe')
    args = parser.parse_args()
    if args.resume and args.reconcile:
        parser.error('Choose --resume or --reconcile, not both')
    private = ROOT / '.browser-state'
    if args.status:
        if not (private / 'queue.sqlite').exists():
            print('No browser tasks yet.'); return
        store = Store(private / 'queue.sqlite')
        for row in store.db.execute('SELECT id,status,listing_url FROM tasks'):
            print(' | '.join(row))
        store.db.close(); return
    if not args.recipe:
        parser.error('--recipe is required')
    recipe = read_json(args.recipe)
    validate_recipe(recipe)
    business = next(b for b in read_json(ROOT / 'data/businesses.json')['businesses'] if b['id'] == args.business)
    fields = recipe_payload(business, recipe)
    digest = hashlib.sha256(json.dumps([fields, recipe], sort_keys=True).encode()).hexdigest()
    if args.check:
        print('Configuration valid; no browser opened and nothing submitted.'); return
    if args.sync:
        store = Store(private / 'queue.sqlite')
        try:
            sync_live_task(store, args.business + ':' + recipe['id'], args.business, recipe['id'])
        finally:
            store.db.close()
        return
    if not args.reconcile:
        queue_path = ROOT / 'data/citations_log.json'
        queue = read_json(queue_path) if queue_path.exists() else {}
        completed = queue.get('submitted', {}).get(args.business, {}).get(recipe['id'])
        if completed:
            raise SystemExit('Already recorded in the shared citation queue: ' + completed.get('url', ''))
    email_client = None
    if args.email_verify:
        from gmail_verification import Gmail, validate_rule
        if recipe.get('verify') != 'email':
            parser.error('This directory does not use email verification')
        validate_rule(recipe.get('email_verification'))
        email_client = Gmail()  # Fail before submission if mailbox access is unavailable.
    from playwright.sync_api import sync_playwright
    private.mkdir(exist_ok=True)
    # Exclusive lock file. A crash leaves an explicit lock
    # requiring inspection; never silently run two workers or reuse a profile.
    lock = private / 'runner.lock'
    try:
        lockfile = lock.open('x')
    except FileExistsError:
        raise SystemExit('Runner lock exists. Confirm no worker is active before removing it.')
    store = None
    try:
        store = Store(private / 'queue.sqlite')
        key = args.business + ':' + recipe['id']
        prior = store.get(key)
        if args.reconcile:
            if not prior or prior[1] != digest:
                raise ValueError('Reconciliation requires an existing task with unchanged configuration')
        elif args.resume:
            if not prior or prior[1] != digest or prior[0] not in ['preparing', 'awaiting_review']:
                raise ValueError('Resume requires an unchanged task with no submission attempt')
            store.transition(key, prior[0], 'preparing')
        elif prior:
            raise ValueError('Existing task: use --resume before submission, or --reconcile after an attempt')
        else:
            store.reserve(key, digest)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(str(private / 'profile'), headless=False)
            try:
                page = context.new_page()
                if not args.reconcile:
                    page.goto(recipe['duplicate_check_url'])
                    input('Inspect directory search by phone AND website. Press Enter when ready. ')
                    if input('Type NO DUPLICATE after confirming no matching listing exists: ') != 'NO DUPLICATE':
                        return
                    page.goto(recipe['submit_url'])
                    input('Complete login/navigation yourself; stop on the blank listing form. Press Enter. ')
                    validate_url(page.url, recipe['allowed_hosts'])
                    fill_form(page, fields, recipe['fields'])
                    print(json.dumps(fields, indent=2, ensure_ascii=False))
                    store.transition(key, 'preparing', 'awaiting_review')
                    page.screenshot(path=str(private / 'review.png'), full_page=True)
                    if input('Review browser fields and any terms. Type SUBMIT YAKIMA to submit this one listing: ') != 'SUBMIT YAKIMA':
                        return
                    validate_url(page.url, recipe['allowed_hosts'])
                    # Re-fill and re-check canonical fields before any irreversible click.
                    fill_form(page, fields, recipe['fields'])
                    button = page.locator(recipe['submit_selector'])
                    if button.count() != 1:
                        raise ValueError('Submit selector must match exactly once')
                    store.transition(key, 'awaiting_review', 'submission_uncertain')
                    if email_client:
                        store.start_email_window(key)
                    button.click()
                if email_client:
                    verify_email(page, store, key, email_client, fields['email'], recipe['email_verification'])
                input('Complete CAPTCHA/email verification manually if needed. Open the PUBLIC listing in this tab, then press Enter. ')
                if not listing_matches(page, fields, recipe):
                    raise ValueError('Public listing identity could not be verified. Task retained for reconciliation.')
                if input('Confirm this is the public listing, not a preview: type LIVE YAKIMA: ') != 'LIVE YAKIMA':
                    return
                status = store.get(key)[0]
                store.transition(key, status, 'live', page.url)
                print('Verified public listing:', page.url)
                print('Sync this verified result to the local pack queue with the same command plus --sync.')
            finally:
                context.close()
    finally:
        if store: store.db.close()
        lockfile.close()
        lock.unlink()


if __name__ == '__main__':
    main()
