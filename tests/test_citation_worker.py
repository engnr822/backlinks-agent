import copy
import unittest
from unittest.mock import Mock

from citation_worker import choose, execute, fields_for, same_identity, NeedsReview


BUSINESS = dict(id='lawton',enabled=True,location_type='service_area',primary_category='Electrician',nap=dict(
    listing_name='Lawton Electricians',phone='(580) 872-2022',website='https://lawtonelectricians.com',
    city='Lawton',state='OK',postal='73501',street='',area='',service_area=['73501','73505','73507']))
POLICY = dict(enabled=True,directory='zearches',terms_url='https://zearches.com/listing-policy.php',
              approval_note='Test only',approved_businesses=['lawton'])
URL='https://zearches.com/directory.php?slug=local-services&q=lawton'


class WorkerTests(unittest.TestCase):
    def test_skip_done_reserved_and_unapproved(self):
        self.assertEqual(choose([BUSINESS],POLICY,{},{}),BUSINESS)
        self.assertIsNone(choose([BUSINESS],POLICY,{'submitted':{'lawton':{'zearches':{}}}},{}))
        self.assertIsNone(choose([BUSINESS],POLICY,{}, {'lawton:zearches':{'status':'reserved'}}))
        self.assertIsNone(choose([BUSINESS],dict(POLICY,approved_businesses=[]),{},{}))

    def test_publish_only_after_durable_intent_then_verify(self):
        adapter=Mock(); adapter.existing.side_effect=[None,URL]; adapter.submit.return_value='accepted'
        states=[]; jobs={}; log={}
        def checkpoint(j,l): states.append(j['lawton:zearches']['status'])
        def submit():
            self.assertEqual(states,['reserved','submission_uncertain'])
            return 'accepted'
        adapter.submit.side_effect=submit
        result=execute(BUSINESS,adapter,jobs,log,checkpoint)
        self.assertEqual(result['status'],'live')
        self.assertEqual(log['submitted']['lawton']['zearches']['url'],URL)
        self.assertEqual(states[-1],'live')

    def test_checkpoint_failure_prevents_click(self):
        adapter=Mock(); adapter.existing.return_value=None
        checkpoint=Mock(side_effect=[None,RuntimeError('push failed'),None])
        result=execute(BUSINESS,adapter,{}, {},checkpoint)
        adapter.submit.assert_not_called()
        self.assertEqual(result['status'],'needs_review')

    def test_timeout_never_retries_or_marks_live(self):
        adapter=Mock(); adapter.existing.return_value=None; adapter.submit.side_effect=TimeoutError()
        jobs={}; log={}
        self.assertEqual(execute(BUSINESS,adapter,jobs,log,Mock())['status'],'needs_review')
        adapter.submit.assert_called_once()
        self.assertNotIn('submitted',log)
        with self.assertRaises(ValueError): execute(BUSINESS,adapter,jobs,log,Mock())

    def test_success_banner_without_public_listing_is_not_live(self):
        adapter=Mock(); adapter.existing.return_value=None; adapter.submit.return_value='accepted'
        log={}
        self.assertEqual(execute(BUSINESS,adapter,{},log,Mock())['status'],'pending_public_verification')
        self.assertNotIn('submitted',log)

    def test_existing_live_entry_not_resubmitted(self):
        adapter=Mock(); adapter.existing.return_value=URL
        result=execute(BUSINESS,adapter,{}, {},Mock())
        adapter.submit.assert_not_called(); adapter.prepare.assert_not_called()
        self.assertEqual(result['source'],'existing_verified')

    def test_password_or_captcha_is_review_not_submission(self):
        adapter=Mock(); adapter.existing.return_value=None; adapter.prepare.side_effect=NeedsReview('account_or_captcha')
        self.assertEqual(execute(BUSINESS,adapter,{}, {},Mock())['status'],'needs_review')
        adapter.submit.assert_not_called()

    def test_identity_requires_all_three_in_same_card(self):
        f=fields_for(BUSINESS)
        self.assertTrue(same_identity('Lawton Electricians (580) 872-2022',[f['website']],f))
        self.assertFalse(same_identity('Lawton Electricians (580) 872-2023',[f['website']],f))
        self.assertFalse(same_identity('Lawton Electricians (580) 872-2022',['https://other.test'],f))

    def test_all_real_profiles_fit_directory_without_name_rewrite(self):
        from citation_worker import ROOT,read
        profiles=[b for b in read(ROOT/'data/businesses.json',{})['businesses'] if b.get('location_type')=='service_area']
        self.assertEqual(len(profiles),6)
        for b in profiles:
            f=fields_for(b)
            self.assertEqual(f['listing_name'],b['nap']['listing_name'])
            self.assertIn(b['nap']['phone'],f['description'])
            if b['primary_category']=='Plumber': self.assertIn('independent plumbers',f['description'])


if __name__=='__main__': unittest.main()
