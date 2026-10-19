"""Pause/drain gate for cloud deploys; no home call and no credentials printed."""
import argparse,json,os,time
from pathlib import Path
from cloud.store import Store
from cloud.commands import CommandQueue,CommandError

def status(queue):
 with queue.store.db(True) as db:
  queue.expire(db)
  counts=dict(db.execute('SELECT state,count(*) FROM commands GROUP BY state'))
 return {**queue.health(),'counts':counts,'drained':not any(counts.get(state,0) for state in ('leased','sent','unknown'))}
def pause(queue,cancel_queued=False):
 queue.set_paused(True)
 if cancel_queued:
  with queue.store.db(True) as db:
   for row in db.execute("SELECT id,actor FROM commands WHERE state='queued'").fetchall():
    db.execute("UPDATE commands SET state='cancelled',updated=? WHERE id=?",(queue.store.clock(),row['id']));queue.audit(db,row,'cancelled_for_cloud_rollback','operator:local-admin')
 return status(queue)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=('status','pause','resume'));parser.add_argument('--cancel-queued',action='store_true');parser.add_argument('--wait',type=int,default=0);parser.add_argument('--empty-only',action='store_true')
 args=parser.parse_args()
 if not 0<=args.wait<=120:parser.error('wait must be 0..120')
 config=json.loads(Path(os.environ.get('OPS_CONSOLE_CONFIG','/etc/ops-console/config.json')).read_text())
 queue=CommandQueue(Store(Path(config.get('state_dir','/var/lib/ops-console'))/'console.db'),config.get('command_queue_enabled') is True,config.get('h3_target_contract') is True)
 if args.action=='pause':answer=pause(queue,args.cancel_queued)
 elif args.action=='resume':
  try:queue.resume(empty_only=args.empty_only)
  except CommandError as error:print(json.dumps({'resumeRefused':error.code,**status(queue)}));return 2
  answer=status(queue)
 else:answer=status(queue)
 deadline=time.monotonic()+args.wait
 while args.action=='pause' and not answer['drained'] and time.monotonic()<deadline:
  time.sleep(.25);answer=status(queue)
 print(json.dumps(answer,sort_keys=True));return 0 if args.action!='pause' or answer['drained'] else 2
if __name__=='__main__':raise SystemExit(main())
