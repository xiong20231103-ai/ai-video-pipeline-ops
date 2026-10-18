"""User-run hidden recovery-key setup, never reads the agent bearer token."""
from getpass import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from agent.backup_crypto import CryptoError,create_recipient
from agent.backup_policy import default_roots

DEFAULT_OPENSSL=Path(r'C:\Program Files\Git\usr\bin\openssl.exe')

def private_directory(path):
    path.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        result=subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',
            os.getlogin()+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode: raise CryptoError('Cannot secure recovery directory; no key was created')
    else: path.chmod(0o700)

def main():
    if not sys.stdin.isatty(): raise SystemExit('Run interactively; hidden passphrase input is required')
    if not DEFAULT_OPENSSL.is_file(): raise SystemExit('Existing OpenSSL missing; no installation attempted')
    base=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))
    state=base/'OpsAgent'; recovery=base/'OpsAgentRecovery'
    destination=state/'backup-settings.json'
    if destination.exists() or (recovery/'v1').exists(): raise SystemExit('Existing recovery setup retained; no overwrite performed')
    password=getpass('New backup recovery passphrase (at least 16 characters, hidden): ')
    confirmation=getpass('Repeat the backup recovery passphrase (hidden): ')
    if password!=confirmation: raise SystemExit('Passphrases differ; nothing created')
    if len(password)<16: raise SystemExit('Passphrase too short; nothing created')
    private_directory(state);private_directory(recovery)
    certificate,key=create_recipient(DEFAULT_OPENSSL,recovery/'v1',password)
    public=state/'backup-recipient.pem'
    if public.exists(): raise SystemExit('Existing recipient retained; recovery folder requires manual review')
    shutil.copyfile(certificate,public)
    settings={'schema':1,'openssl':str(DEFAULT_OPENSSL),'recipientCertificate':str(public),'roots':default_roots(state)}
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as handle:
        json.dump(settings,handle);handle.flush();os.fsync(handle.fileno())
    print('Public recipient configured; no service was started and no cloud request was made.')
    print('Keep an offline copy of this private recovery directory:',str(recovery/'v1'))
    print('Keep its passphrase separately. The private key must remain outside the cloud.')

if __name__=='__main__':
    try: main()
    except CryptoError: raise SystemExit('Recovery setup failed privately; no credentials were logged') from None
