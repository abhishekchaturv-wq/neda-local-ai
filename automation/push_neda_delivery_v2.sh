#!/bin/bash
set -euo pipefail

ROOT="$HOME/Downloads/neda-delivery"
INBOX="$ROOT/inbox"
MANIFEST="$ROOT/DELIVERY_MANIFEST.json"
STATE="$ROOT/state"
LOG="$ROOT/delivery.log"
REPO="$HOME/local-ai"
EXPECTED_REMOTE="https://github.com/abhishekchaturv-wq/neda-local-ai.git"
LOCK="$ROOT/.delivery.lock"

# Result codes:
#   0  SUCCESS
#   10 BUSY / RETRY
#   1+ FAILURE

mkdir -p "$STATE"
exec >>"$LOG" 2>&1

echo
echo "===== NEDA SAFE DELIVERY V2 $(date '+%Y-%m-%d %H:%M:%S') ====="

acquire_lock() {
  if [[ -e "$LOCK" ]]; then
    old_pid="$(sed -n '1p' "$LOCK" 2>/dev/null || true)"
    old_ts="$(sed -n '2p' "$LOCK" 2>/dev/null || true)"

    if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
      echo "RESULT=BUSY"
      echo "Another delivery is already running (PID $old_pid); retry later."
      exit 10
    fi

    echo "Removing stale delivery lock (PID=${old_pid:-unknown}, timestamp=${old_ts:-unknown})."
    rm -f "$LOCK"
  fi

  (
    set -C
    printf '%s\n%s\n' "$$" "$(date '+%Y-%m-%d %H:%M:%S')" > "$LOCK"
  ) 2>/dev/null || {
    echo "RESULT=BUSY"
    echo "Another delivery acquired the lock; retry later."
    exit 10
  }
}

release_lock() {
  rm -f "$LOCK"
}

trap release_lock EXIT INT TERM
acquire_lock

fail() {
  echo "RESULT=FAILED"
  echo "$1"
  exit "${2:-1}"
}

if [[ ! -d "$REPO/.git" ]]; then
  fail "ERROR: $REPO is not a Git repository."
fi

REMOTE="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
if [[ "$REMOTE" != "$EXPECTED_REMOTE" ]]; then
  fail "ERROR: unexpected origin: $REMOTE"
fi

if [[ ! -f "$MANIFEST" ]]; then
  echo "RESULT=NOOP"
  echo "No manifest; nothing to do."
  exit 0
fi

python3 - "$MANIFEST" "$INBOX" <<'PY'
import json, pathlib, sys

manifest = pathlib.Path(sys.argv[1])
inbox = pathlib.Path(sys.argv[2]).resolve()
data = json.loads(manifest.read_text())

files = data.get("files", [])
deletes = data.get("delete_files", [])

if not isinstance(files, list) or not isinstance(deletes, list):
    raise SystemExit("ERROR: files/delete_files must be arrays")

for rel in files:
    p = pathlib.PurePosixPath(rel)
    if not rel or p.is_absolute() or ".." in p.parts:
        raise SystemExit(f"ERROR: unsafe delivery path: {rel!r}")
    src = (inbox / rel).resolve()
    if inbox not in src.parents:
        raise SystemExit(f"ERROR: source escapes inbox: {rel}")
    if not src.is_file():
        raise SystemExit(f"ERROR: missing delivery file: {src}")

for rel in deletes:
    p = pathlib.PurePosixPath(rel)
    if not rel or p.is_absolute() or ".." in p.parts:
        raise SystemExit(f"ERROR: unsafe delete path: {rel!r}")
PY

COUNT="$(python3 - "$MANIFEST" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
print(len(d.get("files", [])) + len(d.get("delete_files", [])))
PY
)"

if [[ "$COUNT" == "0" ]]; then
  echo "RESULT=NOOP"
  echo "Manifest contains no changes; nothing to deliver."
  exit 0
fi

