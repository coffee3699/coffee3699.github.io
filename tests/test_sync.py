import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('sync', Path(__file__).parents[1] / 'scripts/notion_sync.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

def text(s): return [{'type': 'text', 'text': {'content': s}, 'plain_text': s}]
def page(status='Published', approved=True, date='2020-01-01', slug='test-post'):
    return {'properties': {'Status': {'select': {'name': status}}, 'Public Approved': {'checkbox': approved}, 'Published Date': {'date': {'start': date} if date else None}, 'Slug': {'rich_text': text(slug)}, 'Name': {'title': text('Test')}}}

class SyncTests(unittest.TestCase):
    def test_publication_gate(self):
        now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        for candidate in [page(status='Draft'), page(approved=False), page(date='2099-01-01')]:
            self.assertIsNone(sync.metadata(candidate, now))
        self.assertEqual(sync.metadata(page(), now)['slug'], 'test-post')
        for candidate in [page(date=None), page(slug='../private')]:
            with self.assertRaises(ValueError): sync.metadata(candidate, now)
    def test_pagination(self):
        with patch.object(sync, 'request', side_effect=[{'results': [1], 'has_more': True, 'next_cursor': 'next'}, {'results': [2], 'has_more': False}]) as request:
            self.assertEqual(list(sync.paginate('source', {})), [1, 2])
            self.assertEqual(request.call_args.args[1]['start_cursor'], 'next')
    def test_private_mentions_fail(self):
        self.assertEqual(sync.rich([{'type': 'mention', 'mention': {'type': 'page'}, 'plain_text': '原文引用'}]), '原文引用')
        for url in ['https://www.notion.so/private', 'javascript:alert(1)']:
            with self.assertRaises(ValueError): sync.safe_url(url)
    def test_math_code_and_unknown_blocks(self):
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            output = sync.render([{'type': 'equation', 'equation': {'expression': 'x^2'}}, {'type': 'code', 'code': {'rich_text': text('a```b'), 'language': 'python'}}], folder)
            self.assertIn('$$\nx^2\n$$', output)
            self.assertIn('````python', output)
            with self.assertRaises(ValueError): sync.render([{'type': 'unsupported', 'unsupported': {}}], folder)
    def test_failed_sync_preserves_previous_content(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / 'content/posts').mkdir(parents=True)
            (root / 'content/posts/old.md').write_text('previous build')
            with patch.object(sync, 'ROOT', root), patch.dict(sync.os.environ, {'NOTION_TOKEN':'test', 'NOTION_DATA_SOURCE_ID':'a'*32}), patch.object(sync, 'paginate', side_effect=ValueError('fail')):
                with self.assertRaises(ValueError): sync.main()
            self.assertTrue((root / 'content/posts/old.md').exists())
    def test_empty_success_removes_withdrawn_posts(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / 'content/posts').mkdir(parents=True)
            (root / 'content/posts/old.md').write_text('withdrawn')
            with patch.object(sync, 'ROOT', root), patch.dict(sync.os.environ, {'NOTION_TOKEN':'test', 'NOTION_DATA_SOURCE_ID':'a'*32}), patch.object(sync, 'paginate', return_value=iter([])):
                sync.main()
            self.assertEqual(list((root / 'content/posts').iterdir()), [])
