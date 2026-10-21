"""Read-only audit of passive evidence. Never upgrades passive data to real shadow."""
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from agent.core.snapshot import canonical, safe_facts, no_links

MAX_SAMPLE = 8 * 1024 * 1024
MAX_OBJECT = 64 * 1024 * 1024
MAX_FILES = 10000
MAX_SAMPLES = 3000
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MISSING = ["aligned filesystem/process/external-source facts", "offline candidate replay", "complete triggered batch coverage", "capture-time source/profile identity"]


def load_bounded(path, maximum):
    path = no_links(path)
    before = path.stat()
    if before.st_size > maximum:
        raise ValueError("evidence_size_limit")
    with path.open("rb") as stream:
        body = stream.read(maximum + 1)
    after = path.stat()
    if (len(body) > maximum or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns):
        raise ValueError("evidence_changed_or_oversized")
    return body


def source_identity(source):
    # Match the source-text identity used by the existing frozen oracle.
    text = load_bounded(source, 2 * 1024 * 1024).decode("utf-8-sig").replace("\r\n", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def audit_passive(root, batch_id, *, since=None, until=None, source=None, expected_source=None, budget_seconds=30):
    if not 0 < budget_seconds <= 120: raise ValueError("invalid_audit_budget")
    started = time.monotonic()
    root = no_links(root)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", batch_id):
        raise ValueError("invalid_batch_identity")
    def timestamp(value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError("explicit_timezone_required")
        return parsed
    start = timestamp(since) if since else None
    finish = timestamp(until) if until else None
    if start and finish and start > finish:
        raise ValueError("invalid_time_window")
    candidates = sorted(no_links(root / "samples").glob("*.json"))
    if len(candidates) > MAX_SAMPLES:
        raise ValueError("sample_count_limit")
    counts = Counter(); errors = Counter(); observed = {}; objects = {}; used = 0
    first = last = None
    budget_hit = False
    for sample_path in candidates:
        if time.monotonic() - started >= budget_seconds:
            budget_hit = True; break
        try:
            sample = json.loads(load_bounded(sample_path, MAX_SAMPLE).decode("utf-8-sig"))
            safe_facts(sample)
            when = timestamp(sample["observedAt"])
            if (start and when < start) or (finish and when > finish):
                continue
            if sample.get("schema") != 1 or sample.get("mode") != "passive-evidence":
                raise ValueError("unexpected_sample_schema")
            records = sample.get("files")
            if not isinstance(records, list) or len(records) > MAX_FILES:
                raise ValueError("invalid_sample_inventory")
            if sample.get("productionWrites") is not False or sample.get("businessRequests") != 0:
                raise ValueError("capture_side_effects_unverified")
            counts["samples"] += 1
            first = when if first is None else min(first, when)
            last = when if last is None else max(last, when)
            if sample.get("budgetHit"): counts["budgetTruncatedSamples"] += 1
            if sample.get("quotaExhausted"): counts["quotaTruncatedSamples"] += 1
            capture_errors = sample.get("errorCounts", {})
            if not isinstance(capture_errors, dict): raise ValueError("invalid_capture_errors")
            for kind, amount in capture_errors.items():
                if type(amount) is not int or amount < 0: raise ValueError("invalid_error_count")
                # Report codes only: never preserve arbitrary source messages.
                errors["capture_input_errors"] += amount
            seen = set()
            for row in records:
                if time.monotonic() - started >= budget_seconds:
                    budget_hit = True; break
                if not isinstance(row, dict): raise ValueError("invalid_object_reference")
                digest = row.get("sha256", "")
                size = row.get("bytes")
                if not re.fullmatch(r"[0-9a-f]{64}", digest) or type(size) is not int or not 0 <= size <= MAX_OBJECT:
                    raise ValueError("invalid_object_reference")
                key = (row.get("root"), row.get("relative"))
                if not all(isinstance(v,str) and v for v in key) or key in seen:
                    raise ValueError("ambiguous_object_reference")
                seen.add(key)
                if digest not in objects:
                    if used + size > MAX_TOTAL: raise ValueError("audit_total_size_limit")
                    body = load_bounded(root / "objects" / digest, MAX_OBJECT)
                    if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
                        raise ValueError("object_hash_mismatch")
                    value = json.loads(body.decode("utf-8-sig")); safe_facts(value)
                    members = {}
                    def walk(node):
                        if isinstance(node, dict):
                            if any(re.search(r"token|secret|password|webhook|authorization|cookie|api.?key",str(k),re.I) for k in node):
                                raise ValueError("private_field_forbidden")
                            # Exact parent membership only; a date/filename is insufficient.
                            if node.get("batchId") == batch_id and node.get("taskId"):
                                task = node["taskId"]
                                if isinstance(task,str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}",task):
                                    members[task] = {k:node[k] for k in ("pipelineStatus","status","expectedCount","completed","failed") if k in node and (type(node[k]) in (int,bool) or isinstance(node[k],str) and re.fullmatch(r"[A-Za-z0-9_.:-]{0,80}",node[k]))}
                            for child in node.values():walk(child)
                        elif isinstance(node,list):
                            for child in node:walk(child)
                    walk(value)
                    # Cache only bounded identity labels, never entire recorded payloads.
                    objects[digest] = (size, members); used += size
                size_saved, members = objects[digest]
                if size_saved != size: raise ValueError("object_size_conflict")
                observed.update(members)

        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            errors["invalid_or_unreadable_sample"] += 1
    blockers = list(MISSING)
    if budget_hit: blockers.append("audit_time_budget_reached")
    if not counts["samples"]: blockers.append("no_samples_in_window")
    if not observed: blockers.append("batch_not_observed")
    if errors: blockers.append("capture_errors_or_invalid_evidence")
    if counts["budgetTruncatedSamples"] or counts["quotaTruncatedSamples"]:
        blockers.append("capture_truncated")
    deployed = source_identity(source) if source else None
    if source and (not expected_source or deployed != expected_source):
        blockers.append("production_source_not_candidate_baseline")
    return {"schema":1,"mode":"passive-audit","batchId":batch_id,
            "firstObservation":first.isoformat() if first else None,
            "lastObservation":last.isoformat() if last else None,
            "counts":dict(counts),"errors":dict(errors),"auditBudgetHit":budget_hit,
            "elapsedSeconds":round(time.monotonic()-started,3),"verifiedObjectCount":len(objects),
            "verifiedObjectBytes":used,"observedProjects":observed,
            "productionSourceSha256":deployed,"expectedSourceSha256":expected_source,
            "blockers":blockers,"comparable":False,"realShadowPassed":False,
            "switchAccepted":False,"productionWrites":False,"businessRequests":0,
            "note":"Observed labels are inventory, not independently verified completion. Current source inspection does not prove capture-time source identity."}
