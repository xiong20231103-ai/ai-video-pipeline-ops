"""One durable write channel. Persist sent before the first and only home POST."""
from contextlib import closing,contextmanager
import base64,http.client,json,os,sqlite3,threading,time,urllib.error,urllib.parse,urllib.request,uuid
from pathlib import Path
from contracts.commands import command,canonical,MAX_REPLY
from contracts.state_files import read_json,atomic_json

class ExecutionLedger:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS execution_meta(id INTEGER PRIMARY KEY CHECK(id=1),ledger_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS executions(id TEXT PRIMARY KEY,digest TEXT NOT NULL,state TEXT NOT NULL,job TEXT,result TEXT,result_digest TEXT,http_status INTEGER,updated REAL NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO execution_meta VALUES(1,?)',(uuid.uuid4().hex,))
            self.identity=db.execute('SELECT ledger_id FROM execution_meta WHERE id=1').fetchone()[0]
            for row in db.execute("SELECT id FROM executions WHERE state='sent'").fetchall():
                self._result(db,row['id'],{'kind':'unknown','reason':'restart_after_send'})
    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            try:yield db;db.commit()
            except BaseException:db.rollback();raise
    def receive(self,job):
        spec=command(job['target'],job['body'])
        if job.get('ledgerId')!=self.identity or job.get('source')!=spec['source']:raise ValueError('Command identity mismatch')
        if job.get('digest')!=spec['digest']:raise ValueError('Command content conflict')
        with self.db() as db:
            old=db.execute('SELECT * FROM executions WHERE id=?',(job['id'],)).fetchone()
            if old:
                if old['digest']!=spec['digest']:raise ValueError('Command content conflict')
                db.execute('UPDATE executions SET job=? WHERE id=?',(canonical(job),job['id']))
                return old['state']
            db.execute('INSERT INTO executions VALUES(?,?,?,?,?,?,?,?)',(job['id'],spec['digest'],'received',canonical(job),None,None,None,time.time()))
            return 'received'
    def sent(self,identifier):
        with self.db() as db:
            if db.execute("UPDATE executions SET state='sent',updated=? WHERE id=? AND state='received'",(time.time(),identifier)).rowcount!=1:raise ValueError('Command cannot be sent twice')
    def _result(self,db,identifier,result):
        encoded=canonical(result);digest=__import__('hashlib').sha256(encoded.encode()).hexdigest()
        db.execute('UPDATE executions SET state=?,result=?,result_digest=?,http_status=?,updated=? WHERE id=?',
            ('unknown' if result['kind']=='unknown' else 'result',encoded,digest,result.get('httpStatus'),time.time(),identifier))
    def result(self,identifier,result):
        with self.db() as db:self._result(db,identifier,result)
    def pending(self):
        with self.db() as db:row=db.execute('SELECT * FROM executions WHERE result IS NOT NULL ORDER BY updated,id LIMIT 1').fetchone()
        return dict(row) if row else None
    def acknowledge(self,identifier):
        # Retain a minimal never-resend receipt; bodies/results are cloud-owned
        # after acknowledgement. Never mistake a lost result for an unsent job.
        with self.db() as db:db.execute("UPDATE executions SET state='acknowledged',job=NULL,result=NULL,updated=? WHERE id=?",(time.time(),identifier))

class ExecutionWorker:
    def __init__(self,agent):self.agent=agent;self.state=agent.state_dir;self._ledger=None;self.lock=threading.Lock();self.clock=time.time;self.active=threading.Event();self.home_busy=threading.Event();self.retry_after=0.0;self.rejection_path=self.state/'execution-rejections.jsonl'
    def enabled(self):
        path=self.state/'command-settings.json'
        if not path.exists():return False
        try:
            settings=read_json(path)
            return isinstance(settings,dict) and settings=={'schema':1,'enabled':True}
        except (OSError,ValueError):return False
    @property
    def ledger(self):
        with self.lock:
            if self._ledger is None:self._ledger=ExecutionLedger(self.state/'execution.db')
            return self._ledger
    def capability(self):return {'enabled':True,'protocol':1,'ledgerId':self.ledger.identity} if self.enabled() else {'enabled':False}
    def report(self,phase):atomic_json(self.state/'execution-runtime.json',{'schema':1,'phase':phase,'observedAt':time.time()})
    def stopped(self):return self.agent.stop.is_set() or bool(self.agent.lifecycle.stop_request())
    def home_post(self,job):
        spec=command(job['target'],job['body']);port=8766 if spec['source']=='receiver' else 8765
        # Receiver permits tokenless writes only from loopback (existing contract).
        host='127.0.0.1' if spec['source']=='receiver' else '100.92.17.9'
        request=urllib.request.Request('http://'+host+':'+str(port)+spec['target'],data=canonical(spec['body']).encode(),
            headers={'Content-Type':'application/json'},method='POST')
        try:response=self.agent.transport.open(request,timeout=spec['timeoutSeconds'])
        except urllib.error.HTTPError as error:response=error
        with response:
            lengths=response.headers.get_all('Content-Length',[])
            if len(lengths)>1 or lengths and (len(lengths[0])>10 or not lengths[0].isdigit()):raise http.client.HTTPException('Invalid reply length')
            expected=int(lengths[0]) if lengths else None
            if expected is not None and expected>MAX_REPLY:raise OSError('Home reply exceeded bound; result uncertain')
            raw=response.read(MAX_REPLY+1)
            if len(raw)>MAX_REPLY or expected is not None and len(raw)!=expected:raise OSError('Home reply incomplete or exceeded bound; result uncertain')
            return {'kind':'http','httpStatus':response.code,'contentType':response.headers.get('Content-Type','application/json'),
                    'bodyBase64':base64.b64encode(raw).decode('ascii')}
    def process(self,job):
        self.active.set()
        try:
            try:self._process(job)
            except ValueError as error:
                # A malformed or conflicting lease must never reach the home
                # POST. Keep the worker alive and give the cloud a terminal
                # not_sent receipt when the identity is usable.
                self._reject(job,error)
        finally:self.active.clear()

    def _reject(self,job,error):
        message=str(error)
        reason='agent_rejected_identity' if 'identity mismatch' in message.lower() else 'agent_rejected_contract'
        identifier=job.get('id') if isinstance(job,dict) else None
        self.rejection_path.parent.mkdir(parents=True,exist_ok=True)
        with self.rejection_path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'id':identifier if isinstance(identifier,str) else None,'reason':reason,'observedAt':self.clock()},separators=(',',':'))+'\n')
        if not isinstance(identifier,str) or not isinstance(job.get('lease'),str):
            self.retry_after=self.clock()+30;return
        try:
            answer=self.agent.cloud('/agent/results',{'id':identifier,'lease':job['lease'],'ledgerId':self.ledger.identity,'result':{'kind':'not_sent','reason':reason}})
            if answer.get('recorded') is not True:self.retry_after=self.clock()+30
        except (OSError,ValueError,http.client.HTTPException,urllib.error.HTTPError):
            self.retry_after=self.clock()+30
    def _process(self,job):
        state=self.ledger.receive(job)
        if state!='received':
            if state=='acknowledged':
                # Cloud rollback lost its response, but the local receipt proves
                # this is not a fresh command. Do not repeat the home request.
                self.ledger.result(job['id'],{'kind':'unknown','reason':'local_result_unavailable'})
            return
        if self.stopped() or not self.enabled():return
        if type(job.get('expiresAt')) not in (int,float) or job['expiresAt']<=self.clock():
            self.ledger.result(job['id'],{'kind':'not_sent','reason':'invalid_or_expired'});return
        self.ledger.sent(job['id']);self.report('sending')
        try:permit=self.agent.cloud('/agent/commands/'+job['id']+'/start',{'lease':job['lease'],'ledgerId':self.ledger.identity})
        except urllib.error.HTTPError:
            self.ledger.result(job['id'],{'kind':'not_sent','reason':'send_permit_denied'});return
        except (OSError,ValueError,http.client.HTTPException):
            self.ledger.result(job['id'],{'kind':'unknown','reason':'transport_uncertain'});return
        if permit.get('sendPermitted') is not True or self.stopped() or not self.enabled():
            self.ledger.result(job['id'],{'kind':'not_sent','reason':'send_permit_denied'});return
        if job['expiresAt']<=self.clock():
            self.ledger.result(job['id'],{'kind':'not_sent','reason':'invalid_or_expired'});return
        if job['target']=='/api/controls/cloud-cleanup/execute' and not self.clock()<job['body']['expiresAt']:
            self.ledger.result(job['id'],{'kind':'not_sent','reason':'invalid_or_expired'});return
        self.home_busy.set()
        try:result=self.home_post(job)
        except (OSError,http.client.HTTPException):result={'kind':'unknown','reason':'transport_uncertain'}
        finally:self.home_busy.clear()
        self.ledger.result(job['id'],result)
    def flush(self):
        row=self.ledger.pending()
        if not row:return False
        self.report('unknown' if row['state']=='unknown' else 'awaiting_ack')
        job=json.loads(row['job']);answer=self.agent.cloud('/agent/results',{'id':row['id'],'lease':job['lease'],'ledgerId':self.ledger.identity,'result':json.loads(row['result'])})
        if answer.get('recorded') is not True:raise ValueError('Result acknowledgement missing')
        self.ledger.acknowledge(row['id']);self.report('idle');return True
    def loop(self):
        while not self.agent.stop.is_set():
            if not self.enabled():self.agent.stop.wait(1);continue
            delay=self.retry_after-self.clock()
            if delay>0:self.agent.stop.wait(delay);continue
            try:
                if self.flush():continue
                if self.stopped():return
                self.report('idle')
                answer=self.agent.cloud('/agent/commands?wait=25&ledgerId='+self.ledger.identity)
                if answer.get('item'):self.process(answer['item'])
            except (OSError,json.JSONDecodeError,http.client.HTTPException):self.agent.stop.wait(2)
            except ValueError:
                # Includes result acknowledgement loss. The durable result
                # remains in execution.db and is retried after a bounded
                # backoff; no home request is repeated.
                self.retry_after=self.clock()+30
                self.agent.stop.wait(30)


