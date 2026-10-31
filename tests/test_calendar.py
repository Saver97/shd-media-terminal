import tempfile, unittest
from pathlib import Path
from unittest.mock import MagicMock
from calendar_source import Calendar, normalize

class CalendarTests(unittest.TestCase):
    def test_names_empty_days_and_duplicate_rows(self):
        row={'id':4,'name':'Original','name_cn':'','images':{}}
        result=normalize([{'weekday':{'id':6},'items':[row,row]}])
        self.assertEqual(len(result),7)
        self.assertEqual(result[5]['items'][0]['title'],'Original')
        self.assertEqual(len(result[5]['items']),1)
        self.assertEqual(result[0]['items'],[])

    def test_cache_refresh_failure_and_empty_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            factory=MagicMock();response=factory.return_value.__enter__.return_value.get.return_value
            response.json.return_value=[{'weekday':{'id':1},'items':[]}]
            source=Calendar(Path(folder),factory)
            first=source.get({})
            self.assertFalse(first['cached'])
            self.assertTrue(source.get({})['cached'])
            self.assertEqual(factory.call_count,1)
            factory.side_effect=OSError('offline')
            stale=source.get({},True)
            self.assertTrue(stale['stale'])
            source.path.unlink()
            with self.assertRaises(RuntimeError):source.get({})
