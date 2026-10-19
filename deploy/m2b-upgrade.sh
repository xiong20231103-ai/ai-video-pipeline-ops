#!/bin/bash
# Upgrade an active cloud release only; no home deployment or firewall/Serve edits.
set -euo pipefail
test "$(id -u)" = 0
ARCHIVE=${1:?code archive required}
EXPECTED_SHA=${2:?sha256 required}
RELEASE=${3:?git commit required}
[[ "$RELEASE" =~ ^[a-f0-9]{40}$ ]]
OLD_RELEASE=$(readlink -f /opt/ops-console/current)
[[ "$OLD_RELEASE" =~ ^/opt/ops-console/releases/[a-f0-9]{40}$ ]]
test "$OLD_RELEASE" != "/opt/ops-console/releases/$RELEASE"
test ! -e "/opt/ops-console/releases/$RELEASE"
printf '%s  %s\n' "$EXPECTED_SHA" "$ARCHIVE" | sha256sum -c -
BACKUP="/root/ops-console-backup-m2b-$(date -u +%Y%m%dT%H%M%SZ)-${RELEASE:0:12}"
test ! -e "$BACKUP"
umask 077
install -d -m 700 "$BACKUP"
printf '%s\n' "$OLD_RELEASE" > "$BACKUP/previous-release.txt"
cp -p /etc/ops-console/config.json "$BACKUP/config.before.json"
if test -e /etc/ops-console/notifications.json; then
    test ! -L /etc/ops-console/notifications.json
    cp -p /etc/ops-console/notifications.json "$BACKUP/notifications.before.json"
fi
cp -p /etc/systemd/system/ops-console.service "$BACKUP/ops-console.service.before"
tailscale serve status --json > "$BACKUP/serve.before.json"
ufw status verbose > "$BACKUP/ufw.before.txt"
iptables-save > "$BACKUP/iptables.rules"
ip6tables-save > "$BACKUP/ip6tables.rules"
SNAPSHOT=$(sudo -u ops-console mktemp --suffix=.sqlite /var/lib/ops-console/.m2a-before.XXXXXXXX)
[[ "$SNAPSHOT" =~ ^/var/lib/ops-console/\.m2a-before\.[A-Za-z0-9]+\.sqlite$ ]]
sudo -u ops-console python3 -B - "$SNAPSHOT" <<'PY'
import sqlite3,sys
with sqlite3.connect('file:/var/lib/ops-console/console.db?mode=ro',uri=True) as source:
    with sqlite3.connect(sys.argv[1]) as destination:source.backup(destination)
PY
mv -- "$SNAPSHOT" "$BACKUP/state.before.sqlite"
chown root:root "$BACKUP/state.before.sqlite"

cat > "$BACKUP/rollback.sh" <<'ROLLBACK'
#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
BACKUP=$(cd -- "$(dirname -- "$0")" && pwd)
OLD_RELEASE=$(cat "$BACKUP/previous-release.txt")
[[ "$OLD_RELEASE" =~ ^/opt/ops-console/releases/[a-f0-9]{40}$ ]]
test -d "$OLD_RELEASE"
CURRENT=$(readlink -f /opt/ops-console/current)
if test -f "$CURRENT/cloud/command_admin.py"; then
    # Must drain BEFORE returning to a reader-only release. Unknown results need
    # human home reconciliation and intentionally prevent this rollback.
    sudo -u ops-console env PYTHONPATH="$CURRENT" "$CURRENT/.venv/bin/python" -B -m cloud.command_admin pause --cancel-queued --wait 60
fi
# Preserve private inputs, but disable notifications before returning to code
# without the worker. Never roll back or replay notification/command ledgers.
if test -f /etc/ops-console/notifications.json; then
    test ! -L /etc/ops-console/notifications.json
    cp -p /etc/ops-console/notifications.json "$BACKUP/notifications.at-rollback.$(date -u +%Y%m%dT%H%M%SZ).json"
    python3 -B - <<'PRIVATE_NOTIFICATION_ROLLBACK'
import json,os,uuid
from pathlib import Path
path=Path('/etc/ops-console/notifications.json');value=json.loads(path.read_text());value['enabled']=False
temporary=path.with_name('.notifications-rollback-'+uuid.uuid4().hex)
with temporary.open('x',encoding='utf-8') as stream:
    os.fchmod(stream.fileno(),0o640);os.fchown(stream.fileno(),path.stat().st_uid,path.stat().st_gid)
    json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
