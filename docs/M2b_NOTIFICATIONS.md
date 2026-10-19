# M2b notification contract (implementation in progress)

This milestone runs in the cloud only. It consumes existing response cache and
heartbeat metadata; it adds no home polling, process changes or execution calls.
The provider/channel remains pending the user's choice (WeCom, ServerChan, Bark).
No real webhook is present in source, fixtures, logs or this document. No real
message has been sent and the cloud application is not yet wired to this worker.

Snapshot delivery is best effort: short failures between snapshots can be missed.
No complete event cursor is claimed. Existing limited /api/events is not treated
as a complete incremental log. Current failures require current task/batch identity,
component, phase, attempt and error code; date totals cannot manufacture failures.
Cleanup warnings after production completion are excluded. A current download gap
and generic workbench failure are merged. The legal-continue flag alone never
means an operator should click. Fresh source/scan age, blocked state, retry
eligibility, no active recovery or task operation and no cloud in-flight command
are required. Login failures ask for login, not safe continue. A failure carries
its manual-review hint rather than generating a second notification.

Production completion requires the batch's immutable completed_verified receipt,
matching positive planned/completed project and video counts, receipt hash and
dated evidence. It never claims that subsequent upload is complete.

The cloud heartbeat uses its existing monotonic-derived receipt clock. UI's
45-second online threshold is distinct from the five-minute offline notice.
An online agent with an unavailable engine for over a minute is a separate event;
the current merged health cannot reliably isolate Dashboard from receiver, and
the message states that limitation. A busy collector is not offline. Future clock
values do not create offline/freshness proof.

The ledger persists baseline time, source versions, error episodes/rounds,
all event keys, first/last observed times, merged delivery IDs and channel receipt
metadata. First enable baselines existing problems; historical receipt backfill
does not push old completions. Restarts/out-of-order responses cannot reset the
baseline. After genuine recovery, a repeated failure becomes a new episode.
Ten-minute same-type windows retain all distinct keys, including different tasks
and attempts. Deferred quiet-hour events remain pending for the morning; critical
connectivity notices may pass quiet hours.

External delivery intent is durable before calling a provider. A timeout or crash
may have delivered already; it is recorded unknown and never blindly repeated.
There is no exactly-once external-delivery promise. Provider rejection/unknown
states will be visible for operator handling; secrets and raw provider errors
must never enter delivery metadata.

Core unit/snapshot tests use temporary databases and fake senders. Provider,
protected interactive setup, authenticated status page, cloud backup/deployment,
real phone receipt and simulated offline acceptance remain to implement/verify.
M2b is not complete; do not deploy or claim real phone acceptance yet.
