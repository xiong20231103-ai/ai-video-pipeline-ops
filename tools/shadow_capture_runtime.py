"""Bounded capture/publish seam. Replay is deliberately never run in the host.

Call once from the observer host with already-supplied observation/process probes.
The published manifest is consumed later by the offline CLI in another process.
"""
from pathlib import Path
import copy,os,tempfile,threading,time
from agent.core.snapshot import canonical,no_links
from tools.shadow_capture import aligned_capture,CaptureError,validate_plan,DigestCache
from tools.shadow_store import put_snapshot,usage

MAX_APPROVED=2*1024*1024*1024
class CapturePublisher:
    def __init__(self,plan,source,evidence_root,observer,process_probe,*,approved_total_bytes,
                 retained_roots=(),max_capture_bytes=32*1024*1024,min_interval_seconds=60,volatile_http=(),clock=time.monotonic):
        if type(approved_total_bytes) is not int or not 1<=approved_total_bytes<=MAX_APPROVED:raise CaptureError('approved_capacity_required')
        if type(max_capture_bytes) is not int or max_capture_bytes<1 or min_interval_seconds<30:raise CaptureError('capture_limits_invalid')
        self.root=no_links(evidence_root);self.source=no_links(source);self.retained=tuple(map(no_links,retained_roots))
        self.plan=copy.deepcopy(plan);self.observer=observer;self.process_probe=process_probe;self.cap=approved_total_bytes
        self.max_bytes=max_capture_bytes;self.interval=min_interval_seconds;self.clock=clock;self.last=None;self.lock=threading.Lock()
        self.digest_cache=DigestCache();self.volatile_http=tuple(volatile_http)
        for other in [self.source.parent,*self.retained]:
            if self.root==other or self.root.is_relative_to(other) or other.is_relative_to(self.root):raise CaptureError('evidence_root_overlap')
        validate_plan(plan,self.root/'_validation_destination')
        self.state={'schema':1,'state':'dormant','published':0,'rejected':0,'captureAttempts':0,
                    'directoryChangeRejected':0,'businessRequests':0,'realShadowPassed':False,'switchAccepted':False}
    def status(self):
        attempts=self.state['captureAttempts']
        return {**self.state,'directoryChangeFailureRatio':self.state['directoryChangeRejected']/attempts if attempts else None}
    def tick(self):
        if not self.lock.acquire(blocking=False):return {**self.status(),'state':'busy'}
        try:
            now=self.clock()
            if self.last is not None and now-self.last<self.interval:return self.status()
            self.last=now
            self.state['captureAttempts']+=1
            # Check external completeness BEFORE creating a staging directory.
            self.observer.observation()
            self.root.mkdir(parents=True,exist_ok=True)
            # Exclusive across host instances too. A stale lock blocks, never auto-deleted.
            lock=self.root/'.capture-writer.lock'
            try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            except FileExistsError:raise CaptureError('capture_writer_busy') from None
            try:
                os.close(fd)
                # Reserve copies + normalized SQLite + store publication + bounded manifests.
                used=usage(self.root)+sum(usage(p) for p in self.retained)
                reserve=6*self.max_bytes+16*1024*1024
                if used+reserve>self.cap:raise CaptureError('capture_capacity_exhausted')
                with tempfile.TemporaryDirectory(prefix='.capture-stage-',dir=self.root) as folder:
                    snapshot=aligned_capture(self.plan,Path(folder)/'snapshot',source_path=self.source,
                        process_probe=self.process_probe,http_probe=self.observer.observation,
                        max_file_bytes=self.max_bytes,max_total_bytes=self.max_bytes,max_hash_bytes=64*1024*1024,digest_cache=self.digest_cache,volatile_http=self.volatile_http)
                    stored=put_snapshot(snapshot,self.root/'store',approved_total_bytes=self.cap,
                        retained_roots=(*self.retained,Path(folder)))
                    # Atomic append-only handoff: no live paths or response values in report queue.
                    value={'schema':1,'sourceIdentity':stored['sourceIdentity'],'capturedAt':snapshot.manifest['frozenAt'],
                        'emitterPid':os.getpid(),'realShadowPassed':False,'switchAccepted':False}
                    raw=canonical(value);destination=self.root/'ready';destination.mkdir(exist_ok=True)
                    with (destination/(stored['sourceIdentity']+'.json')).open('xb') as out:out.write(raw)
                self.state.update(state='captured',published=self.state['published']+1,lastSourceIdentity=stored['sourceIdentity'])
            finally:lock.unlink(missing_ok=True)
        except Exception as error:
            # Exception values can contain live paths/credentials: return a fixed code only.
            code=str(error) if isinstance(error,CaptureError) and str(error) in {
                'observed_external_ports_incomplete','capture_capacity_exhausted','capture_writer_busy',
                'state_changed_in_window','state_content_changed_in_window','external_or_process_changed',
                'directory_changed_in_window','database_changed_in_window','capture_window_exceeded'} else 'capture_rejected'
            self.state.update(state='blocked',lastCode=code,rejected=self.state['rejected']+1)
            if code=='directory_changed_in_window':self.state['directoryChangeRejected']+=1
        finally:self.lock.release()
        return self.status()
    def loop(self,stop):
        # Dedicated host thread; no exception escapes into heartbeat/write supervision.
        while not stop.is_set():
            self.tick()
            stop.wait(self.interval)
