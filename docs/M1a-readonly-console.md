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
- Canonical query keys, bounded 128-key single-flight read queue, 180-second expiry,
  one 120-second read lease, explicit pending 202, no pending object delivered to
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


## Freshness and slow-read acceptance follow-up (2026-10-17)

The old summary uses a semantic ETag which omits scan-clock fields; its 304
contains no current scan timestamp. Every existing polling slot now performs
an unconditional body read if no full response has been obtained in the last
60 monotonic seconds. This adds no GETs and does not invent a scan timestamp
from a 304. Restart also forces an initial full response.

Home GET timeout comes from the explicit endpoint matrix, not a global 15s.
Safety allows 90s for eight serial control-plane calls and local inventory;
CapCut/audio inventories allow 90s, production inventory 120s, subtitle 30s.
Slow reads report busy while the separate heartbeat remains live, then restore
the prior engine state. Timeouts remain recorded as failures. No new home POST,
redirect, arbitrary path or port is allowed.

Freshness rows refer to the particular data versions the browser has read.
Previously visited keys remain in the list after date/batch selection; the
page explains this and labels capture age as that version's last fetch. It
does not assign a new cache version's time to an older displayed body.

The first real observation recorded about 23m44s before its observer sessions
were lost: active 377 GETs/1 safety timeout, idle 73 GETs/0 failures/0 history
polls; real browser login/data were user-confirmed. That window is incomplete
and predates this correction. Do not claim a complete 30-minute result or
post-fix production acceptance from the 132 isolated tests. Re-run a full
continuous active/idle window, preserving interruptions explicitly.


## Cooperative lifecycle and task migration (2026-10-18)

The previous task wrapper could leave the venv launcher and actual Python
orphaned after task stop. Routine source updates now create owned
`%LOCALAPPDATA%\OpsAgent\maintenance.json` and `stop-request.json`, wait for
the byte lock and task wrapper to exit, replace only the 13 source files, clear
only that request's files, and explicitly start/verify a new running instance
of the expected commit. They do not read private credentials, stop/disable
tasks, kill processes, install packages or require Administrator PowerShell.
An interrupted operation retains maintenance and its one-command rollback.

The PowerShell task remains hidden but owns a Windows Job Object with
KILL_ON_JOB_CLOSE. Existing venv Python is created suspended, assigned to the
job before resume, and its exit code propagates to the task. Closing the wrapper
also closes the whole managed tree. Restart delay is PT1M; acceptance records
actual recovery seconds including startup. The task grants only the current
exact user read/execute so ordinary updates can start it; other task rights
are preserved. File lock and IgnoreNew both prevent duplicate agents.

Cooperative shutdown bounds all read-worker joins to two seconds total; daemon
GET workers may be cut off at process exit. This is an M1a read-only contract,
not a safe-drain contract for future writes. M2 must specify result ambiguity
and reconciliation before enabling any command execution.

The installed legacy source cannot read a stop file, and the old task ACL
cannot be changed by the unelevated tool. One-time `deploy/agent-migrate.ps1`
therefore requires the user's Administrator PowerShell. It backs up source,
task XML, SDDL and enabled state first, writes a rollback, disables only the
owned retrying task, and replaces it. For a legacy locked process it queries
Restart Manager for this exact lock, checks every holder's full launcher argv,
allowed interpreter, current user SID and creation time, then pins a handle and
rechecks PID/creation before terminating only that old read-only agent. Unknown
holders fail closed. This legacy exception is not used in ordinary updates.

Run `deploy/agent-source-update.ps1` with the pinned source package and commit
for subsequent non-admin updates. The printed rollback restores source through
the same stop protocol. The migration's separate rollback restores old task
XML/SDDL and source, so it also restores the legacy limitations.

