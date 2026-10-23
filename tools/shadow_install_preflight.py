"""Read-only installation preflight. Never enables, installs or imports live app.

The result is a review artifact, not an approval token. Missing facts and prior
production are explicitly ineligible for a complete-batch shadow verdict.
"""
from pathlib import Path
import argparse
import hashlib
import json

from agent.core.snapshot import canonical, no_links
from agent.core.source_profiles import PROFILES, read_source
from tools.shadow_agent_observer import AgentReadObserver
from tools.shadow_capture import CaptureError, validate_plan, _source, measure_directory_stability

MAX_STORE = 2 * 1024 * 1024 * 1024


def preflight(plan, source, evidence_root, archived_root, *, approved_bytes,
              max_capture_bytes, routes, batch_started_before_capture):
    """Inspect explicit paths and source bytes only; no path discovery or mkdir."""
    if (type(approved_bytes) is not int or not 1 <= approved_bytes <= MAX_STORE
            or type(max_capture_bytes) is not int or max_capture_bytes < 1
            or type(batch_started_before_capture) is not bool):
        raise CaptureError('preflight_limits_invalid')
    source = no_links(source)
    evidence = no_links(evidence_root)
    archive = no_links(archived_root)
    if (evidence == archive or evidence.is_relative_to(archive)
            or archive.is_relative_to(evidence)):
        raise CaptureError('archive_must_remain_separate')
    roots, bindings = validate_plan(plan, evidence / '_preflight_only')
    exclusions=[_source(roots,spec) for spec in plan.get('exclude',{}).values()]
    for root in [source.parent, *roots.values()]:
        if evidence == root or evidence.is_relative_to(root) or root.is_relative_to(evidence):
            if not any(evidence.is_relative_to(p) for p in exclusions):raise CaptureError('preflight_output_source_overlap')
        if archive == root or archive.is_relative_to(root) or root.is_relative_to(archive):
            if not any(archive==p or archive.is_relative_to(p) for p in exclusions):raise CaptureError('archive_not_capture_input')
    if source.stat().st_size > 2 * 1024 * 1024:
        raise CaptureError('preflight_source_limit')
    source_hash = hashlib.sha256(read_source(source).encode()).hexdigest()
    if source_hash not in PROFILES:
        raise CaptureError('unreviewed_capture_source')
    if not isinstance(routes, list) or not routes or len(routes) > 16:
        raise CaptureError('preflight_routes_required')
    ports = {}
    urls = set()
    from urllib.parse import urlsplit
    for row in routes:
        if set(row) != {'url', 'port', 'path', 'key'}:
            raise CaptureError('preflight_route_shape')
        parsed = urlsplit(row['url'])
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.port != row['port'] or parsed.path != row['path']
                or row['url'] in urls or (row['port'], row['path']) in ports):
            raise CaptureError('preflight_route_mismatch')
        if row['port'] == 18790 and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise CaptureError('preflight_control_not_loopback')
        ports[(row['port'], row['path'])] = row['key']
        urls.add(row['url'])
    AgentReadObserver(ports)
    blockers = []
    if {8765, 8766, 18790} - {port for port, _ in ports}:
        blockers.append('three_port_coverage_missing')
    # Root aliases may map a drive, but recursive metadata capture of an entire
    # drive is never accepted. Exact approved date/subtree bindings are required.
    for name in plan.get('trees', {}):
        path = bindings[name]
        if path == Path(path.anchor):
            blockers.append('recursive_drive_inventory_forbidden')
    total = 0
    absent = 0
    for name in plan.get('files', {}):
        path = bindings[name]
        if not path.is_file():
            blockers.append('required_state_file_missing')
        else:
            total += path.stat().st_size
    for name in plan.get('databases', {}):
        path = bindings[name]
        if not path.is_file():
            blockers.append('required_database_missing')
        for suffix in ('', '-wal'):
            part = no_links(str(path) + suffix)
            if part.is_file():
                total += part.stat().st_size
    for name in plan.get('absent', {}):
        if bindings[name].exists():
            blockers.append('declared_absence_now_exists')
        else:
            absent += 1
    if total > max_capture_bytes:
        blockers.append('capture_input_exceeds_cycle_limit')
    reserve = 6 * max_capture_bytes + 16 * 1024 * 1024
    if reserve >= approved_bytes:
        blockers.append('capture_scratch_reserve_exceeds_store_limit')
    directory_stability=measure_directory_stability(plan,evidence/'_directory_preflight_only')
    if directory_stability['unmeasurableRounds']:blockers.append('directory_stability_unmeasurable')
    if directory_stability['directoryChangeFailedRounds']:blockers.append('directory_stability_requires_review')
    blockers = sorted(set(blockers))
    return {'schema': 1, 'sourceSha256': source_hash,
            'planSha256': hashlib.sha256(canonical(plan)).hexdigest(),
            'technicalPreflight': 'blocked' if blockers else 'ready-for-review',
            'blockers': blockers, 'stateAndDatabaseBytes': total,
            'maxCaptureBytes': max_capture_bytes, 'captureReserveBytes': reserve,
            'approvedNewStoreBytes': approved_bytes, 'oldStoreIncludedInNewQuota': False,
            'explicitAbsentPathCount': absent,
            'directoryStability':directory_stability,
            'batchCoverage': 'resume-segment-only' if batch_started_before_capture else 'start-not-yet-observed',
            'completeBatchEligible': False, 'dependencyClosureVerified': False,
            'installationPermitted': False, 'reviewRequired': True,
            'enabled': False, 'businessRequests': 0, 'productionWrites': False,
            'realShadowPassed': False, 'switchAccepted': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path = no_links(args.spec)
        if path.stat().st_size > 1024 * 1024:
            raise CaptureError('preflight_spec_limit')
        spec = json.loads(path.read_text(encoding='utf-8-sig'))
        result = preflight(spec['capturePlan'], spec['source'], spec['evidenceRoot'], spec['archivedRoot'],
                           approved_bytes=spec['approvedBytes'], max_capture_bytes=spec['maxCaptureBytes'],
                           routes=spec['routes'], batch_started_before_capture=spec['batchStartedBeforeCapture'])
        print(json.dumps(result, ensure_ascii=True))
        return 1 if result['blockers'] else 0
    except Exception:
        print('{"technicalPreflight":"blocked","code":"shadow_preflight_rejected","installationPermitted":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
