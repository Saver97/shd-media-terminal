import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from core import Service

class HandoffTests(unittest.TestCase):
    def test_legacy_bootstrap_never_starts_process_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir()
            (root/'data/library.json').write_text(json.dumps({'settings':{'proxy_mode':'direct','player':'old.exe'},'history':[{'title':'old'}],'subscriptions':[]}))
            with patch('core.subprocess.Popen') as launch:
                service=Service(root);data=service.bootstrap({})
                launch.assert_not_called()
                self.assertFalse(hasattr(service,'engine'))
                self.assertEqual(data['history'],[])
                self.assertEqual(service.store.snapshot()['history'],[{'title':'old'}])

    def test_handoff_preserves_magnet_as_one_argument_and_records_only_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);exe=root/'Thunder.exe';exe.touch();service=Service(root)
            service.settings({'proxy_mode':'direct','thunder_path':str(exe)})
            magnet='magnet:?xt=urn:btih:'+'a'*40+'&dn=Example%20Title&tr=https%3A%2F%2Fexample.com%2Fannounce'
            resource={'magnet':magnet,'title':'Example'}
            with patch('core.subprocess.Popen') as launch:
                result=service.launch_thunder({'resource':resource})
                self.assertEqual(launch.call_args.args[0],[str(exe),magnet,'-StartType:magnet'])
                self.assertEqual(result['history'][0]['resource']['magnet'],magnet)
            before=service.library({})
            with patch('core.subprocess.Popen',side_effect=OSError('failed')):
                with self.assertRaises(OSError):service.launch_thunder({'resource':{'magnet':magnet.replace('a'*40,'b'*40)}})
            self.assertEqual(service.library({}),before)
            with patch('core.subprocess.Popen') as launch:
                with self.assertRaises(ValueError):service.launch_thunder({'resource':{'magnet':'https://example.com'}})
                launch.assert_not_called()
