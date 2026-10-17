"""Viewer-relative leases and deterministic read scheduling; no production I/O."""
from datetime import timedelta
import math
import threading
import time

OTHER_READS=('/api/task-boxes/current','/api/controls/tasks','/api/controls/templates','/api/control-commands/current','/api/controls/continue-current/status','/api/safety','/api/project-gaps','/api/subtitle-verification/current')

def periods(active,day):
    result={'/api/dashboard/summary':5 if active else 60,'/api/health':30 if active else 60,'/api/dashboard':60 if active else 600}
    result.update({target:60 for target in OTHER_READS})
    if active:
        for offset in range(14):
            date=day-timedelta(days=offset); label=str(date.month)+'.'+str(date.day)
            for prefix in ('/api/pipeline','/api/task-boxes/history','/api/dashboard'):
                result[prefix+'?date='+label]=600
    return result

class PollSchedule:
    def __init__(self,clock=time.monotonic):
        self.clock=clock; self.lock=threading.Lock(); self.until=0; self.last={}; self.first={}
    def update_viewer(self,response):
        seconds=response.get('viewerLeaseSeconds',0)
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<=seconds<=120 or response.get('viewerActive') is not True: seconds=0
        with self.lock: self.until=self.clock()+seconds
    def active(self):
        with self.lock: return self.clock()<self.until
    def completed(self,target,when=None):
        with self.lock: self.last[target]=self.clock() if when is None else when
    def recent(self,target,seconds=2):
        with self.lock: return target in self.last and 0<=self.clock()-self.last[target]<seconds
    def next(self,day):
        with self.lock:
            now=self.clock(); current=periods(now<self.until,day)
            # Idle history has no periodic entries; expired leases cannot drain a stale backlog.
            self.first={key:value for key,value in self.first.items() if key in current}
            self.last={key:value for key,value in self.last.items() if key in current or '?date=' not in key}
            candidates=[]
            for priority,(target,period) in enumerate(current.items()):
                if target not in self.first: self.first[target]=now+max(0,(priority-11)//3)*3 if '?date=' in target else now
                due=self.last[target]+period if target in self.last else self.first[target]
                if due<=now: candidates.append((due,priority,target))
            return min(candidates)[2] if candidates else None
