import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import citations as c
import citation_queue as q


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.business = {'id': 'a', 'nap': {key: 'value' for key in c.REQUIRED_NAP}}
        # country='*' = pairs with any business. A record with no country at
        # all is deliberately skipped, so the fixtures have to state one.
        self.dirs = [dict(id='one', name='One', verify='unknown', country='*'),
                     dict(id='two', name='Two', verify='email', country='*')]
        for name, value in [('businesses', lambda: [self.business]),
                            ('directories', lambda: self.dirs),
                            ('LOG_FILE', str(Path(self.tmp.name) / 'log.json'))]:
            p = patch.object(c, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_pending_advances(self):
        log = {'pending': {'a': {'one': {}}}}
        self.assertEqual(c.next_target(log)[1]['id'], 'two')

    def test_filter_excludes_unknown(self):
        self.assertEqual(c.next_target({}, 'email')[1]['id'], 'two')
        self.assertIsNone(c.next_target({}, 'phone'))

    def test_null_nap_is_missing(self):
        self.business['nap']['street'] = None
        self.assertIn('street', c.missing_nap(self.business))

    def test_done_validates_and_clears_pending(self):
        c._save_log({'pending': {'a': {'one': {}}}, 'descriptions': {'a': 'cached'}})
        with self.assertRaises(ValueError):
            c.mark_done('a', 'one', '')
        with self.assertRaises(ValueError):
            c.mark_done('bad', 'one', 'https://example.com/listing')
        c.mark_done('a', 'one', 'https://example.com/listing')
        log = c._load(c.LOG_FILE)
        self.assertEqual(log['pending']['a'], {})
        self.assertEqual(log['descriptions']['a'], 'cached')
        self.assertIn('one', log['submitted']['a'])

    def test_legacy_issue_recognized_even_when_closed(self):
        issue = {'title': 'Add value to One', 'body': None, 'state': 'closed'}
        self.assertIs(q.matching_issue([issue], self.business, self.dirs[0]), issue)

    def test_failure_does_not_mark_new_pair_pending(self):
        with patch.object(q, 'gh', side_effect=['{"has_issues": true}', RuntimeError('offline')]), \
             patch.object(q, 'issue_index', return_value=[]), \
             patch.object(c, 'build_pack', return_value='pack'), \
             patch.object(Path, 'write_text'):
            with self.assertRaises(RuntimeError):
                q.deliver('owner/repo')
        self.assertNotIn('pending', c._load(c.LOG_FILE))

    def test_recovery_and_description_cache_preserved(self):
        existing = {'title': 'Add value to One', 'html_url': 'https://github.com/o/r/issues/1'}
        def pack(*args):
            log = c._load(c.LOG_FILE)
            log['descriptions'] = {'a': {'short': 'cached'}}
            c._save_log(log)
            return 'pack'
        with patch.object(q, 'gh', side_effect=['{"has_issues": true}', 'https://github.com/o/r/issues/2']), \
             patch.object(q, 'issue_index', return_value=[existing]), \
             patch.object(c, 'build_pack', side_effect=pack), \
             patch.object(Path, 'write_text'):
            q.deliver('owner/repo')
        log = c._load(c.LOG_FILE)
        self.assertEqual(set(log['pending']['a']), {'one', 'two'})
        self.assertEqual(log['descriptions']['a']['short'], 'cached')
        self.assertIsNone(c.next_target(log))

    # ---- country ----------------------------------------------------
    def test_country_mismatch_is_never_paired(self):
        """The bug this filter exists for: a US site offered a UAE directory."""
        self.business['nap']['country'] = 'United States'
        self.dirs = [dict(id='yalwa_ae', name='Yalwa UAE', verify='unknown',
                          country='United Arab Emirates')]
        self.assertIsNone(c.next_target({}))

    def test_country_matches_case_insensitively(self):
        self.business['nap']['country'] = 'united states'
        self.dirs = [dict(id='us_only', name='US only', verify='unknown',
                          country='United States')]
        self.assertEqual(c.next_target({})[1]['id'], 'us_only')

    def test_missing_country_is_skipped_not_assumed_global(self):
        self.dirs = [dict(id='nometa', name='No metadata', verify='unknown')]
        self.assertIsNone(c.next_target({}))

    # ---- service-area businesses ------------------------------------
    def _service_area_business(self):
        nap = {k: 'value' for k in c.REQUIRED_SERVICE_AREA}
        nap['country'] = 'United States'
        nap['street'] = ''
        return {'id': 'a', 'location_type': 'service_area', 'nap': nap}

    def test_service_area_skips_directories_that_demand_a_street(self):
        self.business = self._service_area_business()
        self.dirs = [dict(id='needs_street', name='Needs street', verify='unknown',
                          country='*', requires_street=True)]
        self.assertIsNone(c.next_target({}))

    def test_service_area_accepts_a_directory_that_does_not(self):
        self.business = self._service_area_business()
        self.dirs = [dict(id='no_street', name='No street', verify='unknown',
                          country='*', requires_street=False)]
        self.assertEqual(c.next_target({})[1]['id'], 'no_street')

    def test_unknown_requires_street_is_skipped(self):
        self.business = self._service_area_business()
        self.dirs = [dict(id='unaudited', name='Unaudited', verify='unknown',
                          country='*', requires_street='unknown')]
        self.assertIsNone(c.next_target({}))

    def test_service_area_record_with_a_street_is_rejected(self):
        b = self._service_area_business()
        b['nap']['street'] = '127 39th St'
        self.assertTrue(any('street must be empty' in g for g in c.missing_nap(b)))

    def test_service_area_does_not_require_area_or_street(self):
        self.assertEqual(c.missing_nap(self._service_area_business()), [])

    # ---- address formatting -----------------------------------------
    def test_us_address_reads_as_a_us_address(self):
        nap = {'city': 'Yakima', 'state': 'WA', 'postal': '98901',
               'country': 'United States', 'street': ''}
        self.assertEqual(c.full_address(nap), 'Yakima WA 98901')

    def test_dubai_address_is_unchanged(self):
        nap = {'street': '127 39th St', 'area': 'Al Barsha', 'city': 'Dubai',
               'postal': '', 'country': 'United Arab Emirates'}
        self.assertEqual(c.full_address(nap),
                         '127 39th St - Al Barsha - Dubai - United Arab Emirates')


if __name__ == '__main__':
    unittest.main()
