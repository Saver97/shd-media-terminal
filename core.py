"""SHD Media: resource discovery and explicit Thunder handoff; no BT engine."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import getproxies

import requests
from bs4 import BeautifulSoup
from calendar_source import Calendar
from title_names import TitleNames

ROOT = Path(__file__).resolve().parent
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def infohash(magnet):
    if not str(magnet).startswith('magnet:?'):
        raise ValueError('不是有效的磁力链接')
    for xt in parse_qs(urlparse(magnet).query).get('xt', []):
        if xt.lower().startswith('urn:btih:'):
            value = xt[9:]
            if re.fullmatch('[0-9a-fA-F]{40}', value):
                return value.lower()
            if re.fullmatch('[a-zA-Z2-7]{32}', value):
                return base64.b32decode(value.upper()).hex()
    raise ValueError('暂不支持此磁链格式，需要 BTIH 磁链')


def direct_env():
    return {k: v for k, v in os.environ.items()
            if not k.upper().startswith('RQBIT_') and not k.upper().endswith('_PROXY')}


def detect_thunder():
    if os.name != 'nt':
        return ''
    import winreg
    for scheme in ('thunder', 'magnet'):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, scheme + r'\shell\open\command') as key:
                command = winreg.QueryValue(key, None).strip()
            match = re.match(r'^"([^"\r\n]+\.exe)"', command, re.I)
            if match:
                path = Path(match.group(1))
                if path.name.lower() == 'thunder.exe' and path.is_file():
                    return str(path)
        except OSError:
            pass
    return ''


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        defaults = {'settings': {'proxy_mode': 'system', 'proxy_url': '',
                    'thunder_path': detect_thunder()},
                    'history': [], 'dispatch_history': [], 'subscriptions': [], 'labels': {}}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text('utf-8'))
                defaults.update(loaded)
            except (ValueError, OSError) as e:
                raise RuntimeError('本地配置读取失败，请检查 data/library.json；原文件未覆盖') from e
        defaults['settings'].setdefault('thunder_path', detect_thunder())
        self.data = defaults

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.data))

    def change(self, fn):
        with self.lock:
            old = self.snapshot()
            try:
                fn(self.data)
                tmp = self.path.with_suffix('.tmp')
                tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), 'utf-8')
                os.replace(tmp, self.path)
            except Exception:
                self.data = old
                raise


def source_session(settings):
    session = requests.Session()
    session.trust_env = False
    mode = settings.get('proxy_mode', 'system')
    if mode == 'manual':
        proxy = settings.get('proxy_url', '').strip()
        parsed = urlparse(proxy)
        if parsed.scheme not in ('http', 'https', 'socks5', 'socks5h') or not parsed.hostname:
            raise ValueError('代理地址需要 http://主机:端口 或 socks5h://主机:端口')
        session.proxies = {'http': proxy, 'https': proxy}
    elif mode == 'system':
        session.proxies = {k: v for k, v in getproxies().items() if k in ('http', 'https', 'all')}
    elif mode != 'direct':
        raise ValueError('未知的代理模式')
    session.headers['User-Agent'] = 'SHD-Media/0.1 (Desktop; resource search)'
    return session


def parse_results(html):
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.select_one('#topic_list')
    if not table:
        if soup.select_one('form input[name="keyword"]') or '沒有符合' in soup.get_text() or '没有符合' in soup.get_text():
            return []
        raise RuntimeError('资源站返回了非搜索页面，可能需要浏览器验证或稍后重试')
    rows = []
    for tr in table.select('tbody tr'):
        link = tr.select_one('td.title a[href*="/topics/view/"]')
        magnet = tr.select_one('a[href^="magnet:"]')
        if not link or not magnet:
            continue
        cells = tr.find_all('td', recursive=False)
        title = link.get_text('', strip=True)
        tag = tr.select_one('.tag')
        match = re.search(r'\[\s*(\d{1,3}(?:\s*[-–]\s*\d{1,3})?)\s*\]', title)
        if not match:
            match = re.search(r'(?: - |第)(\d{1,3}(?:[-–]\d{1,3})?)', title)
        quality = re.search(r'(?i)(2160p|1080p|720p|4k)', title)
        caption = '简繁' if any(t in title for t in ('简繁', '簡繁')) else '简中' if re.search(r'简|簡|\bGB\b|\bCHS\b', title, re.I) else '繁中' if re.search(r'繁|\bBIG5\b|\bCHT\b', title, re.I) else '未标注'
        rows.append({'hash': infohash(magnet['href']), 'title': title, 'magnet': magnet['href'],
                     'url': urljoin('https://share.dmhy.org', link['href']),
                     'group': tag.get_text(' ', strip=True) if tag else '',
                     'date': cells[0].get_text(' ', strip=True)[:16],
                     'size': cells[4].get_text(strip=True) if len(cells) > 4 else '',
                     'seeds': cells[5].get_text(strip=True) if len(cells) > 5 else '—',
                     'episode': match.group(1) if match else '',
                     'quality': quality.group(1).upper() if quality else '未标注', 'subtitle': caption})
    return rows


def search_source(settings, query, page=1):
    query = str(query).strip()[:180]
    if not query:
        raise ValueError('请输入作品名或字幕组')
    with source_session(settings) as session:
        response = session.get(f'https://share.dmhy.org/topics/list/page/{max(1, int(page))}',
                               params={'keyword': query}, timeout=(10, 25))
        response.raise_for_status()
        response.encoding = 'utf-8'
        rows = parse_results(response.text)
    return {'items': rows, 'query': query, 'page': int(page), 'has_more': len(rows) >= 50}


class Service:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.store = Store(self.root / 'data' / 'library.json')
        self.subscription_lock = threading.Lock()
        self.calendar_source = Calendar(self.root, source_session)
        self.title_names = TitleNames(self.root, source_session)

    def bootstrap(self, _):
        state = self.store.snapshot()
        return {'settings': state['settings'], 'subscriptions': state['subscriptions'],
                'history': state['dispatch_history'], 'version': '0.4.0'}

    def search(self, data):
        return search_source(self.store.snapshot()['settings'], data.get('query'), data.get('page', 1))

    def calendar(self, data):
        return self.calendar_source.get(self.store.snapshot()['settings'], bool(data.get('force')))

    def calendar_titles(self, data):
        day = int(data.get('weekday', 1))
        if day not in range(1, 8):
            raise ValueError('无效星期')
        cached = self.calendar_source.read()
        rows = next((d['items'] for d in cached['days'] if d['weekday'] == day), []) if cached else []
        return self.title_names.resolve(rows, self.store.snapshot()['settings'])

    def calendar_covers(self, data):
        day = int(data.get('weekday', 1))
        if day not in range(1, 8):
            raise ValueError('无效星期')
        return self.calendar_source.covers(self.store.snapshot()['settings'], day)

    def subscription_covers(self, data):
        cached = self.calendar_source.read()
        if not cached:
            try:
                self.calendar({})
                cached = self.calendar_source.read()
            except Exception:
                return {}
        if not cached:
            return {}
        normalize_name = lambda value: re.sub(r'[\W_]+', '', str(value)).casefold()
        wanted = set(str(x) for x in data.get('ids', []))
        state = self.store.snapshot()
        matches = {}
        for sub in state['subscriptions']:
            if sub['id'] not in wanted:
                continue
            name = normalize_name(sub['query'])
            candidates = [(d['weekday'], item['id']) for d in cached['days'] for item in d['items']
                          if name and name in (normalize_name(item['title']), normalize_name(item['original']))]
            if len(set(candidates)) == 1:
                matches[sub['id']] = candidates[0]
        result = {}
        for day in sorted({day for day, _ in matches.values()}):
            ids = {ident for weekday, ident in matches.values() if weekday == day}
            covers = self.calendar_source.covers(state['settings'], day, ids)
            for sub_id, (weekday, ident) in matches.items():
                if weekday == day and str(ident) in covers:
                    result[sub_id] = covers[str(ident)]
        return result

    def library(self, _):
        state = self.store.snapshot()
        return {'history': state['dispatch_history'], 'subscriptions': state['subscriptions']}

    def settings(self, data):
        settings = {k: str(data.get(k, '')).strip() for k in ('proxy_mode', 'proxy_url', 'thunder_path')}
        path = settings['thunder_path']
        if path and (not Path(path).is_file() or Path(path).name.lower() != 'thunder.exe'):
            raise ValueError('请选择有效的 Thunder.exe 程序')
        with source_session(settings):
            pass
        self.store.change(lambda state: state.update(settings=settings))
        return settings

    def test_proxy(self, data):
        started = time.monotonic()
        with source_session(data) as session:
            response = session.get('https://share.dmhy.org/', timeout=(8, 15))
            response.raise_for_status()
            if 'topic_list' not in response.text:
                raise RuntimeError('连接成功但未获得资源列表，可能遇到验证页面')
        return {'milliseconds': round((time.monotonic() - started) * 1000)}

    def launch_thunder(self, data):
        resource = data.get('resource') or {}
        magnet = str(resource.get('magnet', ''))
        if len(magnet) > 24000 or any(ord(c) < 32 for c in magnet):
            raise ValueError('磁链格式异常或过长')
        hash_value = infohash(magnet)
        executable = self.store.snapshot()['settings'].get('thunder_path') or detect_thunder()
        if not executable or not Path(executable).is_file() or Path(executable).name.lower() != 'thunder.exe':
            raise ValueError('未找到迅雷，请在设置中选择 Thunder.exe')
        # Argument array preserves the whole magnet; never execute registry command text.
        subprocess.Popen([executable, magnet, '-StartType:magnet'], env=direct_env())
        item = {'hash': hash_value, 'title': str(resource.get('title') or hash_value),
                'time': time.strftime('%Y-%m-%d %H:%M'), 'resource': dict(resource)}
        def update(state):
            state['dispatch_history'] = [item] + [h for h in state['dispatch_history'] if h['hash'] != hash_value][:99]
        self.store.change(update)
        return {'history': self.store.snapshot()['dispatch_history']}

    def subscribe(self, data):
        query = str(data.get('query', '')).strip()[:180]
        if not query:
            raise ValueError('请输入追番关键词')
        entry = {'id': secrets.token_hex(6), 'query': query, 'group': str(data.get('group', '')),
                 'quality': str(data.get('quality', '')), 'subtitle': str(data.get('subtitle', '')),
                 'items': [], 'checked': '', 'error': ''}
        def update(state):
            if any(all(s[k] == entry[k] for k in ('query', 'group', 'quality', 'subtitle')) for s in state['subscriptions']):
                raise ValueError('相同的追番规则已经存在')
            state['subscriptions'].append(entry)
        self.store.change(update)
        return self.store.snapshot()['subscriptions']

    def unsubscribe(self, data):
        self.store.change(lambda state: state.update(subscriptions=[s for s in state['subscriptions'] if s['id'] != data['id']]))
        return self.store.snapshot()['subscriptions']

    def check_subscriptions(self, _):
        if not self.subscription_lock.acquire(blocking=False):
            return self.store.snapshot()['subscriptions']
        try:
            for entry in self.store.snapshot()['subscriptions']:
                try:
                    items = self.search({'query': entry['query']})['items']
                    items = [r for r in items if all(not entry[k] or entry[k] == r[k] for k in ('group', 'quality', 'subtitle'))]
                    error = ''
                except Exception:
                    items, error = entry.get('items', []), '更新失败，请检查资源站连接'
                def update(state):
                    target = next((s for s in state['subscriptions'] if s['id'] == entry['id']), None)
                    if target:
                        target.update(items=items, error=error, checked=time.strftime('%m-%d %H:%M'))
                self.store.change(update)
            return self.store.snapshot()['subscriptions']
        finally:
            self.subscription_lock.release()
