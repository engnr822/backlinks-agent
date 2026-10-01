import base64
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from gmail_verification import matching_links, validate_rule, allowed_link, Gmail
from browser_submit import Store, verify_email


RULE = dict(audited=True, senders=['verify@directory.example'], hosts=['directory.example'],
            paths=['/verify'], subject_contains=['verify'])
LINK = 'https://directory.example/verify?token=test-only'


def message(link=LINK):
    return dict(internalDate='2000000', payload=dict(mimeType='text/html',
        headers=[dict(name='From', value='Directory <verify@directory.example>'),
                 dict(name='To', value='info@yakimaelectricians.com'),
                 dict(name='Subject', value='Verify your business')],
        body=dict(data=base64.urlsafe_b64encode(f'<a href="{link}">Verify</a>'.encode()).decode())))


class GmailTests(unittest.TestCase):
    def test_exact_matching_message(self):
        self.assertEqual(matching_links(message(),'info@yakimaelectricians.com',RULE,1000),{LINK})

    def test_old_wrong_recipient_wrong_sender_wrong_subject(self):
        for kind in ['date','recipient','sender','subject']:
            m=message()
            if kind=='date': m['internalDate']='100'
            else:
                index={'sender':0,'recipient':1,'subject':2}[kind]
                m['payload']['headers'][index]['value']='wrong@example.org'
            self.assertEqual(matching_links(m,'info@yakimaelectricians.com',RULE,1000),set())

    def test_host_and_path_boundaries(self):
        for url in ['https://directory.example.evil.test/verify','https://directory.example/reset',
                    'https://user@directory.example/verify','http://directory.example/verify',
                    'https://directory.example:444/verify','https://directory.example/verify#extra']:
            with self.subTest(url=url): self.assertFalse(allowed_link(url,RULE))

    def test_no_attachment_or_unreviewed_rule(self):
        m=message(); m['payload']['filename']='attachment.html'
        self.assertEqual(matching_links(m,'info@yakimaelectricians.com',RULE,1000),set())
        with self.assertRaises(ValueError): validate_rule(dict(RULE,audited=False))

    def test_ambiguous_email_links_block(self):
        client=Gmail.__new__(Gmail)
        client.get=Mock(side_effect=[{'messages':[{'id':'1'},{'id':'2'}]},message(),message(LINK+'2')])
        with self.assertRaises(ValueError): client.candidates('info@yakimaelectricians.com',RULE,1000)

    def test_failed_link_navigation_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'state.sqlite')
            try:
                store.reserve('yakima:directory','digest'); store.start_email_window('yakima:directory')
                page=Mock(); page.goto.side_effect=RuntimeError('contains sensitive URL')
                with patch('gmail_verification.wait_for_link',return_value=LINK):
                    verify_email(page,store,'yakima:directory',Mock(),'info@yakimaelectricians.com',RULE)
                    verify_email(page,store,'yakima:directory',Mock(),'info@yakimaelectricians.com',RULE)
                page.goto.assert_called_once_with(LINK)
                self.assertEqual(store.get('yakima:directory')[0],'preparing')
            finally: store.db.close()


if __name__=='__main__': unittest.main()