Tests distinguish isolated unit fixtures, real Windows process/lock/job tests
with synthetic services (zero home HTTP), and installed-task acceptance.
`deploy/agent-acceptance.ps1 -Action CrashRestart` validates exact installed
agent identity and records raw task states/instance IDs until automatic restart;
it never manually restarts the crashed agent. Crash acceptance needs admin
access to the hardened installed worker. `LogonBefore` / `LogonAfter` preserve
before/after evidence; the user must confirm actual logoff/logon at pipeline
idle. The script never logs off Windows. A new runtime instance alone is not
proof of a logoff/logon test. After these checks, re-run the full 30-minute
active/idle observation; the earlier 23m44s window remains incomplete.

Windows behavior references: [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject),
[task security](https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks),
[restart interval](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-restartinterval).


## Approved supervisor and five-minute fallback (2026-10-18)

Installed native PT1M application-exit recovery failed: 437.506 seconds without
a new instance. The user approved an explicit in-task supervisor and a second
trigger on the same task. Python failure closes the old Job, records
restart-wait/exit code/retry time, waits 60 monotonic seconds in interruptible
250ms slices, then starts a fresh Job. Normal exit or either maintenance/stop
file ends supervision. A per-state named mutex prevents competing supervisors.
Task Running describes the supervisor; actual agent liveness requires matching
PID/creation time and running Job/runtime metadata, not a stale runtime phase.

The original logon trigger remains. A second time trigger begins five minutes
after registration, repeats PT5M without Duration or EndBoundary indefinitely,
and uses the existing Interactive principal. Thus it runs during logged-in
sessions, including the current session for immediate acceptance, without
requiring a preliminary logoff. Logon starts immediately via the original
trigger. IgnoreNew skips timer firings while the supervisor runs. Ordinary code
updates do not re-register the task or reset this anchor. Waiting for the next
timer is bounded by five minutes; process startup adds its actual measured cost.

The wrapper checks maintenance/stop files before compilation or Python and
records maintenance-blocked with launcherPid=0 before exiting. The Python
launcher retains its own pre-import gate, and supervision checks again before
each attempt and during backoff. Neither gate reads private credentials.

Updating the existing task definition needs one user-admin operation; the tool
has read/execute, not task-write rights. Use the pinned package's migration tool
to back up source/XML/SDDL and publish a rollback before replacing only this
task. Existing credentials are retained. The new acceptance tool RecoveryAll
tests real Python failure/recovery, exact supervisor termination/Job exit and
actual timer recovery, then holds owned maintenance through another real timer
firing and proves no Python started. It writes raw samples and actual seconds,
uses monotonic deadlines, and never manually starts during either crash test.
Maintenance cleanup manually starts the agent and labels that explicitly.
Unknown process/task identity refuses termination; maintenance-test failure
retains owned markers and a printed cleanup rollback.

The CI supervisor fixture uses 500ms backoff only in a temporary C# harness to
test restart transitions quickly. A separate production-wrapper fixture verifies
the fixed 60s setting and interrupts it with stop; each stop/maintenance gate is
tested separately, as are duplicate supervisors and whole-tree termination.
These have synthetic services and zero home HTTP. Installed 60s/5min checks,
ordinary unelevated update, user logoff/logon and full 30-minute observation
remain separate real acceptance. Never infer them from fixture success.

## State JSON sharing repair (2026-10-18)

The installed b28c828 supervisor's first RecoveryAll attempt stopped on a sharing violation while reading task-job.json. The user's separate observation of Python recovery after 60 seconds remains historical evidence; supervisor recovery and maintenance-trigger acceptance did not run. Repeat all three formal checks on this repair before claiming acceptance.

Agent runtime and supervisor status are published to unique temporary files, flushed and closed, then atomically replaced. Windows readers share read/write/delete access. Python, PowerShell acceptance/update/migration, and the supervisor identity helper retry transient sharing, malformed/truncated JSON and briefly missing snapshots up to ten attempts with 200 ms between attempts. Missing stop/maintenance markers return immediately. Exhaustion fails visibly; readers do not print JSON payloads or infer success from stale status. C# supervisor only checks marker existence and does not parse state JSON.