def configure_execution(state,enabled):
    """Local nonsecret switch. Never opens/mutates the execution ledger."""
    state=Path(state)
    if type(enabled) is not bool:raise ValueError('Invalid execution switch')
    if enabled and not (state/'config.json').is_file():raise ValueError('Configure the existing private agent first')
    if any((state/name).exists() for name in ('maintenance.json','stop-request.json')):raise ValueError('Agent maintenance is active')
    runtime=state/'execution-runtime.json'
    if runtime.exists() and read_json(runtime).get('phase') in {'sending','awaiting_ack','unknown'}:raise ValueError('Pause cloud and reconcile/drain commands before changing the execution switch')
    atomic_json(state/'command-settings.json',{'schema':1,'enabled':enabled})
    return {'enabled':enabled,'ledgerOpened':False,'credentialsRead':False}

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('status','enable','disable'));args=parser.parse_args()
    state=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'OpsAgent'
    if args.action!='status':print(json.dumps(configure_execution(state,args.action=='enable')));return
    runtime=read_json(state/'execution-runtime.json') if (state/'execution-runtime.json').exists() else {}
    settings=read_json(state/'command-settings.json') if (state/'command-settings.json').exists() else {}
    print(json.dumps({'enabled':settings=={'schema':1,'enabled':True},'lastReportedPhase':runtime.get('phase'),'reportedAt':runtime.get('observedAt'),'executionDbExists':(state/'execution.db').exists(),'credentialsRead':False}))
if __name__=='__main__':main()
