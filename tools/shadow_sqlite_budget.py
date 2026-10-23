"""Synthetic online-backup/chunk budget experiment; never opens production DBs."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import time
from contextlib import closing

CHUNK = 64 * 1024


def experiment(scratch_parent, *, target_bytes=132419584, rounds=8):
    if not 1 <= target_bytes <= 192*1024*1024 or not 4 <= rounds <= 16:
        raise ValueError('synthetic_budget_limits')
    with tempfile.TemporaryDirectory(prefix='shadow-budget-', dir=scratch_parent) as folder:
        root = Path(folder)
        db = root/'synthetic.db'
        rng = random.Random(20261023)
        with closing(sqlite3.connect(db)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, payload TEXT, state INTEGER)')
            rows = max(1, target_bytes//8256)
            writer.executemany('INSERT INTO events VALUES(?,?,0)',
                               ((n, rng.randbytes(4096).hex()) for n in range(rows)))
            writer.commit()
            writer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            size = db.stat().st_size
            seen = set()
            samples = []
            for index in range(rounds):
                # 1/8/32 updated records: explicit measured workload scenarios.
                changed = 0 if index == 0 else (1, 8, 32)[(index-1)%3]
                for _ in range(changed):
                    writer.execute('UPDATE events SET state=state+1 WHERE id=?', (rng.randrange(rows),))
                writer.commit()
                target = root/'backup.db'
                started = time.perf_counter()
                with closing(sqlite3.connect(db.as_uri()+'?mode=ro', uri=True)) as reader, \
                        closing(sqlite3.connect(target)) as output:
                    reader.backup(output, pages=128, sleep=0.001)
                backup_seconds = time.perf_counter()-started
                hashes = []
                fresh = 0
                with target.open('rb') as stream:
                    for body in iter(lambda: stream.read(CHUNK), b''):
                        key = hashlib.sha256(body).hexdigest()
                        hashes.append(key)
                        if key not in seen:
                            seen.add(key)
                            fresh += len(body)
                # Actual block-index JSON bytes. Other filesystem/process facts
                # are a separately labelled allowance, never called measured.
                index_bytes = len(json.dumps(hashes, separators=(',', ':')).encode())
                samples.append({'changedRows': changed, 'backupSeconds': round(backup_seconds, 4),
                                'newChunkBytes': fresh, 'indexBytes': index_bytes,
                                'retainedBytes': fresh+index_bytes})
                target.unlink()
            event_snapshots = 78*8 + 8*4 + 72
            allowance = 256*1024  # explicit unmeasured per-snapshot fact/report allowance
            steady = samples[1:]
            forecasts = []
            for changed in (1, 8, 32):
                group = [row for row in steady if row['changedRows'] == changed]
                per_round = max(row['retainedBytes'] for row in group)
                total = samples[0]['retainedBytes'] + event_snapshots*(per_round+allowance)
                forecasts.append({'changedRowsPerSnapshot': changed, 'perRoundMeasuredMaxBytes': per_round,
                                  'forecast12hBytes': total, 'fitsCaptureBudget': total <= 1536*1024*1024})
    return {'schema': 1, 'kind': 'synthetic-measurement-not-production-preflight',
            'syntheticDatabaseBytes': size, 'chunkBytes': CHUNK, 'measuredRounds': samples,
            'assumptions': {'remainingInputItems': 78, 'phaseChangesPerItem': 8,
                            'inboxAndCommandEvents': 32, 'periodicSnapshots': 72,
                            'forecastSnapshotsAfterBaseline': event_snapshots,
                            'unmeasuredFactAllowancePerRound': allowance},
            'forecastScenarios': forecasts, 'captureBudgetBytes': 1536*1024*1024,
            'scratchAndReplayReserveBytes': 512*1024*1024,
            'productionBudgetVerified': False, 'installationPermitted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch-parent', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = experiment(args.scratch_parent)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(json.dumps({'kind': result['kind'], 'rounds': len(result['measuredRounds']),
                      'productionBudgetVerified': False, 'installationPermitted': False}))


if __name__ == '__main__':
    main()
