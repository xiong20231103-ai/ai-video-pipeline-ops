"""Read-only public prefetch projection. Never exports paths, tokens or URLs."""
import hashlib
import json
import re
from pathlib import Path


def read_object(path):
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def original_hash(task):
    fields = ("taskId", "canonicalTaskId", "batchId", "runGroupId", "batchSequence",
              "date", "productionDate", "project", "material", "expectedCount", "urls")
    value = {key: task.get(key) for key in fields}
    value["urls"] = task.get("prefetchOriginalUrls", task.get("urls"))
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def public_views(workbench_dir, tasks):
    """Match explicit queue contracts; do not discover arbitrary task identities."""
    root = Path(workbench_dir) / "handoff"
    directory = root / "download" / "prefetch"
    result = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        tid = str(task.get("taskId") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", tid):
            continue
        if (str(task.get("pipelineStatus") or "waiting") not in {"", "waiting"}
                or task.get("status") in {"running", "completed", "cancelled", "canceled"}):
            continue
        state = read_object(directory / f"{tid}.json")
        if (state.get("taskId") != tid or not task.get("batchId")
                or state.get("batchId") != task.get("batchId")
                or state.get("state") not in {"running", "interrupted", "finished"}):
            continue
        total, done = state.get("urlCount"), state.get("completedOutputs", 0)
        if (type(total) is not int or type(done) is not int or not 0 <= done <= total
                or total != task.get("expectedCount") or total <= 0):
            continue
        failures = state.get("failedLinks") or []
        if (not isinstance(failures, list) or any(not isinstance(item, dict)
                or not isinstance(item.get("url"), str) or not item["url"] for item in failures)):
            continue
        failed = {item["url"] for item in failures if isinstance(item, dict) and isinstance(item.get("url"), str)}
        if len(failed) != len(failures) or len(failed) > total - done:
            continue
        accepted = set()
        plan = read_object(directory / f"{tid}.replacements.json")
        for folder in ("pending", "imported"):
            contract = read_object(root / "task_inbox" / folder / f"{tid}.json")
            replacements = plan.get("replacements")
            if (contract.get("taskId") == tid and contract.get("batchId") == task["batchId"]
                    and plan.get("schemaVersion") == 1 and plan.get("taskId") == tid
                    and plan.get("contractHash") == original_hash(contract)
                    and isinstance(replacements, dict) and set(replacements).issubset(failed)
                    and all(isinstance(url, str) and url for url in replacements.values())
                    and len(set(replacements.values())) == len(replacements)):
                accepted = set(replacements)
                break
        missing = failed - accepted
        # Hash includes gap membership, not timestamps/count alone. URLs never
        # leave this projection, but identical gaps have stable notification IDs.
        fingerprint = hashlib.sha256(json.dumps(sorted(missing), ensure_ascii=False).encode()).hexdigest()
        result.append({"taskId": tid, "batchId": task["batchId"],
                       "productionDate": str(task.get("productionDate") or task.get("date") or ""),
                       "sequence": task.get("batchSequence"), "project": str(task.get("project") or ""),
                       "material": str(task.get("material") or ""), "state": state["state"],
                       "completed": done, "total": total, "missingCount": len(missing),
                       "acceptedPending": len(accepted), "gapFingerprint": fingerprint,
                       "canReplenish": state["state"] == "finished" and bool(missing)})
    return result
