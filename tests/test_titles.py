import tempfile, unittest
from unittest.mock import MagicMock
from title_names import decorate, TitleNames

class TitleTests(unittest.TestCase):
    def test_machine_name_does_not_replace_search_keyword(self):
        row=decorate({'id':713654,'title':'The Marsupilamis','original':'The Marsupilamis'})
        self.assertEqual(row['title'],'长尾豹一家')
        self.assertEqual(row['name_label'],'机翻')
        self.assertEqual(row['search_title'],'The Marsupilamis')
        row=decorate({'id':1,'title':'正式名称','original':'The Marsupilamis','has_cn':True})
        self.assertEqual(row['title'],'正式名称')
        self.assertEqual(row['name_label'],'')
        self.assertEqual(decorate({'id':2,'title':'罗德岛学院','original':'罗德岛学院','has_cn':False})['name_label'],'')

    def test_translation_cache_and_failure_keep_original(self):
        with tempfile.TemporaryDirectory() as folder:
            factory=MagicMock();response=factory.return_value.__enter__.return_value.get.return_value
            response.json.return_value={'responseStatus':200,'responseData':{'translatedText':'示例作品'}}
            service=TitleNames(folder,factory);row={'id':9,'title':'Example Show','original':'Example Show','has_cn':False}
            result=service.resolve([row],{})['9']
            self.assertEqual(result['title'],'示例作品');self.assertEqual(result['search_title'],'Example Show')
            self.assertEqual(result['name_label'],'机翻')
            service.resolve([row],{});self.assertEqual(factory.call_count,1)
            factory.side_effect=OSError('offline');row.update(id=10,title='Another Show',original='Another Show')
            result=service.resolve([row],{})['10'];self.assertEqual(result['title'],'Another Show');self.assertEqual(result['name_label'],'待译')
