#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/root/ops-console-backup-m1b-sources-$stamp-$$"
mkdir -m 0700 "$backup"
export OPS_SOURCE_BACKUP="$backup"
iptables-save > "$backup/iptables.before"
ip6tables-save > "$backup/ip6tables.before"
ufw status verbose > "$backup/ufw.before"
restore_on_failure() {
    code=$?
    if test "$code" != 0 && test -x "$backup/rollback.sh"; then
        echo 'Validation failed; restoring only the saved APT/pip configuration.'
        "$backup/rollback.sh"
    fi
    exit "$code"
}
trap restore_on_failure EXIT
python3 -B - <<'PY'
import configparser,hashlib,json,os,re,shutil,stat
from pathlib import Path
from urllib.parse import urlsplit
backup=Path(os.environ['OPS_SOURCE_BACKUP'])
paths=[Path('/etc/apt/sources.list')]
paths+=sorted(Path('/etc/apt/sources.list.d').glob('*.list'))+sorted(Path('/etc/apt/sources.list.d').glob('*.sources'))
paths += [Path('/etc/pip.conf'),Path('/root/.pip/pip.conf'),Path('/root/.config/pip/pip.conf'),Path('/home/admin/.pip/pip.conf'),Path('/home/admin/.config/pip/pip.conf')]
records=[]; replacements={}
for path in paths:
    if path.is_symlink(): raise SystemExit('Refusing symlink: '+str(path))
    record={'path':str(path),'exists':path.exists()}
    if path.exists():
        info=path.stat(); saved=backup/'files'/str(path).lstrip('/'); saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,saved); os.chmod(saved,0o600)
        record.update(mode=stat.S_IMODE(info.st_mode),uid=info.st_uid,gid=info.st_gid,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        text=path.read_text()
        if '/apt/' in str(path):
            updated=re.sub(r'https?://mirrors\.cloud\.aliyuncs\.com(?=/ubuntu(?:/|\s|$))','https://mirrors.aliyun.com',text)
        else:
            parser=configparser.RawConfigParser(); parser.read_string(text)
            for section in parser.sections():
                for option,value in list(parser.items(section)):
                    if option in {'index-url','extra-index-url'} and 'mirrors.cloud.aliyuncs.com' in value:
                        if option=='extra-index-url': raise SystemExit('Unexpected extra index; explicit review required')
                        parser.set(section,option,'https://pypi.org/simple')
                    if option=='trusted-host' and 'mirrors.cloud.aliyuncs.com' in value:
                        remaining=' '.join(host for host in value.split() if host!='mirrors.cloud.aliyuncs.com')
                        if remaining: parser.set(section,option,remaining)
                        else: parser.remove_option(section,option)
            import io
            output=io.StringIO(); parser.write(output); updated=output.getvalue()
            if 'mirrors.cloud.aliyuncs.com' not in text: updated=text
        if 'mirrors.cloud.aliyuncs.com' in updated and not all('mirrors.cloud.aliyuncs.com' not in line or line.lstrip().startswith('#') for line in updated.splitlines()):
            raise SystemExit('Unrecognized active internal mirror; explicit review required')
        if updated!=text:
            replacements[str(path)]=updated
            record['changed']=True
    records.append(record)
(backup/'manifest.json').write_text(json.dumps(records,indent=2)+'\n'); os.chmod(backup/'manifest.json',0o600)
rollback='''#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
python3 -B - "$0" <<'RESTORE'
from pathlib import Path
import json,os,shutil,sys
backup=Path(sys.argv[1]).resolve().parent
for row in json.loads((backup/'manifest.json').read_text()):
    if not row.get('changed'): continue
    path=Path(row['path'])
    if row['exists']:
        shutil.copy2(backup/'files'/str(path).lstrip('/'),path)
        os.chown(path,row['uid'],row['gid']); os.chmod(path,row['mode'])
    elif path.exists(): path.unlink()
print('Restored APT/pip source configuration; package indexes are rebuildable and were not restored. No firewall or service configuration changed.')
RESTORE
'''
(backup/'rollback.sh').write_text(rollback); os.chmod(backup/'rollback.sh',0o700)
# Backups and the runnable rollback exist before the first mutation.
for name,text in replacements.items():
    path=Path(name); info=path.stat(); temporary=path.with_name(path.name+'.ops-m1b.tmp')
    if temporary.exists(): raise SystemExit('Refusing existing staging file')
    temporary.write_text(text); os.chown(temporary,info.st_uid,info.st_gid); os.chmod(temporary,stat.S_IMODE(info.st_mode)); temporary.replace(path)
    print('Changed source configuration:',name)
print('Rollback: sudo '+str(backup/'rollback.sh'))
print('Replacement files:',len(replacements))
PY
systemctl is-enabled apt-daily.timer apt-daily-upgrade.timer
systemctl is-active apt-daily.timer apt-daily-upgrade.timer
apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o APT::Update::Error-Mode=any update
unattended-upgrade --dry-run --verbose
python3 -B - <<'PY'
import configparser,os,urllib.request
from pathlib import Path
if any(key in os.environ for key in ('PIP_INDEX_URL','PIP_EXTRA_INDEX_URL','PIP_CONFIG_FILE')):raise SystemExit('Environment overrides pip source; explicit review required')
for path in (Path('/root/.pip/pip.conf'),Path('/root/.config/pip/pip.conf'),Path('/etc/pip.conf'),Path('/home/admin/.pip/pip.conf'),Path('/home/admin/.config/pip/pip.conf')):
    if path.exists():
        parser=configparser.RawConfigParser(); parser.read(path)
        if parser.has_option('global','index-url'):
            value=parser.get('global','index-url')
            if value!='https://pypi.org/simple': raise SystemExit('Unexpected effective pip index; manual review required')
            print('Verified public pip index for',path)
with urllib.request.urlopen('https://pypi.org/simple/pip/',timeout=30) as response:
    print('Official PyPI HTTPS status:',response.status)
PY
iptables-save > "$backup/iptables.after"
ip6tables-save > "$backup/ip6tables.after"
ufw status verbose > "$backup/ufw.after"
python3 -B - <<'PY'
from pathlib import Path
import os,re
backup=Path(os.environ['OPS_SOURCE_BACKUP'])
def rules(name):
    return '\n'.join(re.sub(r'\[[0-9]+:[0-9]+\]','[counters]',line) for line in (backup/name).read_text().splitlines() if not line.startswith('#'))
for family in ('iptables','ip6tables'):
    if rules(family+'.before')!=rules(family+'.after'):raise SystemExit(family+' RULE DIFFERENCE: explicit review required')
    print(family+' normalized rule diff: empty (timestamps/counters excluded)')
PY
diff -u "$backup/ufw.before" "$backup/ufw.after"
echo 'Cloud source repair validation completed; no package upgrade or firewall mutation command was run.'
trap - EXIT
