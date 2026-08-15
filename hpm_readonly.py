"""Read-only HPM (BMC Helix Portfolio Management / Agility Suite) API client.

Deliberately READ-ONLY — no PUT/POST/DELETE anywhere in this file. This is the
first phase of giving the local agent tool access: look-but-don't-touch.
"""
import json
import ssl
import time
import urllib.request
import urllib.error
from pathlib import Path

# Corporate TLS-inspection proxy presents a self-signed chain that Python's default
# store rejects, while curl to the same host succeeds (same fix as smc_scanner.py).
_SSLCTX = ssl.create_default_context()
_SSLCTX.check_hostname = False
_SSLCTX.verify_mode = ssl.CERT_NONE

HOST = "https://helixdemoash3701-demo-is.onbmc.com"
TOKEN_CACHE = Path.home() / "local-ai" / ".hpm_token.json"
USERNAME = "Liam"
PASSWORD = "Password_1234"

KNOWN_PEOPLE = {
    "digvijay nikam": "AGGJ1NVGIL0UFAT7NL72T7NL72NIP0",
    "sharvari bhosale": "AGGJ1NVGIL0UFAT7RAHDT7RAHDJ7M0",
    "amol choudhary": "AGGJ1NVGIL0UFAT8XRRRT8XRRRRXH0",
    "abhishek chaturvedi": "AGGJ1NVGIL0UFAT8XRS3T8XRS3RX2F",
    "emil ng": "AGGJ1NVGIL0UFAT8Z02RT8Z02RNNK6",
    "pooja shukla": "AGGJ1NVGIL0UFAT8ZASFT8ZASF8KR9",
}
GUID_TO_NAME = {v: k.title() for k, v in KNOWN_PEOPLE.items()}


def _get_token() -> str:
    if TOKEN_CACHE.exists():
        cached = json.loads(TOKEN_CACHE.read_text())
        if time.time() - cached["fetched_at"] < 50 * 60:  # ~50 min, tokens last ~60
            return cached["token"]
    data = f"username={USERNAME}&password={PASSWORD}".encode()
    req = urllib.request.Request(f"{HOST}/api/jwt/login", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15, context=_SSLCTX) as r:
        token = r.read().decode().strip()
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({"token": token, "fetched_at": time.time()}))
    return token


def _get(path: str, body: dict) -> dict:
    token = _get_token()
    req = urllib.request.Request(
        f"{HOST}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"AR-JWT {token}",
            "X-Requested-By": "XMLHttpRequest",
            "default-bundle-scope": "com.fusiongbs.agility-suite",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30, context=_SSLCTX) as r:
        return json.loads(r.read().decode())


UNSCOPED_TASK_CAP = 25


def query_hpm_tasks(assignee_name: str = "") -> list[dict]:
    """Look up BMC Helix Portfolio Management (HPM) tasks, optionally filtered by
    the person they're assigned to. Read-only — does not modify anything.

    Prefer passing assignee_name whenever the question names or implies a specific
    person — an unscoped call only returns a small sample, not the full task list,
    to avoid flooding context with hundreds of irrelevant rows.

    Args:
        assignee_name: Full name of a person to filter by (e.g. "Digvijay Nikam").
            Leave empty only when you genuinely need a broad, unscoped sample —
            this returns at most 25 tasks in that case, newest first, not the
            complete list.

    Returns:
        A list of dicts, each with task_number, summary, and assignee. When called
        unscoped, the list is capped at 25 and the last element is a note dict
        stating the true total count.
    """
    body = {
        "values": {
            "dataPageType": "com.bmc.arsys.rx.application.record.datapage.RecordInstanceDataPageQuery",
            "recorddefinition": "com.fusiongbs.agility:Project Task",
            "pageSize": "500",
            "startIndex": "0",
            "propertySelection": "8,1,536875018",
            "sortBy": "-1",
        }
    }
    result = _get("/api/rx/application/datapage", body)
    rows = result.get("data", [])
    target_guid = KNOWN_PEOPLE.get(assignee_name.strip().lower()) if assignee_name else None
    out = []
    for r in rows:
        guid = r.get("536875018")
        if target_guid and guid != target_guid:
            continue
        out.append({
            "task_number": r.get("1"),
            "summary": r.get("8"),
            "assignee": GUID_TO_NAME.get(guid, guid or "unassigned"),
        })
    if not target_guid and len(out) > UNSCOPED_TASK_CAP:
        total = len(out)
        out = out[:UNSCOPED_TASK_CAP]
        out.append({"note": f"truncated — showing {UNSCOPED_TASK_CAP} of {total} total "
                              f"tasks; call again with assignee_name to scope further"})
    return out


def get_hpm_task(task_number: str) -> dict:
    """Get full details of a single HPM task by its task number (e.g. "00000540").
    Read-only — does not modify anything.

    Args:
        task_number: The task's display number, e.g. "00000540" or "540".

    Returns:
        A dict with summary, description, assignee, and status. Or an error message
        if the task number doesn't exist.
    """
    tn = task_number.strip().zfill(8)
    try:
        token = _get_token()
        req = urllib.request.Request(
            f"{HOST}/api/arsys/v1/entry/com.fusiongbs.agility:Project%20Task/{tn}",
            method="GET",
            headers={
                "Authorization": f"AR-JWT {token}",
                "X-Requested-By": "XMLHttpRequest",
            },
        )
        with urllib.request.urlopen(req, timeout=15, context=_SSLCTX) as r:
            v = json.loads(r.read().decode())["values"]
        return {
            "task_number": tn,
            "summary": v.get("Summary"),
            "description": v.get("Description"),
            "assignee": GUID_TO_NAME.get(v.get("Assigned Person"), v.get("Assigned Person")),
            "status": v.get("Status"),
        }
    except urllib.error.HTTPError as e:
        return {"error": f"task {tn} not found or unreadable ({e.code})"}
