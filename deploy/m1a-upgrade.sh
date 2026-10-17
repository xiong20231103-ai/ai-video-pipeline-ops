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
BACKUP="/root/ops-console-backup-m1a-review-$(date -u +%Y%m%dT%H%M%SZ)-${RELEASE:0:12}"
test ! -e "$BACKUP"
umask 077
install -d -m 700 "$BACKUP"
printf '%s\n' "$OLD_RELEASE" > "$BACKUP/previous-release.txt"
cp -p /etc/systemd/system/ops-console.service "$BACKUP/ops-console.service.before"
tailscale serve status --json > "$BACKUP/serve.before.json"
ufw status verbose > "$BACKUP/ufw.before.txt"
iptables-save > "$BACKUP/iptables.rules"
ip6tables-save > "$BACKUP/ip6tables.rules"
python3 -B - "$BACKUP/state.before.sqlite" <<'PY'
import sqlite3,sys
with sqlite3.connect('file:/var/lib/ops-console/console.db?mode=ro',uri=True) as source:
    with sqlite3.connect(sys.argv[1]) as destination: source.backup(destination)
PY
cat > "$BACKUP/rollback.sh" <<'ROLLBACK'
#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
BACKUP=$(cd -- "$(dirname -- "$0")" && pwd)
OLD_RELEASE=$(cat "$BACKUP/previous-release.txt")
[[ "$OLD_RELEASE" =~ ^/opt/ops-console/releases/[a-f0-9]{40}$ ]]
test -d "$OLD_RELEASE"
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
echo 'Cloud review update active. No home, firewall or Serve changes.'
