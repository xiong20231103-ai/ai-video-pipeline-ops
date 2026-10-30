# PiP status projection candidate

The additive collection adapter supplies a public allowlist containing mode, online state, child session and recent heartbeat. Request nonces, filesystem paths and client identities are excluded. A stale Workbench or executor produces an offline notice; the display never promises automatic main-session fallback. The pinned legacy collector body is unchanged.

Validation: 239 frontend tests passed in one run; typecheck, lint and build passed. Five pure status tests passed. Seven isolated collector/provenance tests passed on the host; the sandbox rerun failed because atomic directory rename was denied, and that environmental failure was not relabeled as passing.

Actual Workbench/executor/Dashboard live end-to-end acceptance and deployment remain pending. Main mode retains the existing screen-use warning. Rollback restores the prior collector adapter and matching built frontend assets as one deployment.
