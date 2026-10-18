#!/bin/bash
# Stage only. No Serve change and no M0 shutdown before private user configuration.
set -euo pipefail
test "$(id -u)" = 0
ARCHIVE=${1:?archive path required}
EXPECTED_SHA=${2:?archive checksum required}
RELEASE=${3:?release id required}
MODE=${4:-new}
[[ "$RELEASE" =~ ^[a-f0-9]{40}$ ]] || exit 2
BACKUP=/root/ops-console-backup-m1a-20261017
if [ "$MODE" = new ]; then test ! -e "$BACKUP"; else
  [[ "$MODE" = resume-before-install || "$MODE" = resume-unactivated-install ]]
  test -d "$BACKUP"
fi
if [ "$MODE" = resume-unactivated-install ]; then
  test -d /opt/ops-console/releases
  test ! -e /opt/ops-console/current
  test ! -e /etc/ops-console/config.json
  test -z "$(find /var/lib/ops-console -mindepth 1 -maxdepth 1 -print -quit)"
else
  test ! -e /opt/ops-console
  test ! -e /etc/ops-console
  test ! -e /var/lib/ops-console
fi
test ! -e /etc/systemd/system/ops-console.service
printf '%s  %s\n' "$EXPECTED_SHA" "$ARCHIVE" | sha256sum -c -
umask 077
if [ "$MODE" = new ]; then
install -d -m 700 "$BACKUP"
iptables-save > "$BACKUP/iptables.rules"
ip6tables-save > "$BACKUP/ip6tables.rules"
ufw status verbose > "$BACKUP/ufw.before.txt"
tailscale serve status --json > "$BACKUP/serve.before.json"
systemctl is-enabled ops-m0-forward.service > "$BACKUP/forward-enabled.before.txt"
cp -a /etc/systemd/system/ops-m0-forward.service "$BACKUP/ops-m0-forward.service.before"
python3 - "$BACKUP/serve.before.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]))
assert not s.get('AllowFunnel')
assert set(s.get('TCP',{}))=={'443'}
assert len(s.get('Web',{}))==1
web=next(iter(s['Web'].values()))
assert web=={'Handlers':{'/':{'Proxy':'http://127.0.0.1:8765'}}}
PY
cat > "$BACKUP/rollback.sh" <<'ROLLBACK'
#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
if systemctl cat ops-console.service >/dev/null 2>&1; then systemctl disable --now ops-console.service; fi
if test -e /etc/systemd/system/ops-m0-forward.service; then
  cmp /root/ops-console-backup-m1a-20261017/ops-m0-forward.service.before /etc/systemd/system/ops-m0-forward.service
else
  install -m 644 /root/ops-console-backup-m1a-20261017/ops-m0-forward.service.before /etc/systemd/system/ops-m0-forward.service
  systemctl daemon-reload
fi
systemctl enable --now ops-m0-forward.service
tailscale serve --bg --https=443 http://127.0.0.1:8765
ufw status verbose > /root/ops-console-backup-m1a-20261017/ufw.rollback.txt
diff -u /root/ops-console-backup-m1a-20261017/ufw.before.txt /root/ops-console-backup-m1a-20261017/ufw.rollback.txt
echo 'M0 project endpoint restored; cloud data/config retained privately, no firewall changes.'
ROLLBACK
chmod 700 "$BACKUP/rollback.sh"
else
  test -x "$BACKUP/rollback.sh"
  ufw status verbose > "$BACKUP/ufw.before-resume.txt"
  diff -u "$BACKUP/ufw.before.txt" "$BACKUP/ufw.before-resume.txt"
  tailscale serve status --json > "$BACKUP/serve.before-resume.json"
  diff -u "$BACKUP/serve.before.json" "$BACKUP/serve.before-resume.json"
fi
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  # Alibaba's internal mirror overlaps Tailscale CGNAT. Do not widen firewall.
  # Use a signed official public source for this invocation only; /etc/apt is untouched.
  test -f /usr/share/keyrings/ubuntu-archive-keyring.gpg
  cp -an /var/lib/dpkg/status "$BACKUP/dpkg-status.before"
  cat > "$BACKUP/ubuntu-public.list" <<'SOURCES'
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://security.ubuntu.com/ubuntu noble-security main restricted universe multiverse
SOURCES
  APT_OPTIONS=(-o "Dir::Etc::sourcelist=$BACKUP/ubuntu-public.list" -o 'Dir::Etc::sourceparts=-' -o Acquire::ForceIPv4=true -o Acquire::Retries=1 -o Acquire::https::Timeout=20)
  apt-get "${APT_OPTIONS[@]}" update
  DEBIAN_FRONTEND=noninteractive apt-get "${APT_OPTIONS[@]}" install -y python3-venv
fi
if ! id ops-console >/dev/null 2>&1; then useradd --system --home-dir /var/lib/ops-console --shell /usr/sbin/nologin ops-console; fi
install -d -m 755 /opt/ops-console/releases
install -d -m 750 -o root -g ops-console /etc/ops-console
install -d -m 700 -o ops-console -g ops-console /var/lib/ops-console
install -d -m 755 "/opt/ops-console/releases/$RELEASE"
python3 - "$ARCHIVE" "/opt/ops-console/releases/$RELEASE" <<'PY'
import sys,tarfile
with tarfile.open(sys.argv[1],'r:gz') as archive:
    for member in archive.getmembers():
        assert member.isfile() and not member.name.startswith('/') and '..' not in member.name.split('/')
        assert member.name.split('/')[0] in {'cloud','contracts','static','deploy'}
    archive.extractall(sys.argv[2],filter='data')
PY
chmod -R go-w "/opt/ops-console/releases/$RELEASE"
python3 -m venv "/opt/ops-console/releases/$RELEASE/.venv"
"/opt/ops-console/releases/$RELEASE/.venv/bin/python" -m pip --isolated install --disable-pip-version-check --index-url https://pypi.org/simple --timeout 20 --retries 2 -r "/opt/ops-console/releases/$RELEASE/cloud/requirements.txt"
chmod -R a+rX,go-w "/opt/ops-console/releases/$RELEASE"
ln -s "/opt/ops-console/releases/$RELEASE" /opt/ops-console/current
install -m 644 "/opt/ops-console/current/deploy/ops-console.service" /etc/systemd/system/ops-console.service
systemd-analyze verify /etc/systemd/system/ops-console.service
systemctl daemon-reload
# Deliberately not started, enabled or switched until the user enters secrets.
test ! -e /etc/ops-console/config.json
ufw status verbose > "$BACKUP/ufw.staged.txt"
diff -u "$BACKUP/ufw.before.txt" "$BACKUP/ufw.staged.txt"
tailscale serve status --json > "$BACKUP/serve.staged.json"
diff -u "$BACKUP/serve.before.json" "$BACKUP/serve.staged.json"
systemctl is-active ops-m0-forward.service
echo 'Staged only. M0 is unchanged. Private terminal configuration is required before activation.'
