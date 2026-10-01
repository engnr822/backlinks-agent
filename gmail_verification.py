"""Read-only Gmail OAuth and narrowly matched directory verification links.

Never print message contents, tokens, or verification URLs. Email is untrusted
data; only an audited recipe can define the accepted sender and destination.
"""
import argparse
import base64
import os
import re
import time
from email.utils import getaddresses
from html.parser import HTMLParser
from urllib.parse import urlsplit

import requests


class Gmail:
    def __init__(self):
        names = ['GMAIL_CLIENT_ID', 'GMAIL_CLIENT_SECRET', 'GMAIL_REFRESH_TOKEN']
        if any(not os.environ.get(n) for n in names):
            raise ValueError('Missing Gmail OAuth secrets; see EMAIL_AUTOMATION.md')
        self.session = requests.Session()
        self.session.trust_env = False
        try:
            response = self.session.post('https://oauth2.googleapis.com/token', data={
                'client_id': os.environ[names[0]], 'client_secret': os.environ[names[1]],
                'refresh_token': os.environ[names[2]], 'grant_type': 'refresh_token'},
                timeout=30, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError('Gmail OAuth refresh failed; reconnect the configured account')
            self.session.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
        except requests.RequestException:
            raise ValueError('Gmail OAuth network request failed') from None
        profile = self.get('profile')
        expected = os.environ.get('GMAIL_MAILBOX', 'engnr822@gmail.com')
        if profile.get('emailAddress', '').lower() != expected.lower():
            raise ValueError('OAuth account does not match GMAIL_MAILBOX')

    def get(self, path, params=None):
        try:
            response = self.session.get('https://gmail.googleapis.com/gmail/v1/users/me/' + path,
                                        params=params, timeout=30, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError('Gmail read failed; check API access and readonly scope')
            return response.json()
        except requests.RequestException:
            raise ValueError('Gmail network request failed') from None

    def candidates(self, recipient, rule, since):
        query = f'after:{int(since)} to:{recipient} ' + '{' + ' '.join('from:' + s for s in rule['senders']) + '}'
        page = self.get('messages', {'q': query, 'maxResults': 50, 'includeSpamTrash': 'true'})
        if page.get('nextPageToken'):
            raise ValueError('Too many matching emails; narrow the audited rule')
        links = set()
        for item in page.get('messages', []):
            message = self.get('messages/' + item['id'], {'format': 'full'})
            links.update(matching_links(message, recipient, rule, since))
        if len(links) > 1:
            raise ValueError('Multiple verification links matched; human review required')
        return next(iter(links), None)


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.urls = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.update(value for name, value in attrs if name == 'href' and value)


def body_links(part):
    links = set()
    # Ignore attachments entirely, including text/html attachments.
    if part.get('filename'):
        return links
    data = part.get('body', {}).get('data', '')
    if data and part.get('mimeType') in ['text/plain', 'text/html']:
        text = base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace')
        if part['mimeType'] == 'text/html':
            parser = Links(); parser.feed(text); links.update(parser.urls)
        else:
            links.update(re.findall(r'https://[^\s<>"\']+', text))
    for child in part.get('parts', []):
        links.update(body_links(child))
    return links


def validate_rule(rule):
    if not rule or rule.get('audited') is not True:
        raise ValueError('An audited email_verification recipe is required')
    for key in ['senders', 'hosts', 'paths', 'subject_contains']:
        if not rule.get(key):
            raise ValueError('Incomplete email verification rule: ' + key)
    for sender in rule['senders']:
        if not re.fullmatch(r'[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+', sender):
            raise ValueError('Expected exact sender email addresses')
    if any(not p.startswith('/') or p == '/' for p in rule['paths']):
        raise ValueError('Expected exact verification endpoint paths')


def allowed_link(url, rule):
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname in rule['hosts'] and
                p.path in rule['paths'] and not p.username and not p.password and
                p.port in (None, 443) and not p.fragment)
    except ValueError:
        return False


def matching_links(message, recipient, rule, since):
    validate_rule(rule)
    if int(message.get('internalDate', 0)) < int(since * 1000):
        return set()
    payload = message.get('payload', {})
    headers = payload.get('headers', [])
    def values(name):
        return [h['value'] for h in headers if h['name'].lower() == name]
    senders = {a.lower() for _, a in getaddresses(values('from'))}
    recipients = {a.lower() for _, a in getaddresses(values('to') + values('x-original-to'))}
    if len(senders) != 1 or not senders.issubset({s.lower() for s in rule['senders']}):
        return set()
    if recipient.lower() not in recipients:
        return set()
    if not all(word.lower() in ' '.join(values('subject')).lower() for word in rule['subject_contains']):
        return set()
    # This is matching, not proof of sender authenticity. Exact destination
    # hosts/paths constrain the link action; never trust instructions in email.
    return {url for url in body_links(payload) if allowed_link(url, rule)}


def wait_for_link(client, recipient, rule, since, timeout=120):
    validate_rule(rule)
    deadline = time.monotonic() + timeout
    while True:
        link = client.candidates(recipient, rule, since)
        if link:
            return link
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(10, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.parse_args()
    try:
        Gmail()
    except (ValueError, KeyError):
        raise SystemExit('Gmail connection failed. Check the three OAuth secrets, API enablement and expected mailbox.') from None
    print('Gmail connection verified. No messages were read, sent, modified or deleted.')


if __name__ == '__main__':
    main()
