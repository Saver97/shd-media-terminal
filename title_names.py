"""Readable Chinese annotations; never mistake a generated name for a release title."""
import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Reviewed AI translations, deliberately not presented as official Chinese titles.
LOCAL_NAMES = {
    'Electro Andes': '电子安第斯',
    'The Marsupilamis': '长尾豹一家',
    '歯ならび～ズ': '牙齿小伙伴',
    'Kiff: Scarm II: The Screamwriter': '基夫：惊魂记2——尖叫编剧',
    'マゼンチュ': '马赞丘',
    'ゲルぴよ 第2期': '格尔皮约 第二季',
    'ちょこっとヤバシティ': '有点不妙的城市',
    'シルバニアファミリー フレアのカラフル・エブリデイ': '森林家族：芙蕾雅的缤纷日常',
    'Dreamland': '梦境之地',
    'しろたん': '小白海豹',
    'ねずみくんのチョッキ 第2期': '小老鼠的背心 第二季',
    'ふんばるず': '加油小伙伴',
    'ぷにるんず ぷに４': '噗尼萌 第四季',
    'ゆるゆる図鑑': '轻松图鉴',
    '【活動記録】間章 Dream Interlude「陽ノ下に咲く蓮」（蓮ノ空女学院スクールアイドルクラブ）': '【活动记录】间章 梦之间奏「阳光下绽放的莲花」（莲之空女学院学园偶像俱乐部）',
}

def chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]',text)) and not re.search(r'[\u3040-\u30ff]',text)

def decorate(item):
    item=dict(item)
    original=item['original']
    # Old cache schema did not record name_cn. Differing names are preserved.
    has_cn=item.get('has_cn',item['title']!=original) or chinese(original)
    if has_cn:
        item.update(name_label='',search_title=item['title'])
    elif original in LOCAL_NAMES:
        item.update(title=LOCAL_NAMES[original],name_label='机翻',name_note='AI 暂译，非正式中文片名；搜索使用原名。',search_title=original)
    else:
        item.update(name_label='待译',search_title=original)
    return item

class TitleNames:
    def __init__(self, root, factory):
        self.path=Path(root)/'data/title-translations.json'
        self.factory=factory
        self.lock=threading.Lock()

    def resolve(self, items, settings):
        with self.lock:
            try:cache=json.loads(self.path.read_text('utf-8'))
            except (OSError,ValueError):cache={}
            if not isinstance(cache,dict):cache={}
            rows=[decorate(x) for x in items]
            pending=[x for x in rows if x['name_label']=='待译'][:10]
            def translate(item):
                original=item['original'];old=cache.get(original)
                if isinstance(old,dict) and time.time()-old.get('at',0)<(30*86400 if old.get('title') else 3600):return original,old
                value={'at':time.time(),'title':''}
                if len(original.encode('utf-8'))>500:return original,value
                lang='ja' if re.search(r'[\u3040-\u30ff]',original) else 'en' if original.isascii() else None
                if not lang:return original,value
                try:
                    with self.factory(settings) as s:
                        r=s.get('https://api.mymemory.translated.net/get',params={'q':original,'langpair':lang+'|zh-CN','mt':'1'},timeout=(4,10))
                        r.raise_for_status();j=r.json()
                    title=html.unescape(str(j.get('responseData',{}).get('translatedText',''))).strip()
                    if str(j.get('responseStatus'))=='200' and 0<len(title)<=180 and title!=original and chinese(title):value['title']=title
                except Exception:pass
                return original,value
            if pending:
                with ThreadPoolExecutor(max_workers=3) as pool:cache.update(pool.map(translate,pending))
                self.path.parent.mkdir(parents=True,exist_ok=True)
                tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(cache,ensure_ascii=False),'utf-8');tmp.replace(self.path)
            result={}
            for row in rows:
                title=(cache.get(row['original']) or {}).get('title') if row['name_label']=='待译' else None
                if title:row.update(title=title,name_label='机翻',name_note='MyMemory 自动翻译，非正式中文片名；搜索使用原名。')
                result[str(row['id'])]=row
            return result
