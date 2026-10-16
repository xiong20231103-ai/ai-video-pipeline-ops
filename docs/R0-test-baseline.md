# R0 isolated test baseline

Base: H4-merged main 6292acc6c206b17ec62f7e2e88eaef8b37b7ac9b.

The unchanged baseline has 79 tests and 7 errors: six missing shared recovery
module fixtures and one None access when the optional local project-status file
is absent. The new tests follow the existing enqueue-only contract: Dashboard
submits independent requests; only the workbench may deliver/retire its mailbox.
The recovery fixture is a test double, not a substitute production authority or
proof of workbench recovery budgets. Cross-repository recovery integration must
be tested separately before a production switch. No test was skipped or marked
expected-failure. Two negative adapter cases cover a missing shared module and
a conflicting request identity.

The only runtime change is treating a missing/non-object local status as an empty
optional overlay; a trusted reconciled receiver snapshot remains authoritative.

Run from this worktree using Python 3.12:

```powershell
python -m pip install --target .test-deps -r requirements.txt
python -B tools/run_isolated_tests.py
```

The runner substitutes all configured production roots before import, prevents
production network/bind/process execution, and audits writes/SQLite to permit
only this checkout and temporary directories. It never starts FastAPI lifespan
or the collector. Direct unittest discovery without this guard is not the
recommended acceptance command because the shipped production config has real
paths. Dependency and runtime files are ignored by Git.

Acceptance is isolated unit coverage only; no home deployment, process restart,
live API invocation or production batch was performed. Claude handles merge and
deployment. Rollback after an approved future deployment: revert this PR using
the normal idle-window workflow; this PR requires no schema migration.