The runtime whitelist now has 15 files (adds contracts/state_files.py and deploy/agent-json.ps1); standalone controllers have seven tools, including the same Python I/O module under agent_state_io.py. Backups copy both shared helpers so rollback is self-contained. Exactly the prior 11- and 13-file manifests remain accepted, with removal limited to known additive files. No credential files are copied or read by deployment tools.

Regression coverage includes real Windows exclusive and non-delete-shared handles, a held shared snapshot during replacement, repaired partial JSON, concurrent agent publication/readers, concurrent C# publication/PowerShell readers, bounded persistent failure preserving the old document and cleaning temporary files, and 13-to-15-file update/rollback. Temporary process/Job tests send zero home HTTP; they do not replace installed-task acceptance.

After CI succeeds, the pinned administrator handoff first backs up source/task XML/SDDL/enabled state and prints its exact rollback command, then upgrades only OpsConsoleReadonlyAgent and the independent agent directory. RecoveryAll repeats Python crash, supervisor crash across a real five-minute trigger, and maintenance across a real trigger. Ordinary unelevated graceful update is checked afterwards. User-controlled logoff/login and a fresh ten-minute baseline plus full thirty-minute observation remain outstanding. No production application restart, dependency installation, home POST or firewall change is part of this repair.


## Actual observation failure and safe worker diagnostics (2026-10-18)

After actual logoff/logon, the agent restarted automatically but workers repeatedly exited. The new ten-minute Dashboard baseline completed, while the subsequent active/idle observation was aborted and is not accepted. Root cause is not yet known: previous error reporting retained no worker/type/frame evidence. This change adds only a bounded latest-failure record (worker, exception class, basename/function/line, instance/version/time) and matching failed-runtime metadata. It never formats exceptions, messages, locals, source lines, tokens or response bodies. Diagnostic write failure still stops the worker and releases the lock; no unsafe traceback is emitted. A later successful restart does not erase last-worker-failure.json. Retry timing, polling, GET-only permissions and task definitions do not change.

Claude deployed the diagnostic version ebf4def; a real upload/SQLite failure was subsequently captured, as documented below. The new repair still needs Claude deployment to the independent agent directory. Do not merge this PR or claim the 30-minute acceptance passed; use the next real failure record to fix the demonstrated cause, then rerun the full observation. No actual credentials, runtime artifacts or production state are committed.


## PR #13: SQLite failure, foreground reads and cloud-only caches (2026-10-18)

Status: implementation and isolated tests, NOT production acceptance. The actual
safe diagnostic from ebf4def identifies upload -> Ledger.next -> Ledger.db line
36 (`BEGIN IMMEDIATE`) and OperationalError. That diagnostic did not include a
SQLite error code; do not claim an unrecorded code or an HTTP failure as fact.
The old reader unnecessarily acquired a reserved write lock. New WAL reads are
query-only, own writers serialize, and only SQLite BUSY/LOCKED become retryable
I/O. Other SQLite errors remain visible to the safe worker diagnostics, now with
an integer SQLite code. Upload next() is inside its existing retry boundary.
IncompleteRead is a separately reproduced wire-error gap; only that concrete
HTTP exception is converted to retryable I/O, never all HTTPException/errors.

Home storage:

- No completed-box/prefetch response archive on the agent. Migrate old sources
  one row at a time to source_validators(target, etag, semantic_hash, scanned),
  DROP the old body table and VACUUM before worker startup, after acquiring the
  single-instance lock. Validators and versions are small durable metadata.
- Outbox alone retains unsent payloads, at most one per canonical key. A matching
  acknowledgement deletes the row; a late acknowledgement cannot delete a newer
  version. A 304 carries no body; only an unacknowledged 200 may be preserved when
  coalescing. Missing/mismatched cloud base triggers a fresh GET.
- Default 48 MiB queue payload limit; evict oldest unsent rows until bounded and
  increment durable outboxDropped. This is a queue payload limit, not a claim
  that SQLite plus WAL plus filesystem overhead fits exactly 48/50 MiB. Full
  auto-vacuum reclaims deleted pages; report DB and WAL separately in acceptance.
