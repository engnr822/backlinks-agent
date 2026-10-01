import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import browser_submit as runner
import citations


class IntegrationTests(unittest.TestCase):
    def test_real_recipe_preserves_canonical_identity(self):
        root=Path(runner.__file__).parent
        recipe=runner.read_json(root/'recipes/zearches.json')
        business=next(b for b in runner.read_json(root/'data/businesses.json')['businesses'] if b['id']=='yakima')
        runner.validate_recipe(recipe)
        fields=runner.recipe_payload(business,recipe)
        self.assertIn('(509) 992-1165',fields['description'])
        self.assertIn('Yakima, WA 98901',fields['description'])
        self.assertEqual(fields['category'],'Electrician')
        self.assertEqual(fields['directory_category'],'Local Services & Shops')
        self.assertLessEqual(len(fields['description']),250)
        recipe['description_length']['max']=10
        with self.assertRaises(ValueError): runner.recipe_payload(business,recipe)

    def test_only_live_results_clear_pending_queue(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log.json'
            path.write_text(json.dumps({'pending':{'yakima':{'zearches':{'status':'awaiting_submission'}}}}))
            store=runner.Store(Path(d)/'queue.sqlite')
            try:
                store.reserve('yakima:zearches','digest')
                with patch.object(citations,'LOG_FILE',str(path)), patch.object(citations,'businesses',return_value=[{'id':'yakima'}]), patch.object(citations,'directories',return_value=[{'id':'zearches'}]):
                    with self.assertRaises(ValueError): runner.sync_live_task(store,'yakima:zearches','yakima','zearches')
                    self.assertIn('zearches',json.loads(path.read_text())['pending']['yakima'])
                    store.transition('yakima:zearches','preparing','live','https://zearches.com/directory.php?slug=local-services')
                    runner.sync_live_task(store,'yakima:zearches','yakima','zearches')
                    saved=json.loads(path.read_text())
                    self.assertNotIn('zearches',saved['pending']['yakima'])
                    self.assertIn('zearches',saved['submitted']['yakima'])
            finally: store.db.close()

    def test_pack_contains_browser_command_without_paid_generation(self):
        with patch.object(citations,'descriptions',return_value={}):
            root=Path(runner.__file__).parent
            business=next(b for b in runner.read_json(root/'data/businesses.json')['businesses'] if b['id']=='yakima')
            pack=citations.build_pack(business,dict(id='zearches',name='Zearches',submit_url='https://zearches.com/',requires_street=False))
            self.assertIn('--recipe recipes/zearches.json',pack)
            self.assertIn('--sync',pack)


if __name__=='__main__': unittest.main()
