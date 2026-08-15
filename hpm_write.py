"""NEDA's one write capability into BMC Helix Portfolio Management (HPM) —
deliberately narrow, added 2026-08-14 per explicit user instruction ("teach
NEDA how to create tasks and everything you know about HPM"). Scoped to
exactly one thing: creating a new Project Task under the existing "BMC Helix
26.3 Rollout" project. Everything else about HPM stays read-only via
hpm_readonly.py — no creating/editing Projects, Teams, People, or Root
Status/Root Status Reason records (the reference doc this was built from,
reference_hpm_agility_suite_api.md, documents Root Status/Root Status Reason
as a confirmed hard backend read-only block — don't attempt those), no
deletes, no other project. This mirrors the same "narrow, deliberate
exception to an otherwise read-only tool" pattern as smc_tools.py and
self_tools.py.

Reuses hpm_readonly.py's auth (same JWT token cache, same demo creds) and
KNOWN_PEOPLE GUID map rather than duplicating either.

Known gotchas baked into this module (see reference_hpm_agility_suite_api.md
for the fuller writeup — this is the condensed, load-bearing subset):
- queryExpression filtering on Summary (char field) or PROJECT_ID (a reference
  field that, contrary to the general "reference fields filter fine" rule,
  also throws messageNumber 313 for this specific field) both fail server-side
  — every lookup here fetches a broad page and filters client-side in Python,
  same workaround hpm_readonly.py already uses.
- A child task's Start Date must be >= its DIRECT PARENT's own Start Date (not
  just the project's) or create fails with messageNumber 22010. This module
  looks up the parent's real dates first and defaults to them rather than
  guessing, so a caller that omits start_date/end_date still gets a valid task.
- A 201 create response can have an empty body — the new record's real ID
  isn't parsed from the create response, this module re-queries by summary
  afterward to confirm the task actually landed and to get its display number.
"""
import json
import urllib.error
import urllib.request

from hpm_readonly import _get_token, _get, _SSLCTX, HOST, KNOWN_PEOPLE, GUID_TO_NAME

PROJECT_NAME = "BMC Helix 26.3 Rollout"
PROJECT_ID = "AGGJ1NVGIL0UFAT8XPE0T8XPE0P23U"
REQUESTER = "AGGJ1NVGIL0UFAT8XRS3T8XRS3RX2F"  # project's own Requester, reused per the documented pattern
ROOT_TYPE_PROJECT_TASK = "AGGIOAYNIADW4AQ0ZQ0BQ0BMZ936OK"
ROOT_STATUS = {
    "backlog": "AGGA4BT2FU4CWAQ16CTZQ07ZOV9UFR",
    "to do": "AGGCLSOKFP8I7AQPN1VJQOOQ3WAQ2W",
}


def _find_task_by_summary(summary_substring: str) -> dict | None:
    """Broad fetch + client-side filter (see module docstring for why a
    server-side queryExpression can't be used here). Returns the first
    Project Task under PROJECT_ID whose Summary contains summary_substring
    (case-insensitive), with its ID, Start Date, End Date — or None."""
    body = {
        "values": {
            "dataPageType": "com.bmc.arsys.rx.application.record.datapage.RecordInstanceDataPageQuery",
            "recorddefinition": "com.fusiongbs.agility:Project Task",
            "pageSize": "500",
            "startIndex": "0",
            "propertySelection": "8,1,379,536875002,536872155,536875009,536875010",
            "sortBy": "-1",
        }
    }
    result = _get("/api/rx/application/datapage", body)
    needle = summary_substring.strip().lower()
    for r in result.get("data", []):
        if r.get("536872155") != PROJECT_ID:
            continue
        summary = (r.get("8") or "")
        if needle in summary.lower():
            return {
                # 379 is the real GUID instance ID (confirmed live 2026-08-14 that
                # this works for Project Task too, not just CTM:People as the
                # reference doc originally documented) — must be explicitly listed
                # in propertySelection or it comes back missing. This is what the
                # Parent field (536875002) on a create call actually needs; "1" is
                # only the human-readable display number, never a valid Parent value.
                "id": r.get("379"),
                "summary": summary,
                "task_number": r.get("1"),
                "start_date": r.get("536875009"),
                "end_date": r.get("536875010"),
            }
    return None


