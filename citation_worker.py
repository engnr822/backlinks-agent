"""Unattended publishing for explicitly approved, audited directory adapters.

Zearches is the first supported adapter. Unknown directories are not submitted.
The shared ledger is pushed BEFORE a submit click; uncertain tasks never retry.
"""
import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from browser_submit import fill_form, validate_url

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'data/publish_jobs.json'
LOG = ROOT / 'data/citations_log.json'
POLICY = ROOT / 'data/publish_policy.json'
HOSTS = ['zearches.com', 'www.zearches.com']


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def publish_checkpoint():
    """Fail closed if remote persistence is unavailable. No credential extraction."""
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Publishing requires the dedicated GitHub Action with durable state')
    commands = [
        ['git','add','--','data/publish_jobs.json','data/citations_log.json'],
        ['git','commit','-m','chore: persist citation publishing state [skip ci]'],
        ['git','pull','--rebase','origin','main'],
        ['git','push','origin','HEAD:main'],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('State checkpoint failed at ' + command[1] + '; publication stopped')


def fields_for(business):
    n = business['nap']
    if business.get('location_type') != 'service_area' or n.get('street') or n.get('area'):
        raise ValueError('Only streetless service-area profiles are supported')
    providers = {'Electrician':'electricians', 'Plumber':'plumbers',
                 'Water Heater Repair / Plumber':'water heater repair providers'}
    provider = providers[business['primary_category']]
    location = f"{n['city']}, {n['state']} {n['postal']}"
    area = 'Arizona' if n.get('service_area') == ['statewide'] else location
    description = (f"{n['listing_name']} connects customers in {area} with independent {provider}. "
                   f"Referral website; does not perform contracting work. Call {n['phone']}.")
    if not 50 <= len(description) <= 250 or len(n['listing_name']) > 30:
        raise ValueError('Directory field length limit exceeded; canonical name cannot be shortened')
    return dict(n, description=description, directory_category='Local Services & Shops')


def choose(businesses, policy, log, jobs):
    if policy.get('directory') != 'zearches' or policy.get('enabled') is not True:
        return None
    if policy.get('terms_url') != 'https://zearches.com/listing-policy.php' or not policy.get('approval_note'):
        raise ValueError('Directory terms approval must be recorded')
    index = {b['id']:b for b in businesses if b.get('enabled') is True}
    for bid in policy.get('approved_businesses', []):
        if bid not in index:
            raise ValueError('Unknown or disabled approved business')
        key = bid + ':zearches'
        if 'zearches' in log.get('submitted', {}).get(bid, {}) or key in jobs:
            continue
        fields_for(index[bid])
        return index[bid]
    return None


def same_identity(text, links, fields):
    numbers = [re.sub(r'\D','',m) for m in re.findall(r'(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)',text)]
    phone = re.sub(r'\D','',fields['phone'])
    return (fields['listing_name'] in text and any(p in (phone,'1'+phone) for p in numbers)
            and any(urlsplit(link).hostname == urlsplit(fields['website']).hostname for link in links))


class NeedsReview(Exception):
    pass


class Zearches:
    def __init__(self, browser):
        self.context = browser.new_context(service_workers='block')
        self.page = self.context.new_page()
        self.page.set_default_timeout(20000)
        def guard(route):
            req = route.request
            if req.is_navigation_request() and req.frame == self.page.main_frame:
                try: validate_url(req.url, HOSTS)
                except ValueError:
                    route.abort(); return
            route.continue_()
        self.page.route('**/*',guard)

    def close(self):
        self.context.close()

    def check_barriers(self):
        p = self.page
        validate_url(p.url,HOSTS)
        if re.search(r'just a moment|security verification|access denied',p.title(),re.I):
            raise NeedsReview('security_check')
        for selector in ['input[type=password]', 'iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]', '[data-sitekey]']:
            for element in p.locator(selector).all():
                if element.is_visible(): raise NeedsReview('account_or_captcha')

    def search(self, fields, query):
        url='https://zearches.com/directory.php?'+urlencode({'slug':'local-services','q':query})
        self.page.goto(url,wait_until='domcontentloaded')
        self.check_barriers()
        heading=self.page.locator('#results-title').inner_text().strip()
        cards=self.page.locator('main li').evaluate_all('nodes=>nodes.map(n=>({text:n.innerText,links:Array.from(n.querySelectorAll("a[href]")).map(a=>a.href)}))')
        for card in cards:
            if same_identity(card['text'],card['links'],fields): return url
        if heading != '0 search results': raise NeedsReview('existing_entry_or_unrecognized_results')
        return None

    def existing(self, fields):
        found=self.search(fields,urlsplit(fields['website']).hostname)
        return found or self.search(fields,fields['phone'])

    def prepare(self, fields):
        self.page.goto('https://zearches.com/',wait_until='domcontentloaded')
        self.check_barriers()
        form=self.page.locator('#submit')
        form.wait_for(state='visible')
        mapping=[dict(source='website',selector='#url'),dict(source='listing_name',selector='#title'),
                 dict(source='directory_category',selector='#directory',action='select'),
                 dict(source='description',selector='#description')]
        fill_form(self.page,fields,mapping)
        self.check_barriers()
        # Do not manufacture or edit anti-CSRF/timing fields. Wait for the site's own initialization.
        for name in ['csrf_token','form_started_at']:
            if form.locator(f'input[name="{name}"]').count():
                self.page.wait_for_function('(name)=>Boolean(document.querySelector(`#submit input[name="${name}"]`)?.value)',arg=name,timeout=20000)
        button=form.locator('button[type=submit]')
        if button.count()!=1 or not button.is_enabled(): raise NeedsReview('submit_control_changed')

    def submit(self):
        self.diagnostics = {'phase': 'click', 'post_sent': False}
        def observe(request):
            if request.method == 'POST' and urlsplit(request.url).hostname in HOSTS:
                self.diagnostics['post_sent'] = True
        self.page.on('request', observe)
        def observe_response(response):
            if response.request.method == 'POST' and urlsplit(response.url).hostname in HOSTS:
                self.diagnostics['post_http_status'] = response.status
        self.page.on('response', observe_response)
        self.page.locator('#submit button[type=submit]').click()
        self.diagnostics['phase'] = 'feedback'
        # Wait on the site's actual response, not a successful click alone.
        from playwright.sync_api import TimeoutError as BrowserTimeout
        try:
            self.page.locator('#submission-feedback').wait_for(state='visible',timeout=20000)
        except BrowserTimeout:
            self.diagnostics.update(self.failure_details())
            return 'response_unrecognized'
        feedback=self.page.locator('#submission-feedback').inner_text()
        if 'Your website has been submitted' in feedback: return 'accepted'
        if 'Security check failed' in feedback: return 'rejected_security'
        return 'rejected_or_unknown'

    def failure_details(self):
        details = dict(getattr(self, 'diagnostics', {}))
        parsed = urlsplit(self.page.url)
        details['page_host'] = parsed.hostname
        details['page_path'] = parsed.path
        details['ad_overlay'] = parsed.fragment == 'google_vignette'
        # Only known public feedback; never log raw DOM, query strings or tokens.
        for phrase, code in [('Security check failed', 'security_rejected'),
                             ('Your website has been submitted', 'accepted'),
                             ('already exists', 'duplicate'),
                             ('Forbidden', 'forbidden'), ('Access denied', 'access_denied'),
                             ('Internal Server Error', 'server_error'),
                             ('Too Many Requests', 'rate_limited')]:
            if self.page.get_by_text(phrase, exact=False).count():
                details['feedback'] = code
        return details


def execute(business, adapter, jobs, log, checkpoint):
    """A checkpoint is mandatory before ANY click. Tests supply an offline recorder."""
    bid=business['id']; key=bid+':zearches'; fields=fields_for(business)
    if key in jobs or 'zearches' in log.get('submitted',{}).get(bid,{}):
        raise ValueError('Pair already recorded; reconcile it instead of resubmitting')
    jobs[key]={'status':'reserved','run_id':os.environ.get('GITHUB_RUN_ID','local-test'),
               'updated_at':datetime.now(timezone.utc).isoformat(),'listing_url':''}
    checkpoint(jobs,log)
    try:
        live=adapter.existing(fields)
        existing=bool(live)
        if not live:
            adapter.prepare(fields)
            jobs[key]['status']='submission_uncertain'
            checkpoint(jobs,log)
            response=adapter.submit()
            jobs[key]['response']=response
            if isinstance(adapter, Zearches):
                jobs[key]['diagnostics'] = adapter.failure_details()
            # Even after a rejection/timeout, no second submit is attempted.
            live=adapter.existing(fields)
        if live:
            jobs[key].update(status='live',listing_url=live,source='existing_verified' if existing else 'new_submission_verified')
            log.setdefault('submitted',{}).setdefault(bid,{})['zearches']={
                'date':datetime.now(timezone.utc).date().isoformat(),'url':live}
            log.get('pending',{}).get(bid,{}).pop('zearches',None)
        else:
            jobs[key]['status']='pending_public_verification'
    except NeedsReview as error:
        jobs[key].update(status='needs_review',reason=str(error))
    except Exception as error:
        # No raw browser exception: it may include a verification token or private DOM.
        jobs[key].update(status='needs_review',reason='navigation_or_state_error_no_retry',error_type=type(error).__name__)
        if isinstance(adapter, Zearches):
            try: jobs[key]['diagnostics'] = adapter.failure_details()
            except Exception: pass
    checkpoint(jobs,log)
    return jobs[key]


def main():
    os.chdir(ROOT)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    jobs=read(LEDGER,{})
    log=read(LOG,{})
    target=choose(read(ROOT/'data/businesses.json',{})['businesses'],read(POLICY,{}),log,jobs)
    if not target:
        print('No unattempted, approved pairs with a supported adapter. New listings: 0.'); return
    print('Selected:',target['id'],'-> zearches')
    if not args.publish:
        print('Plan only. No browser or submission.'); return
    if os.environ.get('GITHUB_ACTIONS')!='true':
        parser.error('Use the Publish citations Action; remote checkpointing is required')
    def checkpoint(jobs,log):
        write(LEDGER,jobs); write(LOG,log); publish_checkpoint()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        adapter=Zearches(browser)
        try: result=execute(target,adapter,jobs,log,checkpoint)
        finally: adapter.close(); browser.close()
    report=f"{target['nap']['listing_name']} -> Zearches: {result['status']}\n"
    report+=f"Public listing: {result['listing_url'] or 'not verified'}\n"
    print(report)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f: f.write(report)
    if result['status']!='live': raise SystemExit(2)


if __name__=='__main__': main()
