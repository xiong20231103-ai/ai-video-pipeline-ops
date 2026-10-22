# Agent read observer wiring — review stage

This follow-up depends on #53. It adds an explicit in-memory `read_observer` injection to `ReadOnlyAgent.home` without adding HTTP requests, modifying headers/ETag timing, changing bytes returned to callers, creating threads or writing evidence. Omitted injection leaves the deployed behavior unchanged. No configuration file enables this automatically.

The agent consumes each body with one bounded positive-size read. The earlier generic response tee could not classify that read as finished without a second EOF read, which the agent does not perform. This adapter observes only after the original read and JSON parse succeed. Incomplete, oversized, credential-bearing and 304 responses invalidate the observation. Conditional reads remain unchanged, so incomplete 304 windows must be rejected rather than fabricated as aligned samples. A later generation cannot be overwritten by an earlier response.

## Review and idle installation gate

- Do not install during the currently running 10.22 batch. #52/#53 remain open for Claude review.
- This commit is an injection seam, not a complete production recorder/installer. Do not create engine-settings.json or migration-settings.json, change scheduled tasks/watchdogs, or enable source authority to activate it.
- Agent restart/backup must use the reviewed agent-source-update deployment contract, with a git-object source package, predeployment hashes and its generated rollback script. A runnable installation/rollback command cannot be truthfully produced before the final approved package/version and idle host state are selected.
- Next required work: review source roots/closed input plan and explicit hard quota; connect this memory observation to bounded stable-window capture and retained evidence store; isolate capture failures from heartbeat/write worker; verify stop/maintenance/watchdog lifecycle and rollback with fixtures. This patch alone neither writes aligned evidence nor proves a batch comparison.
- R3 full runtime port tapes, R5 executed protection/write evidence and R2 timeline accuracy still need their own capture coverage. Two real completed batches are required; absent triggers stay unaccepted.

## Validation

Synthetic transport tests verify one original request, unchanged result, observer errors isolated, secret body rejection, 304 invalidation, concurrent-generation ordering and unlisted reads ignored. No live source URLs, production paths, settings or service actions are used by these tests. Real shadow count remains 0/2.
