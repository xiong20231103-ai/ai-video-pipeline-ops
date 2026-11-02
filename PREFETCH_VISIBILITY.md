# Home prefetch visibility (review candidate, not deployed)

## Public data and read-only boundary

`prefetch_view.public_views` matches waiting receiver contracts against
`workbench_dir/handoff/download/prefetch/<taskId>.json`. It does not discover
new tasks from arbitrary filenames. It checks task/batch identity, counts and
state. Started projects disappear from the projection. Replacement plans are
only counted when their original contract hash matches a pending/imported
contract. Interrupted projects show progress but no replenishment button,
matching the receiver's finished-only acceptance rule.

The response whitelist contains task/batch identity, date, sequence, project,
material, state, completed/total, missing count, accepted-pending count and a
stable hash of the remaining gap. No source URLs, local paths, process data,
credentials or raw errors are added. Existing task stage and final-video
counts are unchanged.

`/api/dashboard/summary` and full dashboard add `prefetchViews`; task-box items
add `prefetch`. The existing agent already forwards these approved GET bodies:
`ReadOnlyAgent.collect -> Ledger.enqueue -> upload_loop -> POST /agent/push
-> Store.push -> responses cache`. No agent deployment is required for these
additive fields. `test_prefetch_agent_projection.py` exercises the actual
outbox/cache with private source fields and asserts they are absent upstream.

## Browser behavior

One top warning region is anchored beside `gapQuickBar`. Its data and card
labels use the same projection. The existing local early-replenishment dialog
is reused; no new write endpoint is introduced. Cloud wrappers set a read-only
flag; that surface displays “请在家里 Dashboard 补链”, not a write control.

Both `/` and `/static/index.html` render app.js's SHA-256-derived version URL
and return `Cache-Control: no-store`. Source profiles retain all historical
allowlisted hashes, register only two exact new app byte variants, and require
exact helper hashes. AST tests constrain the source delta. Offline replay also
tests a nonempty prefetch snapshot using frozen filesystem ports.

## Review and deployment

This branch is code/test only. Do not merge or deploy automatically. Review it
before the cloud companion; then restart the home Dashboard in a safe window
only after approval. Existing workbench/receiver do not need a restart for this
read-only feature. No production status or task contract is migrated.

The frontend source inventory also repairs three omitted PR #84 functions,
reproduced as a failing origin/main inventory test; old entry IDs/evidence are
preserved, new pending entries have no fabricated PR number. Exact test totals
and baseline comparison are in the combined delivery report.
