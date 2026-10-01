import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import citations
import citation_queue
from description_templates import registry_descriptions


class DescriptionTests(unittest.TestCase):
    def profiles(self):
        root = Path(citations.__file__).parent
        return [b for b in json.loads((root/'data/businesses.json').read_text(encoding='utf-8'))['businesses']
                if b.get('location_type') == 'service_area']

    def test_all_six_without_key_and_without_network(self):
        with patch.dict(os.environ, {'CITATION_DESCRIPTION_MODE':'registry','ANTHROPIC_API_KEY':''}), \
                patch('llm._call_claude', side_effect=AssertionError('Must not call AI')):
            profiles=self.profiles()
            self.assertEqual(len(profiles),6)
            for b in profiles:
                result=citations.descriptions(b)
                for key, limit in [('short',150),('medium',300),('long',750)]:
                    self.assertLessEqual(len(result[key]),limit)
                    self.assertIn(b['nap']['listing_name'],result[key])
                    self.assertIn('referral',result[key].lower())
                self.assertIn('does not perform contracting work',result['medium'])

    def test_missing_category_fails_with_data_error_not_api_error(self):
        b=self.profiles()[0]; b.pop('primary_category')
        with self.assertRaisesRegex(ValueError,'category'): registry_descriptions(b)

    def test_real_issue_pack_path_without_api_key(self):
        business=self.profiles()[0]
        directory=dict(id='test_directory',name='Test directory',country='United States',
                       requires_street=False,verify='email',channel='manual',submit_url='https://example.org/add')
        with tempfile.TemporaryDirectory() as d, \
             patch.dict(os.environ,{'CITATION_DESCRIPTION_MODE':'registry','ANTHROPIC_API_KEY':''}), \
             patch.object(citations,'LOG_FILE',str(Path(d)/'state.json')), \
             patch.object(citations,'next_target',return_value=(business,directory)), \
             patch.object(Path,'write_text') as write, \
             patch.object(citation_queue,'gh',return_value='https://github.com/test/repo/issues/1') as gh, \
             patch('llm._call_claude',side_effect=AssertionError('Must not call AI')):
            self.assertTrue(citation_queue._issue_one('test/repo'))
            gh.assert_called_once()
            pack=write.call_args.args[0]
            self.assertIn('referral website',pack)
            saved=citations._load(citations.LOG_FILE,{})
            self.assertEqual(saved['pending']['yakima']['test_directory']['status'],'awaiting_submission')


if __name__=='__main__': unittest.main()
