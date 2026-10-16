# M1a: Tailnet login, response cache and read-only home agent

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
3. USER ONLY in the cloud terminal:

   ```bash
   sudo /opt/ops-console/current/.venv/bin/python /opt/ops-console/current/cloud/admin.py configure
   ```

   Input an invitation (12+ characters) and a fixed agent token (32+ characters)
   using hidden prompts. Keep the token privately for Claude's later home-agent
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
