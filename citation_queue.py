"""Issue delivery with recovery after a failed state commit. No directory submissions."""
import argparse
import json
import os
import subprocess

import citations


def gh(*args):
    result = subprocess.run(['gh', *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def marker(business_id, directory_id):
    return f'<!-- citation:{business_id}:{directory_id} -->'


def issue_index(repo):
    pages = json.loads(gh('api', '--paginate', '--slurp',
                         f'repos/{repo}/issues?state=all&per_page=100'))
    return [issue for page in pages for issue in page if 'pull_request' not in issue]


def matching_issue(issues, business, directory):
    tag = marker(business['id'], directory['id'])
    legacy = f"Add {business['nap']['listing_name']} to {directory['name']}"
    titles = {legacy, f"Citation: add {business['nap']['listing_name']} to {directory['name']}"}
    return next((i for i in issues if tag in (i.get('body') or '')
                 or i['title'] in titles), None)


def record_pending(log, business, directory, url):
    from datetime import datetime, timezone
    log.setdefault('pending', {}).setdefault(business['id'], {})[directory['id']] = {
        'issued_at': datetime.now(timezone.utc).isoformat(), 'issue_url': url,
        'status': 'awaiting_submission',
    }


def deliver(repo, verification=None, count=1, country=''):
    # Fail before generating paid descriptions if Issues/auth are unavailable.
    metadata = json.loads(gh('api', f'repos/{repo}'))
    if not metadata.get('has_issues'):
        raise RuntimeError('GitHub Issues is disabled for this repository')
    issues = issue_index(repo)
    log = citations._load(citations.LOG_FILE, {})
    # Reconcile ALL existing packs, including old unmarked issues. Closed does
    # not imply a live listing: only --done with a URL confirms submission.
    for business in citations.businesses():
        if citations.missing_nap(business):
            continue
        for directory in citations.directories():
            bid, did = business['id'], directory['id']
            if did in log.get('submitted', {}).get(bid, {}):
                continue
            if did in log.get('pending', {}).get(bid, {}):
                continue
            existing = matching_issue(issues, business, directory)
            if existing:
                record_pending(log, business, directory, existing['html_url'])
    citations._save_log(log)
    for n in range(max(1, count)):
        if not _issue_one(repo, verification, country):
            break


def _issue_one(repo, verification=None, country=''):
    """One pack. Returns False when there is nothing left to issue.

    The log is re-read each time: build_pack writes the description cache, and
    a batch that held one dict in memory would hand the same pair out twice.
    """
    log = citations._load(citations.LOG_FILE, {})
    target = citations.next_target(log, verification, country)
    if not target:
        print('No unissued eligible pairs. Review pending issues and incomplete NAP records.')
        return False
    business, directory = target
    pack = citations.build_pack(business, directory)
    pack += '\n\n' + marker(business['id'], directory['id']) + '\n'
    from pathlib import Path
    Path('citation_pack.md').write_text(pack, encoding='utf-8')
    url = gh('issue', 'create', '--repo', repo, '--title',
             f"Citation: add {business['nap']['listing_name']} to {directory['name']}",
             '--body-file', 'citation_pack.md')
    # Reload because build_pack may have updated the description cache.
    log = citations._load(citations.LOG_FILE, {})
    record_pending(log, business, directory, url)
    citations._save_log(log)
    print(url)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--verification', choices=['email', 'phone', 'none', 'unknown'])
    parser.add_argument('--country', default='',
                        help="us | ae | all. The registry holds two tracks.")
    parser.add_argument('--count', type=int, default=1,
                        help='how many packs to issue in this run. 294 pairs at '
                             '1/day is ten months; at 2/day it is five. Raising '
                             'it does not make the submitting any faster -- that '
                             'is still a person at a form.')
    args = parser.parse_args()
    if not args.repo:
        parser.error('--repo or GITHUB_REPOSITORY is required')
    deliver(args.repo, args.verification, args.count, args.country)


if __name__ == '__main__':
    main()
