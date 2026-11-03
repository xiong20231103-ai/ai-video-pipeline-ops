# Dashboard read-side CPU optimization (not deployed)

Measured first against main on a fixed private production-JSON copy; no live
server, cloud instance, producer, media or production state was changed. The
five-minute replay deliberately excludes metrics/network/GPU and media-directory
walks, so its CPU figures are not claims about the live 95%-of-one-core process.
Exact reports/top-ten functions/commands accompany the combined handoff.

## Read and projection path

- A bounded JSON stat/identity cache returns independent objects. Unchanged
  healthy sources do not repeatedly query source_health. Missing/error diagnostics
  retain the old reader's text, verified by frozen old/new response comparison.
- Metadata walks default to 15 seconds, video download-directory walks to 15,
  generation-directory walks to 30. Existing live state/status paths still run
  every collector pass. Override keys: metadata_scan_interval_seconds,
  download_directory_scan_interval_seconds, generation_directory_scan_interval_seconds.
- Resolve each unique manifest path once per scan, not once per language/attempt.
- Unchanged nonfailed status/metadata sources skip repeated normalization.
  Failed evidence is still checked: current final-byte proof code is untouched.
  Identical normalized projections skip redundant database access.
- Status memo identities belong to the observed read generation. A file replaced
  between read and memo cannot pin old content indefinitely; a behavioral race
  test reproduced that failure before the fix.

## Contract and history

No summary response property was added or removed. Existing contract/frozen
replay tests compare the output, not only return strings. New exact LF/CRLF app
source profiles and two fixed helper hashes are registered; historical profiles
remain accepted and arbitrary/modified source is not dynamically trusted.
Sandbox stat ports gain device/inode fields for immutable offline snapshots.

The archive companion's verified file index is read only for explicit historical
dates. Archived rows do not enter COLLECTOR.metadata, active task admission or
the live SQLite projection. Hash corruption/path escapes fail closed. Archive
indexes themselves use the bounded read cache. Deploy this reader before anyone
uses the companion archival tool.

After review and a future safe rollout, restart the home Dashboard to load the
new code/helpers. Do not overwrite unrelated production modifications. There is
no cloud/API-agent protocol change. If an installed separate shadow/source-
verifying agent consumes these profiles, update its reviewed source-profile/
sandbox modules too and restart that agent in its own safe window; plain existing
GET-body forwarding does not need a restart for response-field changes.
