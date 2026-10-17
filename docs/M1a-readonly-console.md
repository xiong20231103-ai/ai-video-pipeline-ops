# M1a: Tailnet login, response cache and read-only home agent

Canonical private entry: https://ops.tail830b6f.ts.net (node name `ops`).

Depends on R0 PR #11 and #12. Cloud deployment may use this reviewed branch
without merging home production code. No home process is started by deployment.

## Delivered contract

- Private HTTPS only, served by the existing node's Serve 443. App binds only
  127.0.0.1:8000. No Funnel, firewall edits or public listener.
- Argon2id passwords, invitation-only registration (default two accounts), atomic
  quota, 30-day revocable Secure/HttpOnly/SameSite=Lax sessions, Origin/CSRF writes,
  login/registration rate limits, interactive reset/delete CLI and password UI.
- Versioned original JSON/status cache with independent content hash, successful
  home fetch time, content change time, cloud receive time, source scan and source
  health. A 304 renews successful fetch time without inventing a source scan.
  Backfill carries same-host elapsed age so delayed data does not look fresh.
- Canonical query keys, bounded 128-key single-flight read queue, 45-second expiry,
  one 30-second read lease, explicit pending 202, no pending object delivered to
  the legacy business renderer. Per-section source freshness and independent
  full-page refresh; cached data remains visible on errors.
- Health preserves receiver formalBatchTotal/projectTotals/contractVersion;
  missing/stale/invalid health fails closed. No-token submission write APIs arrive
  in M2a; M1a does not pretend they are already available.
- No home writes: every browser /api POST is refused server-side, including
  testing/reset. Cloud safe-continue/cleanup remain disabled even if an old cached
  business response says allowed=true. H3 and deployed-agent gates remain closed.

## Isolated verification

```powershell
python -m pip install --target .test-deps -r requirements.txt -r cloud/requirements-test.txt
python -B tools/run_isolated_tests.py
node --check cloud/readonly.js
node --check cloud/login.js
```

The guard allows only standard-library Windows asyncio socketpair's ephemeral
loopback self-connection, not arbitrary localhost connections/listeners. All
production sockets, process launch and checkout/temp-external writes remain
blocked. Tests use ASGI memory transport, not a listening home server.
Local browser verification intercepts every request with inert fixtures and
checks login, pending reads, source-age UI, disabled writes and mobile overflow.
Real home collection/CPU/memory and a complete production batch are not yet
verified; no unperformed shadow or production test is called passed.

## Cloud deployment: stage, enter secrets privately, then activate

1. Build/upload a code-only tar containing cloud/, the needed contracts, static/
   and deploy/. No config.json, runtime DB, credential, fixture or log is shipped.
2. As root, run deploy/m1a-stage.sh ARCHIVE SHA256 COMMIT. It snapshots rules,
   current project Serve and M0 unit into /root/ops-console-backup-m1a-20261017/
   before changes, writes rollback.sh, prepares a private no-login service user,
   release venv, data/config directories and unit. It does NOT start/enable the
   new service, change Serve or stop M0. Existing project paths abort staging.
   If initial staging stopped before any project path was installed, an explicit
   fourth argument resume-before-install reuses the original backup only after
   proving Serve/UFW unchanged and all project paths still absent. Ubuntu venv
   bootstrap uses a temporary signed official public source list under the
   backup directory; it does not relax CGNAT rules or modify /etc/apt sources.
   resume-unactivated-install additionally permits existing release scaffolding
   only when there is no current link, unit, credential configuration or data.
   Venv pip uses an explicit official PyPI URL and isolated configuration; the
   system's internal pip mirror is not changed or added to firewall exceptions.
3. USER ONLY in the cloud terminal:

   ```bash
   sudo /opt/ops-console/current/.venv/bin/python /opt/ops-console/current/cloud/admin.py configure
   ```

   Input an invitation (12-256 characters) and a fixed agent token (32-256
   printable ASCII characters, without spaces/control characters)
   using hidden prompts. Keep the token privately for the later home-agent
   deployment. Do not send either value to chat. Only invitation/agent verifiers
   are stored in owner-only /etc/ops-console/config.json; nothing echoes secrets.
   Login password is chosen by the user on the private registration page later.
4. After configuration, deploy/m1a-activate.sh snapshots again, starts the app,
   checks local readiness, changes only this project's Serve443 root, disables
   and removes only ops-m0-forward.service (backup retained), and checks unauth
   root303/API401, Tailnet-only Serve, listeners and unchanged UFW. It never uses
   serve reset. On any failure stop and use the prepared rollback if appropriate.
5. User registers/logs in on the HTTPS node. Until Claude deploys the home agent,
   the UI explicitly shows waiting for home data. Do not treat placeholder data
   or an absent heartbeat as successful live acceptance.

## One-command cloud rollback

```bash
sudo /root/ops-console-backup-m1a-20261017/rollback.sh
```