os.replace(temporary,path)
PRIVATE_NOTIFICATION_ROLLBACK
fi
cp -p "$BACKUP/config.before.json" /etc/ops-console/config.json
test ! -e /opt/ops-console/current.rollback-next
ln -s "$OLD_RELEASE" /opt/ops-console/current.rollback-next
mv -Tf /opt/ops-console/current.rollback-next /opt/ops-console/current
systemctl restart ops-console.service
curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/ready
diff -u "$BACKUP/ufw.before.txt" <(ufw status verbose)
diff -u "$BACKUP/serve.before.json" <(tailscale serve status --json)
echo 'Cloud code rolled back; additive schema/data retained; no home, firewall or Serve changes.'
ROLLBACK
chmod 700 "$BACKUP/rollback.sh"
bash -n "$BACKUP/rollback.sh"
SWITCHED=0
trap 'status=$?; if (( status != 0 && SWITCHED == 1 )); then "$BACKUP/rollback.sh"; fi; exit "$status"' EXIT
# Backup and rollback are ready before even changing the queue gate.
sudo -u ops-console env PYTHONPATH="$OLD_RELEASE" "$OLD_RELEASE/.venv/bin/python" -B -m cloud.command_admin pause --wait 60
install -d -m 755 "/opt/ops-console/releases/$RELEASE"
python3 -B - "$ARCHIVE" "/opt/ops-console/releases/$RELEASE" "$RELEASE" <<'PY'
import hashlib,json,sys,tarfile
from pathlib import Path
root=Path(sys.argv[2])
with tarfile.open(sys.argv[1],'r:gz') as archive:
    for item in archive.getmembers():
        assert item.isfile() and not item.name.startswith('/') and '..' not in item.name.split('/')
        assert item.name.split('/')[0] in {'cloud','contracts','static','deploy'}
    archive.extractall(root,filter='data')
manifest=json.loads((root/'cloud/deployment-manifest.json').read_text())
assert manifest['commit']==sys.argv[3]
for name,expected in manifest['sha256'].items(): assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
print('New release manifest verified:',manifest['commit'])
PY
python3 -m venv "/opt/ops-console/releases/$RELEASE/.venv"
"/opt/ops-console/releases/$RELEASE/.venv/bin/python" -m pip --isolated install --disable-pip-version-check --index-url https://pypi.org/simple --timeout 20 --retries 2 -r "/opt/ops-console/releases/$RELEASE/cloud/requirements.txt"
chmod -R a+rX,go-w "/opt/ops-console/releases/$RELEASE"
# Validate Linux rename/fsync behavior using synthetic temporary data before
# touching the active service. No production recipient/private key is involved.
python3 -B "/opt/ops-console/releases/$RELEASE/deploy/m1b-vault-smoke.py"
python3 -B "/opt/ops-console/releases/$RELEASE/deploy/m2a-queue-smoke.py"
python3 -B "/opt/ops-console/releases/$RELEASE/deploy/m2b-notification-smoke.py"
PYTHONPATH="/opt/ops-console/releases/$RELEASE" "/opt/ops-console/releases/$RELEASE/.venv/bin/python" -B -c 'from cloud.app import create_app; from cloud.backup_runtime import CloudBackupWorker; from cloud.notification_runtime import NotificationWorker'
# Snapshot was taken above, before any config or active-release change.
SWITCHED=1
python3 -B - <<'CONFIG'
import json,os
from pathlib import Path
path=Path('/etc/ops-console/config.json');value=json.loads(path.read_text())
value.update(command_queue_enabled=True,h3_target_contract=True)
temporary=path.with_name('config.m2a-next.json')
assert not temporary.exists()
with temporary.open('x',encoding='utf-8') as handle:
    os.fchmod(handle.fileno(),0o640);os.fchown(handle.fileno(),path.stat().st_uid,path.stat().st_gid)
    json.dump(value,handle);handle.flush();os.fsync(handle.fileno())
os.replace(temporary,path)
print('M2b queue flag and deployed H3 contract set; no configuration secrets printed.')
CONFIG

test ! -e /opt/ops-console/current.upgrade-next
ln -s "/opt/ops-console/releases/$RELEASE" /opt/ops-console/current.upgrade-next
mv -Tf /opt/ops-console/current.upgrade-next /opt/ops-console/current
SWITCHED=1
systemctl restart ops-console.service
curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/ready
diff -u "$BACKUP/ufw.before.txt" <(ufw status verbose)
diff -u "$BACKUP/serve.before.json" <(tailscale serve status --json)
echo "Backup: $BACKUP"
echo "Rollback: sudo $BACKUP/rollback.sh"
sudo -u ops-console env PYTHONPATH="/opt/ops-console/releases/$RELEASE" "/opt/ops-console/releases/$RELEASE/.venv/bin/python" -B -m cloud.command_admin status
echo 'Cloud M2b update active. Notifications remain disabled until private setup, isolated phone acceptance and legacy sender shutdown. No home, firewall or Serve changes.'
