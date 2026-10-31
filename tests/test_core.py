import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Store, direct_env, infohash, parse_results, source_session


class CoreTests(unittest.TestCase):
    def test_base32_magnet_matches_known_hex(self):
        self.assertEqual(infohash('magnet:?xt=urn:btih:GELIJUYY6EF3VPE626L4QM7WOSUS66JN'),
                         '311684d318f10bbabc9ed797c833f674a92f792d')

    def test_bad_magnet(self):
        with self.assertRaises(ValueError):
            infohash('https://example.com/not-a-magnet')

    def test_direct_env_removes_inherited_proxy_and_engine_configuration(self):
        with patch.dict(os.environ, {'https_proxy': 'http://localhost:9', 'ALL_PROXY': 'bad',
                                    'RQBIT_SOCKS_PROXY_URL': 'bad', 'RQBIT_LISTEN_PORT': '9', 'PATH': 'keep'}):
            env = direct_env()
            self.assertFalse(any(k.upper().endswith('_PROXY') or k.upper().startswith('RQBIT_') for k in env))
            self.assertEqual(env['PATH'], 'keep')

    def test_web_proxy_does_not_leak_to_direct_session(self):
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://localhost:9'}):
            with source_session({'proxy_mode': 'direct'}) as session:
                self.assertFalse(session.trust_env)
                self.assertEqual(session.proxies, {})
            with source_session({'proxy_mode': 'manual', 'proxy_url': 'http://127.0.0.1:7897'}) as session:
                self.assertEqual(session.proxies['https'], 'http://127.0.0.1:7897')

    def test_atomic_store_preserves_previous_state_on_error(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder)/'state.json')
            store.change(lambda d: d.update(history=[{'title':'old'}]))
            def broken(d):
                d['history'] = ['new']
                raise RuntimeError()
            with self.assertRaises(RuntimeError):
                store.change(broken)
            self.assertEqual(Store(store.path).snapshot()['history'], [{'title':'old'}])
            self.assertEqual(store.snapshot()['history'], [{'title':'old'}])

    def test_results_realistic_nested_keyword_and_hostile_title(self):
        html = '''<table id="topic_list"><tbody><tr><td>2026/10/12 13:08</td><td>动画</td><td class="title"><span class="tag">GMTeam</span><a href="/topics/view/1.html">[GM-Team][国漫][<span>牧神记</span>][2024][101][GB][1080P]&lt;img src=x&gt;</a></td><td><a href="magnet:?xt=urn:btih:GELIJUYY6EF3VPE626L4QM7WOSUS66JN">磁链</a></td><td>1GB</td><td>12</td></tr></tbody></table>'''
        row = parse_results(html)[0]
        self.assertEqual(row['episode'], '101')
        self.assertEqual(row['subtitle'], '简中')
        self.assertIn('<img src=x>', row['title'])
        self.assertEqual(row['url'], 'https://share.dmhy.org/topics/view/1.html')

    def test_challenge_page_is_not_silent_empty_search(self):
        with self.assertRaises(RuntimeError):
            parse_results('<html>Verify you are human</html>')


if __name__ == '__main__':
    unittest.main()
