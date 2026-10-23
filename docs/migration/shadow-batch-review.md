# Offline batch and campaign review

This follow-up to #52 adds a review checklist, not a production acceptance gate.
No service, collector, schedule or production setting is installed or changed.

## Batch input and requirements

`python -B tools/shadow_evidence.py review-batch --input <descriptor.json> --out <new-report.json>`

The explicit descriptor has exactly `reports`, `batchId`, `startedEvidence` and
`completedEvidence`. It contains sanitized producer facts, never credentials.

- Boundary evidence must have the same batch ID, distinct source identities,
  timezone-aware `observedAt` timestamps in increasing order, explicit
  `realBatchEvidence` and `dependencyClosureVerified` claims. Start
  `expectedTaskIds` and end `completeTaskIds` must be nonempty, unique and equal.
- Each R1/R2/R3/R5 comparison needs `observedAt`, `taskIds`, unique
  `observedTriggerIds`, matching old/new source identities, a positive case count,
  zero mismatches, closure and real-evidence claims. Samples outside the boundary
  window, unrelated tasks and repeated snapshots do not count. R1 and R2 must
  cover every expected task. R3/R5 need their actual operations; they need not
  operate on every video. Absent cleanup remains unaccepted.
- R2 additionally requires independent timeline accuracy verification. The #52
  lossless source roundtrip report deliberately does not provide this claim.
- The output records an input SHA256 and a summary identity. Editing a summary
  makes subsequent campaign verification fail. These hashes detect changed input;
  **they do not authenticate authorship or prove live capture**.

## Two-batch campaign

`python -B tools/shadow_evidence.py review-campaign --batch-review <first.json> --batch-review <second.json> --out <new-campaign.json>`

Two reports with the same batch ID or shared snapshot evidence cannot be counted
as two independent batches. All required modules must be ready for review in both
batches. This conservative full-project checklist does not authorize partial
module deployment. R4 has a separate paired workbench transition and is excluded.

Every output retains `realShadowPassed=false` and `switchAccepted=false`.
`readyBatchCount` counts internally consistent submissions for review, while
`acceptedRealBatchCount` stays **0**. Claude must inspect raw immutable sources and
runtime provenance before accepting a real batch; a synthetic JSON descriptor can
never substitute for that review.

## Remaining limitations

The live producer is not yet connected. #52's replay output deliberately lacks
the complete batch context and live proof required here. Do not fill those gaps
by relabeling old passive samples or copying test fields into production reports.
Production runtime integration, complete R3 native tapes, R5 actual-operation
capture, independently verified R2 timelines and two real complete batches remain
pending. No accepted batch count changed as a result of this PR.
