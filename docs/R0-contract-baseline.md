# Lightweight R0 contract baseline

This PR depends on the separate R0 test repair PR #11. It does not deploy an
agent, change production collection, issue a live API request, or implement
second-step R4/R5 production replacements.

contracts/endpoints.json is the complete API route/query inventory from the
fixed Dashboard source, plus receiver submission routes. Every GET is classified
as first-screen, periodic, after-operation or on-demand. Recent-14-day offline
coverage means keys actually cached, never a promise of all uncached pages.
The full Dashboard requires a low-frequency refresh even if summary is unchanged;
templates and event/history/cleanup status do not depend only on summary changes.
The receiver health adapter must preserve formalBatchTotal/projectTotals/
contractVersion. Cloud testing/reset is explicitly forbidden.

Cache identity includes method, canonical relative path, and every effective
scalar query parameter. Duplicate scalar values follow FastAPI's last-value
selection. Unknown queries/path traversal/absolute URLs are refused. Hash
normalization ignores only explicit outer /updatedAt and /metrics/time; nested
business heartbeat, expiry, identity, receipt hashes and array order are retained.
Transport metadata (success/change/source scan/source health and persistent
versions) is required in M1a; a semantic hash alone is not freshness evidence.

The lightweight frozen golden tier currently covers the ORIGINAL receiver
normalizer with 16 synthetic cases, controlled HTTP/file/empty-SQLite input,
clock/timezone, empty directory/process fixtures and fixed metrics. No real
customer state, credential, video or production database is copied. Fixture
outputs are strict JSON, with no ignored fields. The late-manifest case freezes
current behavior; it is not a statement that late data is inherently safe.

This is a named adapter tier, not full Dashboard/collector or R4/R5 shadow
acceptance. The remaining source fixtures (full databases, logs, leases, directory
stat/process identity, control-plane responses) must be added before optimizing
those readers in H1 or replacing them in second-step R0/R1. The 81 existing
isolated OPS tests remain part of every acceptance run.

Run: python -B tools/run_isolated_tests.py (after installing requirements into
.test-deps). OPS_WRITE_GOLDEN=fixture-receiver-only explicitly regenerates this
adapter tier under the same production I/O guard. Regeneration is a reviewable
baseline change; never auto-regenerate expected files in CI to hide differences.

Golden comparison uses exact JSON pointers. Wildcard exclusions are refused,
arrays remain ordered, booleans and integers are distinct, and shadow windows
with different source identities are not eligible to count as zero-difference.
Real read/write shadow runs require explicit source-version alignment, an isolated
write sink, no duplicate production execution, and a full batch before switching.

Acceptance: isolated unit/fixture replay only; no live shadow batch performed.
Rollback: revert this PR; no runtime database or deployed services are changed.


The future shadow checklist imports all 77 review rules with original source
locations: R4-01..30, RC-01..12, R5-01..06, R5-D01..08, R5-A01..08 and
R5-P01..13. D08 is included even though the user's abbreviated list ended at D07.
All real-shadow statuses start NOT RUN, caseCount=0, mismatchCount=null. An empty
or simulated zero-difference result cannot authorize switching. Full-batch and
aligned source-identity evidence is mandatory. This is a checklist/gate framework,
not implementation of R4; user approval remains required before R4 or R6 work.
