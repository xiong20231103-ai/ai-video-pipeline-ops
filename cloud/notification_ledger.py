"""Durable snapshot episodes and notification delivery, independent of home writes."""
import json,secrets
from cloud.notification_facts import digest

class NotificationLedger:
 def __init__(self,store):
  self.store=store
  with store.db(True) as db:
   db.executescript('''
    CREATE TABLE IF NOT EXISTS notification_meta(id INTEGER PRIMARY KEY CHECK(id=1),baseline REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_sources(scope TEXT PRIMARY KEY,version INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_episodes(base_key TEXT PRIMARY KEY,scope TEXT NOT NULL,active INTEGER NOT NULL,round INTEGER NOT NULL,first_seen REAL NOT NULL,last_seen REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_events(event_key TEXT PRIMARY KEY,base_key TEXT NOT NULL,round INTEGER NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,first_seen REAL NOT NULL,last_seen REAL NOT NULL,batch_id TEXT);
    CREATE TABLE IF NOT EXISTS notification_deliveries(id TEXT PRIMARY KEY,kind TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,receipt TEXT NOT NULL,error_code TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notification_buckets(kind TEXT PRIMARY KEY,last_sent REAL NOT NULL);
   ''')
   # A crashed/uncertain external send is never blindly repeated after restart.
   db.execute("UPDATE notification_deliveries SET state='unknown',updated=? WHERE state='sending'",(store.clock(),))
   db.execute("UPDATE notification_events SET state='unknown' WHERE batch_id IN (SELECT id FROM notification_deliveries WHERE state='unknown') AND state='sending'")
 def baseline(self):
  with self.store.db() as db:row=db.execute('SELECT baseline FROM notification_meta WHERE id=1').fetchone()
  return row[0] if row else None
 def initialize(self,observations):
  """Atomic first-enable baseline, not one baseline per process restart."""
  now=self.store.clock()
  with self.store.db(True) as db:
   if db.execute('SELECT 1 FROM notification_meta').fetchone():return False
   db.execute('INSERT INTO notification_meta VALUES(1,?)',(now,))
   for scope,version,items in observations:self._observe(db,scope,version,items,True)
  return True
 def _observe(self,db,scope,version,items,baseline,recovery_identity=None):
  old=db.execute('SELECT version FROM notification_sources WHERE scope=?',(scope,)).fetchone()
  if old and version<=old[0]:return
  now=self.store.clock();keys=set()
  for item in items:
   key=item['baseKey'];keys.add(key)
   row=db.execute('SELECT * FROM notification_episodes WHERE base_key=?',(key,)).fetchone()
   if row and (row['active'] or item.get('once')):
    db.execute('UPDATE notification_episodes SET last_seen=? WHERE base_key=?',(now,key))
    db.execute('UPDATE notification_events SET last_seen=? WHERE base_key=? AND round=?',(now,key,row['round']))
    continue
   episode=(row['round']+1) if row else 1;event=digest([key,episode])
   db.execute('INSERT OR REPLACE INTO notification_episodes VALUES(?,?,1,?,?,?)',(key,scope,episode,now,now))
   state='baseline' if baseline or item.get('historical') else 'pending'
   db.execute('INSERT INTO notification_events VALUES(?,?,?,?,?,?,?,?,NULL)',(event,key,episode,item['kind'],json.dumps(item,ensure_ascii=False),state,now,now))
  for row in db.execute('SELECT base_key FROM notification_episodes WHERE scope=? AND active=1',(scope,)).fetchall():
   if row[0] not in keys:
    episode=db.execute('SELECT round FROM notification_episodes WHERE base_key=?',(row[0],)).fetchone()[0]
    original=db.execute('SELECT * FROM notification_events WHERE base_key=? AND round=?',(row[0],episode)).fetchone()
    payload=json.loads(original['payload'])
    # A task switch, stale/missing data or changed error is not recovery.
    # Current-task recovery requires the same positively recovered identity.
    same_task=recovery_identity is not None and all((payload.get('identity') or {}).get(k)==recovery_identity.get(k) for k in ('batchId','canonicalTaskId'))
    recovery_allowed=(scope=='connectivity' and not items) or same_task
    if recovery_allowed and not baseline and not payload.get('once') and original['state']!='baseline':
     recovery_key=digest([row[0],episode,'recovered'])
     recovered={**payload,'kind':'recovered','severity':'normal','needsManualReview':False,'recoveredFrom':payload['kind'],'message':'已恢复：'+payload['code']+'；只报告已核对的状态变化。'}
     db.execute("INSERT OR IGNORE INTO notification_events VALUES(?,?,?,?,?,'pending',?,?,NULL)",(recovery_key,row[0],episode,'recovered',json.dumps(recovered,ensure_ascii=False),now,now))
    db.execute('UPDATE notification_episodes SET active=0,last_seen=? WHERE base_key=?',(now,row[0]))
  db.execute('INSERT OR REPLACE INTO notification_sources VALUES(?,?)',(scope,version))
 def observe(self,scope,version,items,recovery_identity=None):
  with self.store.db(True) as db:self._observe(db,scope,version,items,False,recovery_identity)
 def prepare(self,*,quiet=False):
  now=self.store.clock()
  with self.store.db(True) as db:
   pending=db.execute("SELECT * FROM notification_events WHERE state='pending' ORDER BY first_seen,event_key").fetchall()
   for first in pending:
    payload=json.loads(first['payload'])
    if quiet and payload.get('severity')!='critical':continue
    bucket=db.execute('SELECT last_sent FROM notification_buckets WHERE kind=?',(first['kind'],)).fetchone()
    if bucket and now-bucket[0]<600:continue
    # Five full event keys plus short sanitized explanations fit provider limits.
    selected=[r for r in pending if r['kind']==first['kind'] and (not quiet or json.loads(r['payload']).get('severity')=='critical')][:5]
    identifier=secrets.token_hex(16)
    db.execute("INSERT INTO notification_deliveries VALUES(?,?,'sending',?,?,'','')",(identifier,first['kind'],now,now))
    for row in selected:db.execute("UPDATE notification_events SET state='sending',batch_id=? WHERE event_key=?",(identifier,row['event_key']))
    return {'id':identifier,'kind':first['kind'],'events':[{'eventKey':r['event_key'],**json.loads(r['payload'])} for r in selected]}
  return None
 def finish(self,identifier,state,receipt='',error_code=''):
  if state not in {'sent','rejected','unknown'}:raise ValueError('Invalid delivery state')
  # Provider response metadata only: never raw HTTP body, exception or webhook.
  if len(receipt)>80 or len(error_code)>80:raise ValueError('Invalid provider metadata')
  now=self.store.clock()
  with self.store.db(True) as db:
   row=db.execute("SELECT kind FROM notification_deliveries WHERE id=? AND state='sending'",(identifier,)).fetchone()
   if not row:raise ValueError('Delivery is not in flight')
   db.execute('UPDATE notification_deliveries SET state=?,updated=?,receipt=?,error_code=? WHERE id=?',(state,now,receipt,error_code,identifier))
   db.execute('UPDATE notification_events SET state=? WHERE batch_id=?',(state,identifier))
   if state=='sent':db.execute('INSERT OR REPLACE INTO notification_buckets VALUES(?,?)',(row[0],now))
 def status(self):
  with self.store.db() as db:
   return {'events':dict(db.execute('SELECT state,count(*) FROM notification_events GROUP BY state')),'deliveries':dict(db.execute('SELECT state,count(*) FROM notification_deliveries GROUP BY state')),'baselineAt':self.baseline(),'semantics':'snapshot-best-effort; uncertain external sends are not automatically repeated'}
