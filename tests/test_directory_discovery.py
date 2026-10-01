import unittest
from directory_discovery import classify, safe_page, select_targets


class DiscoveryTests(unittest.TestCase):
    def test_navigation_boundaries(self):
        start='https://example.org/listing'
        self.assertTrue(safe_page('https://www.example.org/register',start))
        for url in ['https://other.org/register','http://example.org/register',
                    'https://example.org/delete','https://example.org/verify?token=secret',
                    'https://user@example.org/register']:
            self.assertFalse(safe_page(url,start))

    def test_unknown_is_not_accepted_address_policy(self):
        self.assertEqual(classify([dict(name='email_address',label='Email address',required=True,type='email')]),'form_found_needs_review')
        self.assertEqual(classify([dict(name='street',label='Street',required=True,type='text')]),'requires_street')
        self.assertEqual(classify([dict(name='password',label='Password',required=True,type='password')]),'needs_account')
        self.assertEqual(classify([],True),'captcha_or_security_check')

    def test_registry_selection_excludes_completed_and_ineligible(self):
        def d(id,**kw): return dict(id=id,channel='manual',country='United States',requires_street='unknown',**kw)
        records=[d('already'),d('next'),dict(d('street'),requires_street=True),dict(d('api'),channel='api'),dict(d('ae'),country='United Arab Emirates'),d('maps',tier=1)]
        self.assertEqual([x['id'] for x in select_targets(records,{'already':{}},count=3)],['next'])


if __name__=='__main__': unittest.main()
