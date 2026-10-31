import tempfile,unittest
from pathlib import Path
from core import Service

class HistoryTests(unittest.TestCase):
    def test_delete_selected_preserves_handoff_marks_and_subscriptions(self):
        with tempfile.TemporaryDirectory() as folder:
            service=Service(Path(folder))
            service.store.change(lambda s:s.update(dispatch_history=[{'hash':'a'},{'hash':'b'}],handed_off=['a','b'],subscriptions=[{'id':'keep'}]))
            result=service.delete_history({'hashes':['a','unknown']})
            self.assertEqual(result['history'],[{'hash':'b'}])
            self.assertEqual(result['handed_off'],['a','b'])
            self.assertEqual(result['subscriptions'],[{'id':'keep'}])
            self.assertEqual(Service(Path(folder)).library({})['history'],[{'hash':'b'}])
            service.delete_history({'hashes':['b']})
            self.assertEqual(service.library({})['history'],[])
            with self.assertRaises(ValueError):service.delete_history({'hashes':'a'})
