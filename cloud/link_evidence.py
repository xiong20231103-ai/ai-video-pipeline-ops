"""Independent evidence store. Source events never overwrite cloud decisions."""
import base64
from contextlib import contextmanager, closing
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import sqlite3
import time
import uuid

DAY = 86400
LOG = logging.getLogger(__name__)


class Evidence:
    def __init__(self, root, clock=time.time, cap=5 * 1024**3):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock, self.cap = clock, cap
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS records (
              id TEXT PRIMARY KEY, source TEXT NOT NULL, platform TEXT NOT NULL,
              video_id TEXT NOT NULL, judge_round TEXT NOT NULL, seq INTEGER NOT NULL,
              payload TEXT NOT NULL, uploaded REAL NOT NULL, review TEXT,
              delivery TEXT NOT NULL, decided REAL, revision INTEGER NOT NULL DEFAULT 0,
              cloud_decision INTEGER NOT NULL DEFAULT 0, sha TEXT,
              UNIQUE(source,platform,video_id,judge_round));
            CREATE TABLE IF NOT EXISTS shots(sha TEXT PRIMARY KEY,path TEXT NOT NULL,size INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS actions(
              id TEXT PRIMARY KEY,record_id TEXT NOT NULL,kind TEXT NOT NULL,
              actor TEXT NOT NULL,created REAL NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / 'links.db', timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _cleanup(self, db, needed=0):
        freed = count = 0
        now = self.clock()
        # Shared images stay protected while ANY referencing record is pending.
        rows = db.execute('''SELECT s.*,MAX(COALESCE(r.decided,r.uploaded)) AS age,
          MAX(CASE WHEN r.review='pending' THEN 1 ELSE 0 END) AS protected
          FROM shots s LEFT JOIN records r ON r.sha=s.sha GROUP BY s.sha ORDER BY age''').fetchall()
        total = sum(r['size'] for r in rows)
        for r in rows:
            if r['protected']:
                continue
            if r['age'] is not None and now-r['age'] < 15*DAY and total+needed <= self.cap:
                continue
            (self.root / r['path']).unlink(missing_ok=True)
            db.execute('DELETE FROM shots WHERE sha=?', (r['sha'],))
            db.execute('UPDATE records SET sha=NULL WHERE sha=?', (r['sha'],))
            count += 1
            freed += r['size']
            total -= r['size']
        LOG.info('evidence_cleanup count=%d bytes=%d', count, freed)
        return total

    def cleanup(self):
        with self.db() as db:
            total=self._cleanup(db)
            if total+600*1024<=self.cap:
                db.execute("INSERT OR REPLACE INTO evidence_settings VALUES('capacity_blocked','0')")
            return total

    def ingest(self, event):
        required = ('source', 'platform', 'video_id', 'judge_round', 'url')
        if any(not isinstance(event.get(k), str) or not 0 < len(event[k]) <= 2048 for k in required):
            raise ValueError('invalid_identity')
        if type(event.get('seq')) is not int or event['seq'] < 1:
            raise ValueError('invalid_sequence')
        review = event.get('review')
        delivery = event.get('delivery', 'not_applicable')
        if review not in {None,'pending','confirmed','rejected','expired'} or delivery not in {'not_applicable','waiting','sent','failed'}:
            raise ValueError('invalid_state')
        decided = event.get('decidedAt')
        if decided is not None and (type(decided) not in (int,float) or decided <= 0 or decided > self.clock()+300):
            raise ValueError('invalid_decision_time')
        raw = None
        if event.get('image'):
            from PIL import Image
            raw = base64.b64decode(event['image'], validate=True)
            if len(raw) > 600*1024:
                raise ValueError('image_too_large')
            with Image.open(BytesIO(raw)) as im:
                if im.format != 'JPEG' or max(im.size) > 1600:
                    raise ValueError('invalid_jpeg')
                im.verify()
        key = tuple(event[k] for k in required[:4])
        payload = {k:v for k,v in event.items() if k != 'image'}
        with self.db() as db:
            old = db.execute('SELECT * FROM records WHERE source=? AND platform=? AND video_id=? AND judge_round=?',key).fetchone()
            if old and event['seq'] < old['seq'] and not raw:
                return {'id':old['id'], 'stale':True, 'image':'unchanged'}
            if old and event['seq'] == old['seq'] and not raw:
                return {'id':old['id'], 'stale':True, 'image':'unchanged'}
            # Equal-sequence retries may repair missing images, never replay state.
            if old and event['seq'] <= old['seq']:
                payload=json.loads(old['payload'])
                review,delivery,decided=old['review'],old['delivery'],old['decided']
                event={**event,'seq':old['seq']}
            identifier = old['id'] if old else uuid.uuid4().hex
            sha = old['sha'] if old else None
            image_status = 'unchanged' if sha else 'missing'
            if raw:
                digest = hashlib.sha256(raw).hexdigest()
                existing = db.execute('SELECT sha FROM shots WHERE sha=?',(digest,)).fetchone()
                if existing or self._cleanup(db,len(raw)) + len(raw) <= self.cap:
                    if not existing:
                        relative = Path('shots') / time.strftime('%Y-%m-%d',time.gmtime(self.clock())) / (digest+'.jpg')
                        target = self.root / relative
                        target.parent.mkdir(parents=True,exist_ok=True)
                        tmp = target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                        tmp.write_bytes(raw)
                        tmp.replace(target)
                        db.execute('INSERT INTO shots VALUES(?,?,?)',(digest,str(relative),len(raw)))
                    sha, image_status = digest, 'stored'
                else:
                    image_status = 'capacity_rejected'
                    db.execute("INSERT OR REPLACE INTO evidence_settings VALUES('capacity_blocked','1')")
            cloud = old and old['cloud_decision']
            if old and decided is None and old['review']==review:
                decided=old['decided']
            db.execute('''INSERT INTO records(id,source,platform,video_id,judge_round,seq,payload,uploaded,review,delivery,decided,sha)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET seq=excluded.seq,
              payload=excluded.payload,review=excluded.review,delivery=excluded.delivery,decided=excluded.decided,sha=excluded.sha''',
              (identifier,*key,event['seq'],json.dumps(payload,ensure_ascii=False),old['uploaded'] if old else self.clock(),
               old['review'] if cloud else review, old['delivery'] if cloud else delivery, old['decided'] if cloud else decided,sha))
            return {'id':identifier,'stale':False,'image':image_status}

    def listing(self,limit=1000,offset=0):
        if type(limit) is not int or not 1<=limit<=1000 or type(offset) is not int or offset<0:
            raise ValueError('invalid_link_page')
        with self.db() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM records ORDER BY uploaded DESC,id LIMIT ? OFFSET ?',(limit,offset))]
            record_count=db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
            total = db.execute("SELECT COUNT(*) FROM records WHERE review='pending'").fetchone()[0]
            size = db.execute('SELECT COALESCE(SUM(size),0) FROM shots').fetchone()[0]
            capacity_blocked=db.execute("SELECT value FROM evidence_settings WHERE key='capacity_blocked'").fetchone()
            displayable = db.execute("SELECT COUNT(*) FROM records WHERE review='pending' AND sha IS NOT NULL AND json_extract(payload,'$.displayable')=1").fetchone()[0]
        for r in rows:
            r['payload'] = json.loads(r['payload'])
        return {'items':rows,'total':record_count,'nextOffset':offset+len(rows) if offset+len(rows)<record_count else None,'pending':total,'displayable':displayable,'imageBytes':size,'imageCapacity':self.cap,'capacityReached':size>=self.cap or bool(capacity_blocked and capacity_blocked['value']=='1')}

    def decide(self, identifier, revision, decision, request_id, actor):
        if decision not in {'confirmed','rejected'} or not isinstance(request_id,str) or not 1<=len(request_id)<=128:
            raise ValueError('invalid_decision')
        with self.db() as db:
            previous = db.execute('SELECT * FROM actions WHERE id=?',(request_id,)).fetchone()
            if previous:
                if previous['record_id']!=identifier or previous['kind']!=decision or previous['actor']!=actor:
                    raise ValueError('request_id_conflict')
                return json.loads(previous['payload'])
            r = db.execute('SELECT * FROM records WHERE id=?',(identifier,)).fetchone()
            if not r or r['revision']!=revision or r['review']!='pending':
                raise ValueError('revision_conflict')
            if decision=='confirmed' and (not r['sha'] or not json.loads(r['payload']).get('displayable')):
                raise ValueError('not_displayable')
            snapshot=json.loads(r['payload'])
            result = {'id':identifier,'review':decision,'revision':revision+1,'decidedAt':self.clock(),
                      'source':r['source'],'platform':r['platform'],'video_id':r['video_id'],'judge_round':r['judge_round'],
                      'sourceFingerprint':snapshot.get('sourceFingerprint'),'replace_id':snapshot.get('replace_id')}
            db.execute('UPDATE records SET review=?,decided=?,revision=revision+1,cloud_decision=1,delivery=? WHERE id=?',
                       (decision,result['decidedAt'],'waiting' if decision=='confirmed' else 'not_applicable',identifier))
            db.execute('INSERT INTO actions VALUES(?,?,?,?,?,?)',(request_id,identifier,decision,actor,self.clock(),json.dumps(result)))
            return result

    def changes(self, source, after=0):
        if not isinstance(source,str) or not 1<=len(source)<=256 or type(after) is not int or after<0:
            raise ValueError('invalid_change_cursor')
        with self.db() as db:
            rows=db.execute('''SELECT a.rowid AS cursor,a.* FROM actions a JOIN records r ON r.id=a.record_id
                               WHERE r.source=? AND a.rowid>? ORDER BY a.rowid LIMIT 100''',(source,after)).fetchall()
        return {'items':[{'cursor':r['cursor'],'actionId':r['id'],'kind':r['kind'],'actor':r['actor'],
                         'createdAt':r['created'],'data':json.loads(r['payload'])} for r in rows],
                'nextCursor':rows[-1]['cursor'] if rows else after}

    def backup(self):
        folder = self.root/'db-backups'
        folder.mkdir(exist_ok=True)
        target = folder/(time.strftime('%Y%m%d-%H%M%S',time.gmtime(self.clock()))+'.db')
        with closing(sqlite3.connect(self.root/'links.db')) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
        for old in sorted(folder.glob('*.db'))[:-7]:
            old.unlink()
        return {'file':target.name,'bytes':target.stat().st_size}
