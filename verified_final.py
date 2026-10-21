"""Read-only reconciliation of stale maintenance failures with verified finals."""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=128)
def _digest(path, size, modified, changed):
    # Stat identity is part of the key; never reuse a hash after a file changes.
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def released_final_verified(metadata):
    """Fail closed: a production flag or a non-empty MP4 alone is insufficient."""
    if (metadata.get("productionStatus") != "completed"
            or metadata.get("draftReleaseStatus") != "released"
            or metadata.get("qualityStatus") != "passed"):
        return False
    try:
        report_path = metadata.get("qualityReportPath")
        output_path = metadata.get("finalOutputPath")
        if not report_path or not output_path:
            return False
        report = json.loads(Path(report_path).read_text(encoding="utf-8-sig"))
        output = Path(output_path)
        owner = metadata.get("remotePipelineTaskId")
        if (not isinstance(report, dict) or report.get("status") != "passed"
                or not metadata.get("taskId") or not owner
                or report.get("taskId") != metadata["taskId"]
                or report.get("canonicalTaskId") != owner
                or report.get("fileName") != output.name):
            return False
        digest = str(report.get("sha256") or "").lower()
        size = report.get("fileSize")
        if (not re.fullmatch(r"[0-9a-f]{64}", digest)
                or type(size) is not int or size <= 0 or not output.is_file()):
            return False
        before = output.stat()
        if before.st_size != size:
            return False
        actual = _digest(str(output.resolve()), size, before.st_mtime_ns, before.st_ctime_ns)
        after = output.stat()
        return (actual == digest and before.st_size == after.st_size
                and before.st_mtime_ns == after.st_mtime_ns
                and before.st_ctime_ns == after.st_ctime_ns)
    except (OSError, ValueError, TypeError):
        return False
