"""Linux release probe: only inert temp DB, no sockets or configuration reads."""
import base64,json,sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud.store import Store
from cloud.commands import CommandQueue
with TemporaryDirectory(prefix='m2a-queue-smoke-') as folder:
 store=Store(Path(folder)/'console.db');queue=CommandQueue(store,True,True);ledger='a'*32
 queue.advertise({'enabled':True,'protocol':1,'ledgerId':ledger});store.heartbeat('healthy')
 row=queue.enqueue('fixture','fixture-command-123456','/api/controls/upload/rescan',{});job=queue.claim(ledger);queue.permit(job['id'],job['lease'],ledger)
 result={'kind':'http','httpStatus':422,'contentType':'application/json','bodyBase64':base64.b64encode(b'{"detail":"fixture"}\n').decode()}
 queue.finish(job['id'],job['lease'],ledger,result);assert queue.get(row['cloudCommandId'])['result']==result
 assert queue.listing()['items'][0]['result'] is None
 queue.set_paused(True);assert not queue.ready()
 print(json.dumps({'m2aQueueSmoke':True,'productionWrites':False,'homeRequests':0,'rawHttpResultPreserved':True}))