def create_hpm_task(summary: str, parent_summary: str, assignee_name: str = "",
                     start_date: str = "", end_date: str = "", root_status: str = "to do") -> dict:
    """Create a new HPM Project Task under the "BMC Helix 26.3 Rollout" project
    — the ONLY write this tool can do. It always creates a Project Task as a
    child of an existing task you name by its summary text; it cannot create a
    new top-level category, a Project, a Team, or a Person, and it cannot
    delete or change the status of anything that already exists.

    Args:
        summary: the new task's title/summary text.
        parent_summary: summary text (or a distinctive substring of it) of the
            EXISTING task this should be created under, e.g. "Platform" or
            "Dashboards & Insight Finder". Looked up by substring match, case-
            insensitive — if this matches nothing, the call fails with a clear
            error rather than guessing.
        assignee_name: optional, e.g. "Digvijay Nikam" — must be one of the
            known team members (see hpm_readonly.KNOWN_PEOPLE); an unrecognized
            name fails with the list of valid names rather than silently
            creating an unassigned task.
        start_date: optional, "YYYY-MM-DD". Defaults to the parent task's own
            Start Date if omitted — required because HPM rejects a child task
            whose Start Date is earlier than its direct parent's.
        end_date: optional, "YYYY-MM-DD". Defaults to the parent task's own End
            Date if omitted, for the same reason (a child's End Date can't be
            later than its parent's).
        root_status: "to do" (default) or "backlog" — the visible Status
            column value for the new task.

    Returns:
        A dict with summary, task_number, parent, assignee, start_date,
        end_date on success — or a dict with just "error" describing exactly
        what went wrong (unknown parent, unknown assignee, or the raw HPM
        error) if the create didn't happen.
    """
    root_status_key = root_status.strip().lower()
    if root_status_key not in ROOT_STATUS:
        return {"error": f"unknown root_status {root_status!r} — must be one of: "
                          f"{', '.join(ROOT_STATUS)}"}

    parent = _find_task_by_summary(parent_summary)
    if not parent:
        return {"error": f"no task under {PROJECT_NAME!r} matches parent_summary "
                          f"{parent_summary!r} — check the exact wording and try a "
                          f"shorter, more distinctive substring."}
    if not parent.get("id"):
        return {"error": f"found parent task {parent['summary']!r} but its real "
                          f"instance ID came back empty — refusing to create with a "
                          f"broken Parent reference."}

    assignee_guid = None
    if assignee_name:
        assignee_guid = KNOWN_PEOPLE.get(assignee_name.strip().lower())
        if not assignee_guid:
            return {"error": f"unknown assignee {assignee_name!r} — known names: "
                              f"{', '.join(sorted(KNOWN_PEOPLE))}"}

    real_start = start_date.strip() if start_date else parent.get("start_date")
    real_end = end_date.strip() if end_date else parent.get("end_date")
    if not real_start or not real_end:
        return {"error": f"parent task {parent['summary']!r} has no Start/End Date on "
                          f"record, and none was given — pass start_date/end_date "
                          f"explicitly."}

    field_instances = {
        "8": {"id": 8, "value": summary},
        "7": {"id": 7, "value": 0},
        "536872155": {"id": 536872155, "value": PROJECT_ID},
        "536875002": {"id": 536875002, "value": parent["id"]},
        "536875008": {"id": 536875008, "value": ROOT_TYPE_PROJECT_TASK},
        "536875004": {"id": 536875004, "value": ROOT_STATUS[root_status_key]},
        "536875017": {"id": 536875017, "value": REQUESTER},
        "536875009": {"id": 536875009, "value": real_start},
        "536875010": {"id": 536875010, "value": real_end},
    }
    if assignee_guid:
        field_instances["536875018"] = {"id": 536875018, "value": assignee_guid}

    token = _get_token()
    req = urllib.request.Request(
        f"{HOST}/api/rx/application/record/recordinstance",
        data=json.dumps({
            "recordDefinitionName": "com.fusiongbs.agility:Project Task",
            "fieldInstances": field_instances,
        }).encode(),
        method="POST",
        headers={
            "Authorization": f"AR-JWT {token}",
            "X-Requested-By": "XMLHttpRequest",
            "default-bundle-scope": "com.fusiongbs.agility-suite",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSLCTX) as r:
            if r.status not in (200, 201):
                return {"error": f"create returned unexpected status {r.status}"}
    except urllib.error.HTTPError as e:
        return {"error": f"create failed: HTTP {e.code} — {e.read().decode()[:500]}"}

    created = _find_task_by_summary(summary)
    if not created:
        return {"error": "create call succeeded (no HTTP error) but the new task "
                          "couldn't be found on re-query — check manually before "
                          "assuming it worked."}
    return {
        "summary": created["summary"],
        "task_number": created["task_number"],
        "parent": parent["summary"],
        "assignee": assignee_name or "unassigned",
        "start_date": real_start,
        "end_date": real_end,
        "root_status": root_status_key,
    }