Stops/disables the new app, restores the backed-up project M0 unit if needed and
its original Tailnet Serve443 proxy. Cloud config/DB/releases are retained
privately for recovery; shared Python packages are not uninstalled. This restores
the pre-M1 private unauthenticated M0 jump, so it is a deliberate rollback, not a
parallel login bypass. No firewall rules change, no household process is touched.
M0 compatibility/DNS services are not removed. Activation also keeps a copy of
this command in its own backup directory.

## Home-agent deployment: Claude only, idle window

The agent is code/PR only. It never starts/stops/restarts Dashboard or a workbench.
All reads use fixed loopback8765, health also reads receiver8766. A local OS file
lock prohibits a second instance. Heartbeat, collection, upload and read-demand
threads are independent; all old-engine GETs share a single lock. Durable SQLite
versions/outbox survive restart and compact unsent content without dropping the
base behind a 304. Unknown write outcomes are not part of this read-only milestone.

Before changing any home scheduled task or local agent files, Claude must back
up that task/config and create an idle-window rollback. During that deployment,
the USER runs python -m agent.configure from the approved checkout to enter the
same token privately. Owner/SYSTEM/Administrators-only Windows ACL protects the
LOCALAPPDATA/OpsAgent configuration; never place it in a repo or PR. Then Claude
can run python -m agent.readonly with the existing Dashboard Python environment,
and install the reviewed per-user restart-on-failure startup task. No automatic
home deployment command has been executed in this PR.

Rollback home agent: stop/disable only its own future task and restore its backed
up configuration, leave Dashboard/workbench running. Verify no in-flight read
and no second agent before a restart. Preserve the agent ledger across reinstall;
discarding version state cannot safely force old data over cloud state.

Future M1b adds exact-file encrypted-secret backups/restore drill; H3 adds atomic
target validation; M2a/M2b add writes/notifications behind deployed dependencies.

## Review amendment: viewer-aware polling, identity limits and independent deployment

Cloud persists the latest authenticated GET page/API request time. Anonymous
health, login/static resources and agent traffic do not count. The frontend
marks API/status requests from hidden tabs `X-Ops-Page-Visible: false`; a hidden
legacy timer therefore does not keep viewing active. Heartbeat and fetch replies
carry a bounded 0..120 second relative lease, used with agent monotonic time.
Missing/malformed lease information or two minutes without a visible request
falls back to idle, including if the cloud goes offline.

| Scheduled home GETs per hour | Before (always) | After: viewing | After: idle |
|---|---:|---:|---:|
| Dashboard summary | 720 | 720 | 60 |
| Dashboard + receiver health (two GETs per collection) | 240 | 240 | 120 |
| Full dashboard (no date) | 60 | 60 | 6 |
| Eight other current-state routes (unchanged 60s) | 480 | 480 | 480 |
| 14 dates x 3 history routes | 252 | 252 | 0 |
| Total | 1752 | 1752 | 666 |

These are nominal steady-state maxima at zero response cost; they exclude first
load and on-demand GETs. Collection is serialized, with intervals measured from
completion, and never catches up missed polling bursts. Actual totals are lower
when requests take time. Idle history remains available only through the 202
on-demand flow. Counters include failed GET attempts and receiver health, by
minute/target/port/active-or-idle/reason; no bodies, headers or credentials.
`python -B -m agent.metrics --since EPOCH --until EPOCH` reads counters without
opening private configuration. Minute-bucket boundaries must be reported when
comparing a real 30-minute window. Budget reduction in idle is about 62%.

The existing Dashboard actually listens on local Tailscale 100.92.17.9:8765,
not 127.0.0.1. The agent is fixed to that existing local address, ports 8765 and
8766 (8766 health only). It does not change production bindings. All home
requests explicitly use GET with no body or bearer token. Environment proxies
are disabled and redirects are refused for both cloud and home transports.
Cloud may receive POST uploads/heartbeats; this does not permit POST to home.

Rate buckets trust Serve identity only from loopback, with HTTPS forwarding
and a single valid Tailnet X-Forwarded-For. They prefer Tailscale-User-Login;
tagged nodes use the forwarded IP. Remote/malformed/multi-hop headers fall back
to peer identity, so forging headers on a direct request cannot rotate buckets.
The bucket key is a SHA256 identity digest, not a raw login/IP. This is rate
isolation only, never a replacement for application authentication.
Upstream rationale: https://tailscale.com/docs/features/tailscale-serve#identity-headers
and Tailscale 1.104.1 ipn/ipnlocal/serve.go lines 1014-1050 (Serve overwrites
X-Forwarded-For and removes/replaces identity headers).

User authorization now permits deploying only the read-only agent independently,
without merging any PR. Ship a source/manifest whitelist from this PR to
E:\Backup\ops-agent; never copy production config/data. Python must be the
existing %LOCALAPPDATA%\TikHubOPS\venv_cuda\Scripts\python.exe. Install or upgrade
no packages there. Missing dependencies require stopping and notifying the user.

