"""Read-only request counters. Does not open private configuration or start the agent."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import time

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--since',type=float,default=0)
    parser.add_argument('--until',type=float,default=None)
    args=parser.parse_args()
    path=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'OpsAgent' / 'agent.db'
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    rows=db.execute('SELECT mode,target,port,reason,SUM(count) AS requests,SUM(failures) AS failures,SUM(seconds) AS elapsedSeconds FROM request_stats WHERE minute>=? AND minute<? GROUP BY mode,target,port,reason ORDER BY mode,target,port,reason',(int(args.since//60),int((args.until or time.time())//60)+1)).fetchall()
    print(json.dumps({'minuteBuckets':True,'rows':[dict(row) for row in rows]},indent=2))
    db.close()

if __name__=='__main__': main()
