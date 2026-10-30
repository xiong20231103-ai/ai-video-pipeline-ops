# Console-session startup protection

This helper is used by `launch.ps1` and `dashboard-watchdog.ps1` before dependency checks, configuration reads, health requests, mutexes or status writes. `app.py` also checks the native Windows session before importing application modules, covering direct Python and ASGI imports. The startup VBS continues through the guarded watchdog.

Only the active console session may start these production roles. The guard does not trust SESSIONNAME. Unknown session identity is refused; a transient missing console retries a bounded number of times. Refusals write diagnostic metadata under `data/session-guard`; log failure does not permit startup. Dot-sourcing the PowerShell helper does not change the caller's StrictMode. Existing watchdog instance locking and server behavior are preserved.

Deploy the three entry files and their Python/PowerShell helper dependencies as one reviewed group, after confirming the pipeline is idle. Preserve unrelated local modifications when integrating; do not replace an entire production checkout with a worktree. Back up exact current files first. Do not remove a helper while an entry still imports it. This change itself does not change Windows, scheduled tasks, ports, credentials or default execution mode.

Rollback requires an idle pipeline and restoration of the complete backed-up entry/helper group. Do not replace files or restart services during an active batch.

Run `deploy/pip/Test-SessionGuard.ps1` and `deploy/pip/Test-DashboardEntry.ps1` using Windows PowerShell 5.1. The latter executes copies of the full entry scripts in temporary fixtures with mocked native session identity; it never starts the production Dashboard. Python regression uses `tools/run_isolated_tests.py`, which limits writes to the worktree/temp and blocks live HTTP/process execution.

Real child-session startup, watchdog behavior and a three-minute duplicate-service check remain required before PiP acceptance. These unit/fixture tests do not replace those checks. Other production roles require their own protected entrypoints. No system setting change, PiP login or deployment is performed by this helper.
