# Cloud prefetch visibility and notification (not deployed)

## Dependency and transport

Deploy only after the companion home prefetch projection is reviewed and
available. The existing installed read-only agent forwards the approved summary
GET body, through its SQLite outbox and `/agent/push`, into cloud `Store.responses`.
The cloud browser uses that cache, not home disk access. This does not authorize
additional reads or writes and requires no new agent endpoint/token.

Legacy and React v2 pages show prefetch progress and accepted-but-not-downloaded
replacements without changing original production stage/final counts. Cloud
early replenishment is **hint only**: “请在家里 Dashboard 补链”. The reviewed ordinary
command contract accepts only `urls/startNow` and targets `/api/tasks/replenish`;
it does not authorize `/api/tasks/prefetch-replenish/{task_id}`. No whitelist is
expanded here.

## Notification behavior

Fresh explicit `prefetchViews` observations feed an independent `prefetch`
ledger scope. Task identity plus remaining-gap fingerprint gives one notice
per task/gap, across repeated polls/restarts. Started or filled gaps close
silently. Obsolete pending messages are closed before send. Old producers
omitting the field and stale snapshots cannot falsely close an alert. No
`recovered` message is generated for this once-only fact. Existing `task_failed`
scope and tests remain independent.

Notifications follow existing enable/provider/quiet-hour controls. A newly
installed ledger treats its first observation as history (existing behavior),
so old gaps are displayed but not retroactively spammed as new notifications.

## Cloud 966d784 deployment prerequisite

No server was contacted or modified. Local git comparison shows the merge base
of 966d784 and main d888aaa is 4516ecd. `cloud/app.py` on main additionally mounts
PR #80 material-handoff routes; main also includes material package/contracts,
agent collection/snapshot/source-profile and prefetch notice changes. There is
no notification module diff between 966d784 and that main, so the existing
notification fix is retained by aligning to main, not dropped.

This is a main-based release: first align the cloud to reviewed main (including
PR #80 files/config requirements), then apply reviewed A/B changes and build
the v2 assets. Do not copy only cloud/app.py onto 966d784: its new imports/routes
require companion files and this feature requires the home public projection.
After approval, restart only ops-console for cloud code loading; restarting
the Windows agent/workbench/receiver is not needed for the additive GET fields.
These are future instructions, not actions performed by this task.
