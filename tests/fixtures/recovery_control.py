"""Test double for the shared RecoveryControl enqueue-only transport contract.

This is not the production recovery engine. Dashboard unit tests check durable
independent requests and no mailbox mutation; recovery budgets/delivery are
owned and integration-tested by the workbench repository.
"""
import json
from pathlib import Path

class RecoveryControlError(RuntimeError):
    pass

class RecoveryControl:
    def __init__(self, state_path, lock_path, mailbox_path):
        self.state_path = Path(state_path)

    def enqueue_request(self, request):
        command_id = str(request.get('commandId') or '')
        if not command_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in command_id):
            raise RecoveryControlError('invalid request id')
        path = self.state_path.parent / 'recovery-requests' / (command_id + '.json')
        if path.exists():
            old = json.loads(path.read_text(encoding='utf-8'))
            if any(old.get(k) != request.get(k) for k in ('taskId', 'runGroupId', 'batchId')):
                raise RecoveryControlError('request target changed')
            return old
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**request, 'state': 'requested'}
        path.write_text(json.dumps(payload), encoding='utf-8')
        return payload
