"""Read-only browser discovery from the registry. Never fills or submits forms."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'data/directory_discovery.json'


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def select_targets(directories, reports, country='us', count=3):
    countries = {'us': 'United States', 'ae': 'United Arab Emirates'}
    # The imported directory list is tier 3. Exclude map/platform tracks.
    eligible = [d for d in directories if d.get('channel') == 'manual' and d.get('tier', 3) >= 3
                and d.get('requires_street') is not True
                and d.get('country') in ('*', countries[country])
                and d['id'] not in reports
                and not (ROOT / 'recipes' / (d['id'] + '.json')).exists()]
    return sorted(eligible, key=lambda d: (d.get('tier', 99), d['id']))[:count]


def safe_page(url, start_url):
    try:
        parsed, start = urlsplit(url), urlsplit(start_url)
        same_host = (parsed.hostname or '').removeprefix('www.') == (start.hostname or '').removeprefix('www.')
        return bool(parsed.scheme == 'https' and same_host and not parsed.username and not parsed.password
                    and parsed.port in (None, 443) and not parsed.fragment
                    and not re.search(r'logout|delete|remove|verify|confirm|token|unsubscribe', parsed.path + '?' + parsed.query, re.I))
    except ValueError:
        return False


def classify(fields, captcha=False):
    street = any(f['required'] and re.search(r'street|address(?:_?line)?[_ -]?1', f['name'] + ' ' + f['label'], re.I)
                 and not re.search(r'email|e-mail', f['name'] + ' ' + f['label'], re.I) for f in fields)
    if street: return 'requires_street'
    if captcha: return 'captcha_or_security_check'
    if any(f['type'] == 'password' for f in fields): return 'needs_account'
    return 'form_found_needs_review' if fields else 'no_form_found'


def discover(browser, directory):
    start = directory['submit_url']
    result = dict(directory_id=directory['id'], checked_at=datetime.now(timezone.utc).isoformat(),
                  entry_url=start, status='uninspected', requires_street='unknown', verify='unknown', pages=[])
    if not safe_page(start, start):
        result['status']='unsupported_entry_url'; return result
    context = browser.new_context(service_workers='block')
    # No credentials or persistent sessions. Only same-site main-frame navigation.
    page = context.new_page()
    page.set_default_timeout(15000)
    def guard(route):
        req=route.request
        if req.is_navigation_request() and req.frame == page.main_frame and not safe_page(req.url,start):
            route.abort()
        else: route.continue_()
    page.route('**/*',guard)
    try:
        next_url=start
        for _ in range(3):
            page.goto(next_url,wait_until='domcontentloaded')
            page.locator('body').wait_for()
            # Capture public field structure, never values, tokens or page contents.
            fields=page.locator('input,textarea,select').evaluate_all('''nodes => nodes.filter(n => n.type !== 'hidden' && n.getClientRects().length).map(n => ({
              tag:n.tagName.toLowerCase(), type:n.type || '', name:n.name || '', id:n.id || '',
              label:Array.from(n.labels || []).map(l => l.innerText).join(' ') || n.getAttribute('aria-label') || n.placeholder || '',
              required:n.required || n.getAttribute('aria-required') === 'true'
            }))''')
            captcha=page.locator('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],[data-sitekey]').count()>0
            if re.search(r'just a moment|security verification|access denied',page.title(),re.I): captcha=True
            status=classify(fields,captcha)
            result['pages'].append(dict(url=page.url,fields=fields,status=status))
            result['status']=status
            if status=='requires_street': result['requires_street']=True
            if status in ('requires_street','captcha_or_security_check','needs_account'): break
            meaningful=[f for f in fields if not re.search(r'search|newsletter',f['name']+' '+f['label'],re.I)
                        and f['type'] not in ('submit','button','checkbox')]
            if len(meaningful)>=3: break
            links=page.locator('a[href]').evaluate_all('nodes => nodes.map(n=>({text:n.innerText,url:n.href}))')
            seen={p['url'] for p in result['pages']}
            candidates=[link['url'] for link in links if re.search(r'add.*business|list your|create.*listing|free listing|register|sign up|join',link['text'],re.I)
                        and safe_page(link['url'],start) and link['url'] not in seen]
            if not candidates: break
            next_url=candidates[0]
    except Exception:
        result['status']='navigation_failed_needs_review'
    finally:
        context.close()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--country',choices=['us','ae'],default='us')
    p.add_argument('--count',type=int,choices=range(1,6),default=3)
    p.add_argument('--plan',action='store_true',help='List targets without opening a browser or writing state')
    args=p.parse_args()
    reports=read(STATE,{})
    targets=select_targets(read(ROOT/'data/directories.json',{})['directories'],reports,args.country,args.count)
    if args.plan:
        for d in targets: print(d['id']+' | '+d['submit_url'])
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            for directory in targets:
                report=discover(browser,directory)
                reports[directory['id']]=report
                temporary=STATE.with_suffix('.tmp')
                temporary.write_text(json.dumps(reports,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
                temporary.replace(STATE)
                print(directory['id']+' | '+report['status'])
        finally: browser.close()
    print('Discovery only: no account created, email read or listing submitted. Review data/directory_discovery.json.')


if __name__=='__main__': main()
