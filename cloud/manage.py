"""Interactive credential entry; never prints secret values or accepts CLI secrets."""
import argparse
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
from cloud.app import HASHER
from cloud.store import Store

DEFAULT_ORIGIN='https://ops.tail830b6f.ts.net'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['configure','reset-password','delete-account'])
    args=parser.parse_args()
    config_path=Path(os.environ.get('OPS_CONSOLE_CONFIG','/etc/ops-console/config.json'))
    if args.command=='configure':
        if config_path.exists(): raise SystemExit('Configuration already exists; no overwrite performed')
        invite=getpass('Registration invitation (at least 12 characters, hidden): ')
        token=getpass('Home agent token (32-256 printable ASCII characters, hidden): ')
        if not 12<=len(invite)<=256 or not 32<=len(token)<=256 or not all(33<=ord(char)<=126 for char in token):
            raise SystemExit('Invalid length/format; nothing written')
        config={'origin':os.environ.get('OPS_CONSOLE_ORIGIN',DEFAULT_ORIGIN),
                'state_dir':'/var/lib/ops-console','max_accounts':2,'invite_hash':HASHER.hash(invite),
                'agent_token_sha256':hashlib.sha256(token.encode()).hexdigest()}
        config_path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(config_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as handle:
            json.dump(config,handle); handle.flush(); os.fsync(handle.fileno())
        if os.name=='posix' and os.getuid()==0:
            import pwd
            owner=pwd.getpwnam('ops-console'); os.chown(config_path,owner.pw_uid,owner.pw_gid)
        print('Configuration saved with owner-only permissions. No secret value was displayed.')
        return
    config=json.loads(config_path.read_text(encoding='utf-8'))
    store=Store(Path(config['state_dir'])/'console.db')
    name=input('Account name: ').strip()
    user=store.user(name)
    if not user: raise SystemExit('Account not found')
    if args.command=='delete-account':
        if input('Type DELETE to delete this account and revoke sessions: ')!='DELETE': raise SystemExit('Cancelled')
        store.delete_user(name)
    else:
        password=getpass('New password (at least 12 characters, hidden): ')
        if not 12<=len(password)<=256: raise SystemExit('Invalid password length')
        store.change_password(user['id'],HASHER.hash(password))
    print('Account updated; its previous sessions have been revoked.')

if __name__=='__main__': main()
