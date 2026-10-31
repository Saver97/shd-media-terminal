"""Bangumi broadcast calendar and bounded local cover cache."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlparse
from title_names import decorate

def normalize(payload):
    if not isinstance(payload,list) or not payload:
        raise ValueError('日历返回格式异常')
    days={n:[] for n in range(1,8)}
    for day in payload:
        number=day['weekday']['id']
        if number not in days or not isinstance(day['items'],list):
            raise ValueError('日历星期格式异常')
        seen=set()
        for item in day['items']:
            ident=int(item['id'])
            title=str(item.get('name_cn') or item.get('name') or '').strip()
            if ident<=0 or not title or ident in seen or item.get('type',2)!=2:continue
            seen.add(ident)
            days[number].append({'id':ident,'title':title,'original':str(item.get('name') or title),'has_cn':bool(str(item.get('name_cn') or '').strip()),
                                 'air_date':str(item.get('air_date') or ''),
                                 'cover':(item.get('images') or {}).get('medium') or (item.get('images') or {}).get('small','')})
    return [{'weekday':n,'items':items} for n,items in days.items()]

def present(value, **flags):
    return dict(value, days=[dict(d, items=[decorate(x) for x in d['items']]) for d in value['days']], **flags)

class Calendar:
    def __init__(self, root, session_factory):
        self.root=Path(root)/'data'
        self.path=self.root/'calendar.json'
        self.session_factory=session_factory
        self.lock=threading.Lock()

    def read(self):
        try:
            value=json.loads(self.path.read_text('utf-8'))
            if not isinstance(value['days'],list) or len(value['days'])!=7: return None
            float(value['timestamp'])
            return value
        except (OSError,ValueError,KeyError,TypeError):return None

    def get(self, settings, force=False):
        with self.lock:
            cached=self.read()
            if cached and not force and 0<=time.time()-cached['timestamp']<21600:
                return present(cached,cached=True,stale=False)
            try:
                with self.session_factory(settings) as session:
                    session.headers['User-Agent']='SHD-Media/0.3 (Windows; personal Bangumi calendar client)'
                    response=session.get('https://api.bgm.tv/calendar',timeout=(8,20))
                    response.raise_for_status()
                    days=normalize(response.json())
            except Exception as exc:
                if cached:return present(cached,cached=True,stale=True,notice='更新失败，正在显示上次缓存的放送表。')
                raise RuntimeError('新番日历暂时无法获取，请检查资源站代理或稍后重试。') from exc
            result={'days':days,'timestamp':time.time(),'updated':time.strftime('%Y-%m-%d %H:%M')}
            self.root.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False),'utf-8');tmp.replace(self.path)
            return present(result,cached=False,stale=False)

    def covers(self, settings, weekday, ids=None):
        cached=self.read()
        if not cached:return {}
        rows=next((d['items'] for d in cached['days'] if d['weekday']==weekday),[])[:60]
        if ids is not None:rows=[x for x in rows if x['id'] in ids]
        def fetch(item):
            url=str(item.get('cover') or '')
            parts=urlparse(url.replace('/cover/s/', '/cover/m/'))
            if parts.hostname!='lain.bgm.tv' or parts.scheme not in ('http','https'):return None
            path=self.root/'calendar-covers'/f"{item['id']}-medium.img"
            try:
                if path.is_file() and time.time()-path.stat().st_mtime<7*86400:
                    raw=path.read_bytes()
                else:
                    with self.session_factory(settings) as session:
                        with session.get('https://lain.bgm.tv'+parts.path,timeout=(4,6),stream=True,allow_redirects=False) as r:
                            if r.status_code!=200:return None
                            raw=b''
                            for chunk in r.iter_content(16384):
                                raw+=chunk
                                if len(raw)>131072:return None
                mime='image/jpeg' if raw.startswith(b'\xff\xd8\xff') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else None
                if not mime:return None
                path.parent.mkdir(parents=True,exist_ok=True)
                if not path.exists() or time.time()-path.stat().st_mtime>=7*86400:path.write_bytes(raw)
                return str(item['id']),'data:'+mime+';base64,'+base64.b64encode(raw).decode()
            except Exception:return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            return dict(result for result in pool.map(fetch,rows) if result)