- outbox_sizes is an additive metadata table: the original four-column outbox
  schema stays compatible with rollback. Old code recreates an empty sources
  table and performs a full GET on its first read. Do not back up response bodies
  as an additional permanent home archive. Runtime credentials are untouched.

Two bounded home GET channels: periodic/slow-demand/prefetch and foreground.
The long-poll watcher never waits for home HTTP. Fast box reads outrank ordinary
foreground work, long safety reads stay in the slow channel even when requested
by a page, same-target in-flight work coalesces, and on-demand uploads outrank
old periodic outbox work. Cache-recovery GET also uses these channels. At most
two home GETs are in progress; each channel's receiver health GET is sequential.
GET /agent/fetch-requests?wait=25 waits for a notification with a 250 ms fallback
for other server workers/restarts. The agent uses a 35-second transport timeout;
old-server immediate empty responses have a 250 ms compatibility delay. Browser
202 retry is 500 ms. A healthy network is required for the <=1-second delivery
acceptance target; this is not a network-independent guarantee.

User-confirmed revision: no immutable/permanent archive and NO dependency on
completionReceipt. No Dashboard contract/source change for box freezing.

All task boxes use stale-while-revalidate: return an existing cloud response
immediately, visibly aged. If a visible viewer opens a response older than 60
seconds, enqueue one background read. A cloud-only browser watcher refreshes
the rendered same box when its version/ETag changes; leaving the box cancels
that watcher. The top H4 reception clock is adapted only in cloud/readonly.js
to display actual cache/source age, including when frozen; every per-source
sample retains its age and stale colors. No green archive-age exemption.

Conservative freeze requires ALL: selected projects explicitly complete; a
reliable date-wide upload total and completed count equal the date's expected
video total with zero failures; and three observed days since the box display
content last changed. Expected totals require complete project identities and
per-project expected counts for every box on that date; missing, conflicting,
test/extra upload counts, partial historical rows or changed date membership
refuse freezing. Full chronological source observations, not an offline gap or
an old source timestamp, start/advance the three-day stability window. Exact
box/project/task identity and result fields define that content hash; scan
clocks, live processes and unrelated boxes do not reset it. These facts and
upload proofs live only in the cloud SQLite database.

A frozen box is never prefetched or refreshed by dedicated periodic box/date
reads. Only a visible user's open with cache older than 24 hours enqueues a
single refresh. The base full dashboard still refreshes shared current state.
A newly changed project/date count or missing evidence removes freezing.
The agent stores only paused/prefetch target strings, not results.

Visible authenticated viewers prefetch the latest 10 boxes in the existing
descending order, skipping frozen/fresh boxes. Other boxes keep a 60-second
minimum interval. Idle has none. Previous theoretical active/idle budgets are
1752/666 home GET/hour before startup and user demand; prefetch adds at most ten
cold reads and at most 600 steady-state GET/hour if all ten remain mutable.
Frozen dedicated reads reduce that bound. Actual deltas must be measured.

Acceptance after Claude's home deployment: cached and uncached box switch
latencies five times each, long-poll delivery latency, active/idle 30-minute
observation with request-count deltas by reason, baseline Dashboard CPU/memory,
agent working/private memory and DB/WAL bytes before/after. The existing actual
baseline was 602.574 seconds on Dashboard PID 31940; it may only be reused if
PID/source and pipeline conditions remain comparable. Do not call synthetic
fixtures or a briefly stable agent the completed observation. Do not merge this
PR until real acceptance. No home POST, production checkout edit, Dashboard
restart, firewall widening, public listener or Funnel is authorized here.

Rollback: use the code-only updater's generated backup rollback.ps1, which
gracefully stops only the independent agent and restores its exact source
manifest. The old code recreates its body cache on subsequent GET; removed
response archive bodies are deliberately not restored locally. Cloud uses the
upgrade backup's rollback.sh with additive schema retained. Exact paths are
recorded by the actual deployment; unexecuted rollback is not called tested.
