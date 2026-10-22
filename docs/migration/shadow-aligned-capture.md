# Stable-input shadow evidence tools — first reviewable stage

This change is dormant and does not deploy, enable a collector, switch a source,
restart a process, run a real command, or modify installed Dashboard code. It is
based on PR #51; PR #50's independent audit is not a runtime dependency.

## Implemented

- `tools/shadow_capture.py`: explicit allowlisted state, bounded directory
  inventory, verified missing paths, process birth identity and existing external
  response facts. Any input/directory/absence/DB/WAL/HTTP generation/source or helper
  change during the window rejects the whole snapshot. No partial sample is called
  aligned. SQLite opens only scratch byte copies, never the production DB or SHM.
- `tools/shadow_observer.py`: explicitly supplied wrapper around an **existing**
  GET reader. It calls that reader once, tees the bytes already read by the caller,
  stores no headers, refuses credential bodies and invalidates incomplete/inflight
  or failed responses. No additional GET or POST is created. Nothing is installed
  globally or into a production process by these modules.
- Strict `SandboxIO` closure: unknown facts cannot silently become absent files.
  Complete directory inventories can prove descendant absence; metadata-only files
  still cannot be read as content. Missing HTTP facts also invalidate strict replay.
  The opt-in does not change existing fixture behavior or deployed agent settings.
- `tools/shadow_store.py`: immutable 64 KiB content-addressed chunks, exact restore,
  deduplication, single writer and hard approved byte budget. Retained evidence
  roots count against the budget. A full store refuses new evidence instead of
  deleting history, changing quotas or pretending its sample was complete.
- `tools/shadow_archive.py`: byte-verified nondestructive archival of the old
  passive store. Original evidence and its quota remain untouched. Archive bytes
  require separately approved capacity; archiving does not magically free space.
- Paired R1 and R5 **read** adapters; R2 independently compares source DB rows and
  exact evidence bytes after isolated history import. Lossless transfer alone does
  not accept timeline accuracy. R3 replays recorded ports and checks its original
  actual receipt as well as old/new output/effects; unknown/missing/unconsumed ports
  make the case incomplete, even if both branches raised the same exception.
- `tools/shadow_operation_records.py` can transform an existing completed HTTP
  receipt for the four exact R3 forwarding routes. Native upload/startup commands
  require an actual full runtime tape. Ambiguous 5xx/local parse/auth boundaries
  are refused rather than guessed. The adapter does not read a live ledger or send.
- Batch review distinguishes missing triggers, missing boundaries, unclosed input,
  differences and readiness for human review. It never sets `realShadowPassed` or
  `switchAccepted` true. Timeline acceptance is separately required for R2.

## Explicit CLI (reviewed paths only)

`python -B tools/shadow_evidence.py --help`

Commands: `capture-recorded`, `archive-passive`, `verify-archive`, `capacity`,
`compare --module R1|R2|R3|R5`.

All source/output paths and archive/store capacity budgets must be explicitly
supplied. Comparison outputs must be fresh and outside captured roots and the
legacy source directory. `capture-recorded` consumes already recorded observations;
it does not obtain new HTTP responses or install a live observer.

No installation command for the home machine is authorized by this PR. Any later
installation must happen idle, under Claude review, with a backup/rollback, disabled
cleanup/autoRecovery, no migration pointer and an unchanged old production behavior.
No existing recorder files, schedule, settings or 2 GiB cap were changed here.

## Still required before calling the complete tool delivered

1. Reviewed passive runtime integration connecting the memory observer to the old
   reader without extra requests, and an installer/rollback verified against the
   actual startup/watchdog contract. This PR only exposes the cold integration API.
2. Capture of actual complete R3 runtime port tapes for upload-worker start/timeout,
   and R5 write/protection executions without persisting preview capabilities.
   R5 read parity is not acceptance of a real cleanup operation.
3. R2 timeline reference/coverage from actual batch sources, including waits,
   failures and duration/ETA quality; lossless import is only one layer.
4. Two distinct complete real batches with per-operation triggers. Existing passive
   evidence is retained but cannot be retroactively upgraded into those samples.

The current verified real-shadow batch count remains **0/2**. This is an engineering
progress PR, not a production acceptance or Friday switch authorization.
