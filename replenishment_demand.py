"""Read-only admission evidence for company clients; never changes task counts."""


def annotate_gaps(items, payload):
    valid = (isinstance(payload, dict) and not payload.get("error")
             and isinstance(payload.get("items"), list))
    queue = payload["items"] if valid else []
    out = []
    for original in items:
        gap = dict(original)
        missing = gap.get("missingCount")
        if not valid or type(missing) is not int or missing < 0:
            gap.update(replenishmentDemandState="unknown")
            out.append(gap)
            continue
        links = set()
        seen = set()
        unsettled = False
        for child in queue:
            if not isinstance(child, dict):
                continue
            tid = child.get("taskId")
            if not isinstance(tid, str) or not tid or tid in seen:
                continue
            if (not gap.get("taskId") or child.get("replenishForTaskId") != gap["taskId"]
                    or child.get("canonicalTaskId") != gap["taskId"]
                    or str(child.get("date") or child.get("productionDate") or "")
                    != str(gap.get("date") or gap.get("productionDate") or "")
                    or child.get("project") != gap.get("project")
                    or child.get("material") != gap.get("material")):
                continue
            if child.get("status") != "pending_confirmation":
                # Imported/active task files alone do not prove how many usable
                # downloads remain. Suspend instead of treating them as absent.
                if child.get("status") not in {"failed", "cancelled", "canceled", "merged_into_parent", "completed", "uploaded"}:
                    unsettled = True
                continue
            seen.add(tid)
            urls = child.get("urls")
            if isinstance(urls, list):
                links.update(url.strip() for url in urls if isinstance(url, str) and url.strip())
        if unsettled and missing:
            gap.update(replenishmentDemandState="unknown")
            out.append(gap)
            continue
        received = min(missing, len(links))
        gap.update(replenishmentDemandState="known", replenishmentQueuedCount=received,
                   replenishmentAdditionalNeeded=max(0, missing - received))
        out.append(gap)
    return out
