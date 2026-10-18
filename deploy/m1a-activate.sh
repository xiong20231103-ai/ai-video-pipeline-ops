#!/bin/bash
# Run only after the user has entered private configuration on the server.
set -euo pipefail
test "$(id -u)" = 0
test -s /etc/ops-console/config.json
test "$(stat -c %a /etc/ops-console/config.json)" = 600
BACKUP=/root/ops-console-backup-m1a-activate-20261017
test ! -e "$BACKUP"
umask 077
install -d -m 700 "$BACKUP"
tailscale serve status --json > "$BACKUP/serve.before.json"
ufw status verbose > "$BACKUP/ufw.before.txt"
iptables-save > "$BACKUP/iptables.rules"
ip6tables-save > "$BACKUP/ip6tables.rules"
cp /root/ops-console-backup-m1a-20261017/rollback.sh "$BACKUP/rollback.sh"
chmod 700 "$BACKUP/rollback.sh"
cp -p /etc/ops-console/config.json "$BACKUP/config.before.json"
chmod 600 "$BACKUP/config.before.json"
systemctl enable --now ops-console.service
for attempt in {1..20}; do
  if curl --fail --silent http://127.0.0.1:8000/ready >/dev/null; then break; fi
  sleep 1
done
curl --fail --silent --show-error http://127.0.0.1:8000/ready
# Switch one owned HTTPS root. Never reset all Serve configuration.
tailscale serve --bg --https=443 http://127.0.0.1:8000
# Fail closed if the new login is not reachable; do not leave the old jump as a bypass.
systemctl disable --now ops-m0-forward.service
rm -- /etc/systemd/system/ops-m0-forward.service
systemctl daemon-reload
test "$(curl --silent --show-error --max-time 15 --output /dev/null --write-out '%{http_code}' https://ops.tail830b6f.ts.net/)" = 303
test "$(curl --silent --show-error --max-time 15 --output /dev/null --write-out '%{http_code}' https://ops.tail830b6f.ts.net/api/dashboard)" = 401
tailscale serve status --json
tailscale funnel status
systemctl status ops-console.service --no-pager --full
ss -lntup
ufw status verbose > "$BACKUP/ufw.after.txt"
diff -u "$BACKUP/ufw.before.txt" "$BACKUP/ufw.after.txt"
echo 'M1a active, M0 socat stopped, no public port or firewall changes.'
