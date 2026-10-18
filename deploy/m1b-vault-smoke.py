"""Linux pre-activation vault smoke: temporary synthetic data, no production I/O."""
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import uuid
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud.backups import BackupVault,FORMAT

with TemporaryDirectory(prefix='ops-m1b-vault-smoke-') as folder:
    vault=BackupVault(Path(folder)/'vault');now=datetime.now(timezone.utc).isoformat()
    # Shape fixture tests filesystem/SQL durability, not cryptographic strength.
    content=b'\x30\x80'+bytes.fromhex('060b2a864886f70d0109100117')+b'synthetic-only'
    data={'schema':1,'packageId':'20261018T000000Z-'+uuid.uuid4().hex,'format':FORMAT,'privateKeyIncluded':False,'sourceBytes':1,'startedAt':now,'completedAt':now,
          'artifacts':[{'name':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'files':1} for name in ('ledger.cms','configuration.cms')]}
    vault.reserve(data)
    for part in data['artifacts']:
        upload=vault.begin_part(data['packageId'],part['name'],len(content));upload['handle'].write(content)
        vault.finish_part(data['packageId'],part['name'],upload,len(content),part['sha256'])
    assert vault.publish(data['packageId'])['published'] and vault.verify(data['packageId'])['verified']
    original=vault.directory(data['packageId']);trash=vault.root/('.deleting-'+data['packageId']);original.rename(trash)
    reopened=BackupVault(vault.root);assert reopened.verify(data['packageId'])['verified']
    print('PASS: synthetic Linux fsync/publication/checksum/crash-rename recovery; production/key access=0')
