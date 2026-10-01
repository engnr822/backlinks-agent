import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from browser_submit import Store, fill_form, listing_matches, payload, validate_recipe, validate_url


def recipe():
    return dict(id='fixture', enabled=True, requires_street=False,
                accepts_referrals=True, verify='email', country='United States',
                audit_evidence='OFFLINE TEST ONLY', allowed_hosts=['example.org'],
                duplicate_check_url='https://example.org/search', submit_url='https://example.org/add',
                fields=[dict(source='listing_name', selector='#name')], submit_selector='#submit')


class BrowserTests(unittest.TestCase):
    def test_unknown_eligibility_blocks(self):
        for key, value in [('enabled', False), ('requires_street', 'unknown'),
                           ('accepts_referrals', None), ('verify', 'phone'), ('country', 'UAE')]:
            with self.subTest(key=key):
                r=recipe(); r[key]=value
                with self.assertRaises(ValueError): validate_recipe(r)

    def test_no_street_mapping(self):
        r=recipe(); r['fields'][0]['source']='street'
        with self.assertRaises(ValueError): validate_recipe(r)

    def test_redirect_and_credentials_rejected(self):
        for url in ['http://example.org', 'https://example.org.evil.test',
                    'https://user@example.org', 'https://example.org:444/']:
            with self.subTest(url=url):
                with self.assertRaises(ValueError): validate_url(url, ['example.org'])

    def test_stored_attempt_survives_restart_and_cannot_be_reserved_twice(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'queue.sqlite'; s=Store(path)
            s.reserve('yakima:one','hash')
            s.transition('yakima:one','preparing','submission_uncertain')
            s.db.close(); s=Store(path)
            self.assertEqual(s.get('yakima:one')[0], 'submission_uncertain')
            with self.assertRaises(sqlite3.IntegrityError): s.reserve('yakima:one','hash')
            with self.assertRaises(ValueError): s.transition('yakima:one','preparing','live')
            s.db.close()

    def test_changed_phone_stops_form(self):
        page=Mock(); field=page.locator.return_value
        field.count.return_value=1; field.input_value.return_value='5099921165'
        with self.assertRaises(ValueError):
            fill_form(page, {'phone':'(509) 992-1165'}, [dict(source='phone',selector='#phone')])

    def test_ambiguous_selector_stops_form(self):
        page=Mock(); page.locator.return_value.count.return_value=2
        with self.assertRaises(ValueError):
            fill_form(page, {'phone':'(509) 992-1165'}, [dict(source='phone',selector='#phone')])
        page.locator.return_value.fill.assert_not_called()

    def test_public_identity_requires_name_phone_and_website(self):
        p=Mock(); p.url='https://example.org/listing'
        p.locator.return_value.inner_text.return_value='Yakima Electricians\n(509) 992-1165\n98901'
        p.locator.return_value.evaluate_all.return_value=['https://yakimaelectricians.com/']
        fields=dict(listing_name='Yakima Electricians',phone='(509) 992-1165',website='https://yakimaelectricians.com')
        self.assertTrue(listing_matches(p,fields,recipe()))
        p.locator.return_value.evaluate_all.return_value=['https://other.test']
        self.assertFalse(listing_matches(p,fields,recipe()))

    def test_non_pilot_blocked(self):
        with self.assertRaises(ValueError): payload(dict(id='clovis',nap={}))


if __name__ == '__main__': unittest.main()
