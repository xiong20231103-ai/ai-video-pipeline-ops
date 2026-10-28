"""Cloud-only handoff/regression selection using the existing strict I/O runner."""
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
if Path.cwd().resolve()!=root:
    raise SystemExit('Run from the isolated repository root')
sys.dont_write_bytecode=True
# Avoid Argon2's Windows `cmd /c ver` probe; no app/credential config is loaded.
with patch('platform.machine',return_value='AMD64'):
    import argon2
os.environ['OPS_ISOLATED_TEST_FILES']=','.join([
    'test_material_handoff.py','test_material_handoff_prune.py','test_cloud_readonly.py','test_command_routes.py',
    'test_command_queue.py','test_backup_routes.py','test_backup_vault.py',
    'test_link_evidence.py','test_notification_runtime.py','test_public_docs_boundary.py'])
sys.argv=[str(root/'tools/run_isolated_tests.py')]
runpy.run_path(str(root/'tools/run_isolated_tests.py'),run_name='__main__')