USER ONLY, in a local PowerShell window (not the server terminal):

```powershell
Set-Location -LiteralPath 'E:\Backup\ops-agent'
& "$env:LOCALAPPDATA\TikHubOPS\venv_cuda\Scripts\python.exe" -B -m agent.configure
```

Enter the SAME privately retained cloud agent token at the hidden prompt.
Configuration is owner-restricted under LOCALAPPDATA\OpsAgent. The assistant
never reads/displays/records its content. This does not start the agent.

After this and green tests, install/start the one owned task:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\Backup\ops-agent\deploy\agent-task.ps1 -Action Install -StartNow
```

The installer first creates an ACL-restricted timestamped backup of the previous
owned task (if present), a completed-backup marker and self-contained rollback.
It refuses a task-name collision owned by another program. Exactly one task,
OpsConsoleReadonlyAgent, runs after this user's logon, hidden, limited interactive
privileges, no stored Windows password, IgnoreNew plus agent file lock, restart
on nonzero exit after one minute, no execution time limit. The hidden wrapper
waits for the exact child Python and propagates its exit code. The launcher
emits only a generic failure message, never exception/config contents. It does
not start/stop Dashboard, workbench or other production processes.

One-command uninstall/rollback (use the exact path printed by installation):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File E:\Backup\ops-agent-task-backups\TIMESTAMP\rollback.ps1
```

Rollback stops/unregisters only this owned task and restores its prior definition
if one existed, retaining private config/data/files. It does not delete logs or
kill processes by generic name. Definition/syntax tests do not count as a real
logon/crash/rollback test; record real acceptance separately.

Before starting the agent, sample the unchanged Dashboard process for ten
minutes. After startup observe thirty minutes, explicitly record each mode's
actual duration (including the 120s idle grace), GET counts/failures, source-age
and pipeline/log health. Keep raw CPU totals, normalized machine CPU, working
set/private bytes and process creation identity; a restart invalidates the
comparison. No measured load or complete-batch result may be inferred from unit
tests. Private browser login and token entry are user operations, never read
session/config secrets to simulate their acceptance.

For an already active cloud release use deploy/m1a-upgrade.sh ARCHIVE SHA COMMIT.
It snapshots the live DB using SQLite backup, current release/unit, Serve and
firewall before changes, writes one-command rollback, builds a separate venv,
atomically switches only current and restarts only ops-console. Additive schema
rollback retains current user/session data; snapshot restore is not automatic.
No new public port, firewall or Serve changes. Default APT/pip source repair
belongs to M1b and must not be claimed complete here.


## Node rename before private agent configuration (2026-10-17)

The canonical origin is https://ops.tail830b6f.ts.net. Agent configure and cloud
setup defaults, activation probes and regression tests use this name. Registered
users/password hashes and existing database sessions are retained. Browser
cookies are host-scoped and are not copied from the old hostname: log in again
on ops with the same account/password. Old-origin POSTs remain rejected.

Before rename snapshot the private config, SQLite DB, node hostname preference,
release, owned Serve handler, UFW and IPv4/IPv6 rules under a root-only backup.
Set only `tailscale set --hostname=ops`; if effective Self.DNSName does not become
ops.tail830b6f.ts.net, stop for the user's admin-console override. Never choose a
different name or silently proceed with an old DNSName.

Tailscale 1.104.1 retains the old Serve Web domain key after changing the node
name. Migrate only this project's old/new domain keys, preserving the loopback
proxy and every unrelated handler/TCP/service object. Use the daemon local
serve-config API with its ETag/If-Match to reject concurrent overwrites. Do not
use serve reset or service-wide set-config. Serve obtains its new TLS certificate
automatically when the new HTTPS name is accessed; validate normally, without -k.

Change only origin in the owner-only cloud configuration, retaining the other
fields and permissions; restart only ops-console. Verify new /login=200,
anonymous API=401, certificate SAN/expiry/normal trust, unchanged firewall/Serve
scope and retained registered-user count. Actual user login is performed
privately by the user; fixture login replay does not count as real credentials.

Rename rollback:

```bash
sudo /root/ops-console-backup-rename-ops-20261017/rollback.sh
```

It restores the prior hostname preference, waits for the prior effective DNS,
migrates back only the owned Serve key and origin, retains current credentials
and user/session data, then restarts only cloud ops-console. It does not revert
unrelated Serve/firewall state or delete backups. Code rollback is independent
because deployed config supplies the runtime origin; preserve this distinction
when using the existing code-release rollback script.

The independent home source whitelist must be backed up and updated to this PR
commit with every file hash verified before notifying the user to run configure.
If a private home configuration already exists, stop rather than reading or
overwriting it. No agent task runs until user-only token entry and acceptance.