echo "===== FETCH ORIGIN ====="
git -C "$REPO" fetch origin main || fail "ERROR: git fetch failed"
BASE_SHA="$(git -C "$REPO" rev-parse origin/main)"
echo "Delivery base: $BASE_SHA"

WORKTREE="$(mktemp -d "$ROOT/.worktree.XXXXXX")"
cleanup_worktree() {
  git -C "$REPO" worktree remove --force "$WORKTREE" 2>/dev/null || true
  rm -rf "$WORKTREE" 2>/dev/null || true
}
trap 'cleanup_worktree; release_lock' EXIT INT TERM

echo "===== CREATE ISOLATED WORKTREE ====="
git -C "$REPO" worktree add --detach "$WORKTREE" "$BASE_SHA" ||
  fail "ERROR: failed to create isolated worktree"

python3 - "$MANIFEST" "$INBOX" "$WORKTREE" <<'PY'
import json, pathlib, shutil, sys

manifest = pathlib.Path(sys.argv[1])
inbox = pathlib.Path(sys.argv[2]).resolve()
worktree = pathlib.Path(sys.argv[3]).resolve()
data = json.loads(manifest.read_text())

for rel in data.get("files", []):
    src = (inbox / rel).resolve()
    dst = (worktree / rel).resolve()
    if worktree not in dst.parents:
        raise SystemExit(f"ERROR: destination escapes worktree: {rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"DELIVERY FILE: {rel}")

for rel in data.get("delete_files", []):
    dst = (worktree / rel).resolve()
    if worktree not in dst.parents:
        raise SystemExit(f"ERROR: delete path escapes worktree: {rel}")
    if dst.exists():
        if not dst.is_file():
            raise SystemExit(f"ERROR: refusing to delete non-file: {rel}")
        dst.unlink()
        print(f"DELETE FILE: {rel}")

(worktree / ".neda_delivery_id").write_text(
    str(data.get("delivery_id", "UNKNOWN")) + "\n"
)
PY

DELIVERY_ID="$(cat "$WORKTREE/.neda_delivery_id")"
rm -f "$WORKTREE/.neda_delivery_id"

echo "===== VALIDATE ====="
git -C "$WORKTREE" diff --check || fail "ERROR: git diff --check failed"
CHANGED="$(git -C "$WORKTREE" status --short)"
echo "$CHANGED"

python3 - "$MANIFEST" "$WORKTREE" <<'PY'
import json, pathlib, subprocess, sys

manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
worktree = pathlib.Path(sys.argv[2])
allowed = set(manifest.get("files", [])) | set(manifest.get("delete_files", []))

raw = subprocess.check_output(
    ["git", "-C", str(worktree), "status", "--porcelain=v1", "--untracked-files=all"],
    text=True,
)

changed = set()
for line in raw.splitlines():
    if not line:
        continue
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    changed.add(path)

unexpected = changed - allowed
if unexpected:
    raise SystemExit("ERROR: undeclared changes detected: " + ", ".join(sorted(unexpected)))
PY

if [[ -z "$CHANGED" ]]; then
  echo "RESULT=NOOP"
  echo "No changes after applying manifest; nothing to commit."
  exit 0
fi

echo "===== STAGE ONLY DECLARED FILES ====="
while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  git -C "$WORKTREE" add -- "$rel"
done < <(python3 - "$MANIFEST" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
for x in d.get("files", []) + d.get("delete_files", []):
    print(x)
PY
)

if git -C "$WORKTREE" diff --cached --quiet; then
  echo "RESULT=NOOP"
  echo "Nothing staged; nothing to commit."
  exit 0
fi

echo "===== COMMIT ====="
git -C "$WORKTREE" -c user.name="NEDA Delivery" -c user.email="neda-delivery@localhost" \
  commit -m "delivery: $DELIVERY_ID" || fail "ERROR: commit failed"

echo "===== PUSH ====="
git -C "$WORKTREE" push origin HEAD:main || fail "ERROR: push failed"

echo "===== SUCCESS ====="
git -C "$WORKTREE" log -1 --oneline
echo "RESULT=SUCCESS"
exit 0
