# Mutable final-output verification and the frozen baseline

PR #53's Windows CI run 39757339984 failed
`test_changed_bytes_invalidate_cached_digest`; the sibling push run passed.
The mutable helper cached SHA256 by path, size, mtime and ctime. Those fields can
remain unchanged for a rapid same-size overwrite. Windows ctime may represent
creation time. This is a verification defect, not a test to skip or slow down.

The candidate now reads current bytes for every verification and also compares
file device/inode before and after hashing. Tests explicitly hold stat metadata
constant while changing the bytes, so the regression is deterministic and does
not depend on runner timing. No sleep or forced timestamp advancement hides it.

Tradeoff for Claude: repeated verification reads the full final file again and
can cost substantial I/O on large batches. This change is **not deployed**.
Any future optimization needs a trustworthy immutable/versioned source and must
pass the identical-stat mutation test; stat-keyed reuse is not sufficient.

The deployed PR49 helper is retained byte-for-byte (normalized UTF-8 line endings)
in `contracts/legacy-verified-final-pr49.txt`, pinned to the existing SHA256
`69b8b086e0502c506e75f1644fe2a3d28c8bac94c99c2b54870c2205fb9199e0`.
The isolated Oracle loads that exact helper under an exit-stack-scoped module
binding; it restores the ordinary candidate module on exit. Old replay must not
silently inherit today's fix. Capture proof containing the new candidate helper
is rejected as the old deployed PR49 profile. A future deployment therefore also
requires explicit reviewed source-profile registration before real shadow capture.

No production data, process, configuration, cleanup setting or recovery request
was changed. This is a source/CI fix awaiting review, not a deployment instruction.
