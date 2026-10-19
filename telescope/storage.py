"""Persistent catalog and a single moderation boundary for all public contributions."""
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, directory, catalog=ROOT/'data/catalog.json'):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.images=self.directory/'images'
        self.images.mkdir(exist_ok=True)
        self.db=self.directory/'catalog.db'
        self.catalog=json.loads(Path(catalog).read_text(encoding='utf-8'))
        self.fields={f['key']:f for f in self.catalog['fields']}
        with closing(self.connect()) as db, db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1): raise RuntimeError('Unsupported database version; refusing to modify it')
            db.executescript('''
              CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS submissions(
                id TEXT PRIMARY KEY,model_id TEXT NOT NULL REFERENCES models(id),kind TEXT NOT NULL,
                payload TEXT NOT NULL,image TEXT,status TEXT NOT NULL DEFAULT 'pending',
                created TEXT NOT NULL,reviewed TEXT,ip_hash TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS submission_status ON submissions(status,created);
              CREATE INDEX IF NOT EXISTS submission_ip ON submissions(ip_hash,created);
              CREATE TABLE IF NOT EXISTS overrides(
                model_id TEXT NOT NULL REFERENCES models(id),field TEXT NOT NULL,value TEXT NOT NULL,
                submission_id TEXT NOT NULL REFERENCES submissions(id),PRIMARY KEY(model_id,field));
              PRAGMA user_version=1;
            ''')
            db.executemany('INSERT INTO models(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
               [(m['id'],json.dumps(m,ensure_ascii=False)) for m in self.catalog['models']])

    def connect(self):
        db=sqlite3.connect(self.db,timeout=10)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def public(self):
        with closing(self.connect()) as db:
            models={r['id']:json.loads(r['payload']) for r in db.execute('SELECT * FROM models ORDER BY id')}
            for r in db.execute('SELECT o.*,s.payload,s.reviewed FROM overrides o JOIN submissions s ON s.id=o.submission_id'):
                m=models[r['model_id']]
                if r['field']=='reference_price':
                    m['reference_price']=json.loads(r['value'])
                    m['price_asof']=r['reviewed'][:10]
                else:
                    m['parameters'][r['field']]=json.loads(r['value'])
                    m['verification'][r['field']]='community'
                p=json.loads(r['payload'])
                m.setdefault('community_sources',{})[r['field']]={k:p.get(k,'') for k in ('credit','note','source_url')}
            contributions=[]
            for r in db.execute("SELECT * FROM submissions WHERE status='approved' ORDER BY created DESC"):
                p=json.loads(r['payload'])
                contributions.append({'id':r['id'],'model_id':r['model_id'],'kind':r['kind'],'created':r['created'],
                    **{k:p.get(k,'') for k in ('credit','note','equipment','conditions','field','value','source_url')},
                    'image_url':f"/media/{r['image']}" if r['image'] else None})
            return {**{k:v for k,v in self.catalog.items() if k!='models'},'models':list(models.values()),'contributions':contributions}

    def submit(self, model_id, kind, payload, image, ip_hash):
        key=uuid.uuid4().hex
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM models WHERE id=?',(model_id,)).fetchone(): raise ValueError('型号不存在')
            recent=db.execute("SELECT COUNT(*) FROM submissions WHERE ip_hash=? AND created>strftime('%Y-%m-%dT%H:%M:%S','now','-1 hour')",(ip_hash,)).fetchone()[0]
            today=db.execute("SELECT COUNT(*) FROM submissions WHERE created>strftime('%Y-%m-%dT%H:%M:%S','now','-1 day')").fetchone()[0]
            pending=db.execute("SELECT COUNT(*) FROM submissions WHERE status='pending'").fetchone()[0]
            if recent>=6 or today>=200 or pending>=1000: raise OverflowError('投稿较多，请稍后再试')
            db.execute('INSERT INTO submissions(id,model_id,kind,payload,image,created,ip_hash) VALUES(?,?,?,?,?,?,?)',
                (key,model_id,kind,json.dumps(payload,ensure_ascii=False),image,now(),ip_hash))
        return key

    def review(self, key=None, action=None):
        with closing(self.connect()) as db, db:
            if not key:
                return [dict(r) for r in db.execute("SELECT id,model_id,kind,created FROM submissions WHERE status='pending' ORDER BY created")]
            row=db.execute('SELECT * FROM submissions WHERE id=?',(key,)).fetchone()
            if not row: raise ValueError('投稿不存在')
            result=dict(row)
            result['payload']=json.loads(result['payload'])
            if not action:
                result['image_path']=str(self.images/row['image']) if row['image'] else None
                return result
            if action not in ('approved','rejected'): raise ValueError('审核操作无效')
            if row['image'] and action=='approved' and not (self.images/row['image']).is_file(): raise ValueError('图片缺失，不能批准')
            if db.execute("UPDATE submissions SET status=?,reviewed=? WHERE id=? AND status='pending'",(action,now(),key)).rowcount!=1:
                raise ValueError('投稿已审核，拒绝重复操作')
            if action=='approved' and row['kind']=='parameter':
                p=result['payload']
                db.execute('INSERT INTO overrides(model_id,field,value,submission_id) VALUES(?,?,?,?) ON CONFLICT(model_id,field) DO UPDATE SET value=excluded.value,submission_id=excluded.submission_id',
                   (row['model_id'],p['field'],json.dumps(p['value'],ensure_ascii=False),key))
            return {'id':key,'status':action}

    def public_image(self, filename):
        with closing(self.connect()) as db:
            allowed=db.execute("SELECT 1 FROM submissions WHERE image=? AND status='approved'",(filename,)).fetchone()
        return self.images/filename if allowed else None
