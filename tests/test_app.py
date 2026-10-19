import base64
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from contextlib import closing
from pathlib import Path
from PIL import Image
from telescope.server import Server, normalize_image, validate
from telescope.storage import ROOT, Store


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=Server(('127.0.0.1',0),self.temp.name)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.origin=self.server.origin
        self.store=self.server.store

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        defaults={}
        if body is not None:
            defaults={'Content-Type':'application/json','Origin':self.origin,'X-CSRF-Token':self.request('/api/session')[1]['token']}
        defaults.update(headers or {})
        request=urllib.request.Request(self.origin+path,data=json.dumps(body).encode() if body is not None else None,headers=defaults)
        try: response=urllib.request.urlopen(request,timeout=5)
        except urllib.error.HTTPError as e: response=e
        with response:
            data=response.read()
            if response.headers.get('Content-Type','').startswith('application/json'): data=json.loads(data)
            return response.status,data

    def submission(self,**changes):
        result={'model_id':'ADD02','kind':'parameter','credit':'合成测试','consent':True,'field':'eye_relief_mm','value':18.5,'note':'使用合成测量记录验证投稿和审核流程。','source_url':'https://example.org/specs'}
        result.update(changes)
        return result

    def image(self):
        output=io.BytesIO()
        exif=Image.Exif();exif[270]='private camera metadata'
        Image.new('RGB',(80,60),'green').save(output,'JPEG',exif=exif)
        return base64.b64encode(output.getvalue()).decode()

    def test_catalog_download_and_no_private_content(self):
        status,catalog=self.request('/api/catalog')
        self.assertEqual(status,200)
        self.assertEqual(len(catalog['models']),92)
        self.assertEqual(sum(m['reference_price'] is not None for m in catalog['models']),61)
        serialized=json.dumps(catalog,ensure_ascii=False)
        for term in ('goofish.com','闲鱼','咸鱼','seller','ip_hash','会话附件','item_id'):
            self.assertNotIn(term,serialized)
        self.assertEqual(self.request('/../data/catalog.json')[0],404)
        self.assertEqual(self.request('/api/admin')[0],404)
        status,data=self.request('/downloads/telescopes.xlsx')
        self.assertEqual(status,200)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml=archive.read('xl/workbook.xml').decode()
            self.assertNotIn('推荐清单',xml)
            self.assertNotIn('闲鱼',xml)
            self.assertIn('望远镜参数',xml)
            text=''.join(archive.read(p).decode() for p in archive.namelist() if p.endswith('.xml'))
            self.assertNotIn('goofish.com',text)
            self.assertIn('参考入手价格',text)

    def test_parameter_moderation_and_upgrade_preservation(self):
        status,result=self.request('/api/submissions',self.submission())
        self.assertEqual(status,202)
        key=result['id']
        model=lambda:next(m for m in self.store.public()['models'] if m['id']=='ADD02')
        self.assertIsNone(model()['parameters']['eye_relief_mm'])
        self.assertEqual(len(self.store.review()),1)
        self.assertEqual(self.store.review(key)['payload']['value'],18.5)
        self.store.review(key,'approved')
        self.assertEqual(model()['parameters']['eye_relief_mm'],18.5)
        self.assertEqual(model()['verification']['eye_relief_mm'],'community')
        reloaded=Store(self.temp.name)
        saved=next(m for m in reloaded.public()['models'] if m['id']=='ADD02')
        self.assertEqual(saved['parameters']['eye_relief_mm'],18.5)
        self.assertNotIn('ip_hash',json.dumps(reloaded.public()))
        with self.assertRaises(ValueError): self.store.review(key,'approved')

    def test_photo_hidden_until_approved_and_exif_removed(self):
        status,result=self.request('/api/submissions',self.submission(kind='photo',equipment='合成相机',conditions='合成环境',image_data=self.image()))
        self.assertEqual(status,202)
        item=self.store.review(result['id']);path=Path(item['image_path'])
        with Image.open(path) as image:
            self.assertEqual(image.format,'JPEG')
            self.assertEqual(len(image.getexif()),0)
            self.assertNotIn('exif',image.info)
        self.assertEqual(self.request('/media/'+path.name)[0],404)
        self.assertEqual(self.store.public()['contributions'],[])
        self.store.review(result['id'],'approved')
        self.assertEqual(self.request('/media/'+path.name)[0],200)
        self.assertEqual(self.store.public()['contributions'][0]['equipment'],'合成相机')
        self.assertEqual(self.request('/media/../request-secret')[0],404)

    def test_rejected_photo_and_review_conflict(self):
        _,result=self.request('/api/submissions',self.submission(kind='photo',equipment='相机',conditions='测试条件',image_data=self.image()))
        image=self.store.review(result['id'])['image_path']
        self.store.review(result['id'],'rejected')
        self.assertEqual(self.request('/media/'+Path(image).name)[0],404)
        self.assertEqual(len(self.store.public()['contributions']),0)
        with self.assertRaises(ValueError): self.store.review(result['id'],'approved')

    def test_untrusted_requests(self):
        self.assertEqual(self.request('/api/submissions',self.submission(),{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/submissions',self.submission(),{'X-CSRF-Token':'invalid'})[0],403)
        self.assertEqual(self.request('/api/submissions',self.submission(),{'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('/api/catalog',headers={'Host':'evil.example'})[0],400)
        self.assertEqual(self.request('/api/submissions',self.submission(consent=False))[0],400)
        self.assertEqual(self.request('/api/submissions',self.submission(source_url='javascript:alert(1)'))[0],400)
        self.assertEqual(self.request('/api/submissions',self.submission(model_id='no-model'))[0],400)

    def test_field_validation_and_images(self):
        for value in (True,False,-1,0,float('inf'),float('nan'),'18'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): validate(self.submission(value=value),self.store)
        with self.assertRaises(ValueError): validate(self.submission(field='__proto__'),self.store)
        with self.assertRaises(ValueError): validate(self.submission(source_url='',note='太短'),self.store)
        with self.assertRaises(ValueError): normalize_image(base64.b64encode(b'<svg onload="alert(1)"></svg>').decode())
        with self.assertRaises(ValueError): normalize_image('not base64')
        self.assertEqual(len(self.store.review()),0)

    def test_rate_limit(self):
        for _ in range(6): self.assertEqual(self.request('/api/submissions',self.submission())[0],202)
        self.assertEqual(self.request('/api/submissions',self.submission())[0],429)
        self.assertEqual(len(self.store.review()),6)

    def test_derived_parameters_follow_approved_inputs(self):
        for field,value in [('objective_mm',50),('magnification',8),('field_deg',8)]:
            status,submission=self.request('/api/submissions',self.submission(field=field,value=value))
            self.assertEqual(status,202)
            self.store.review(submission['id'],'approved')
        model=next(m for m in self.store.public()['models'] if m['id']=='ADD02')
        self.assertEqual(model['parameters']['exit_pupil_mm'],6.25)
        self.assertEqual(model['parameters']['field_m'],139.9)
        self.assertEqual(model['verification']['field_m'],'derived')
        self.assertEqual(self.request('/api/submissions',self.submission(field='exit_pupil_mm',value=100))[0],400)

    def test_unknown_schema_fails_closed(self):
        other=Path(self.temp.name)/'future';other.mkdir()
        with closing(sqlite3.connect(other/'catalog.db')) as db: db.execute('PRAGMA user_version=999')
        with self.assertRaises(RuntimeError): Store(other)
        with closing(sqlite3.connect(other/'catalog.db')) as db: self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],999)


if __name__=='__main__': unittest.main()
