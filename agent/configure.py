"""User-only hidden credential entry. Configuration never starts the agent."""
from getpass import getpass
import json
import os
from pathlib import Path
import subprocess

DEFAULT_ORIGIN='https://ops.tail830b6f.ts.net'

def main():
    state=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'OpsAgent'
    path=state/'config.json'
    if path.exists(): raise SystemExit('Existing agent configuration retained; no overwrite performed')
    token=getpass('The same agent token entered on the cloud server (hidden): ')
    if not 32<=len(token)<=256 or not all(33<=ord(char)<=126 for char in token): raise SystemExit('Invalid token length/format; nothing written')
    origin=DEFAULT_ORIGIN
    state.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        # argv-only invocation; neither credential nor shell-expanded input is passed.
        subprocess.run(['icacls',str(state),'/inheritance:r','/grant:r',os.getlogin()+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],check=True,stdout=subprocess.DEVNULL)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as handle:
        json.dump({'cloud_origin':origin,'agent_token':token},handle); handle.flush(); os.fsync(handle.fileno())
    print('Agent configuration saved privately; no service was started.')

if __name__=='__main__': main()
