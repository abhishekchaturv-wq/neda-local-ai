#!/bin/bash
set -euo pipefail

ROOT="$HOME/Downloads/neda-delivery"
INBOX="$ROOT/inbox"
MANIFEST="$ROOT/DELIVERY_MANIFEST.json"
STATE="$ROOT/state"
LOG="$ROOT/watcher.log"
DELIVERY="$ROOT/automation/push_neda_delivery_v2.sh"
POLL_SECONDS="${NEDA_DELIVERY_POLL_SECONDS:-3}"
BUSY_RETRY_SECONDS="${NEDA_DELIVERY_BUSY_RETRY_SECONDS:-5}"

mkdir -p "$STATE" "$INBOX"
exec >>"$LOG" 2>&1

echo
echo "===== NEDA DELIVERY WATCHER V3 $(date '+%Y-%m-%d %H:%M:%S') ====="
echo "Watching: $INBOX"
echo "Poll interval: ${POLL_SECONDS}s"
echo "Busy retry: ${BUSY_RETRY_SECONDS}s"

last_fingerprint=""

fingerprint() {
  python3 - "$MANIFEST" "$INBOX" <<'PY'
import hashlib, json, pathlib, sys

manifest = pathlib.Path(sys.argv[1])
inbox = pathlib.Path(sys.argv[2])

if not manifest.is_file():
    print("")
    raise SystemExit

try:
    data = json.loads(manifest.read_text())
except Exception:
    print("INVALID_MANIFEST")
    raise SystemExit

paths = list(data.get("files", [])) + list(data.get("delete_files", []))
h = hashlib.sha256(manifest.read_bytes())

for rel in sorted(set(paths)):
    p = inbox / rel
    h.update(rel.encode())
    if p.is_file():
        h.update(str(p.stat().st_size).encode())
        h.update(str(p.stat().st_mtime_ns).encode())
        h.update(hashlib.sha256(p.read_bytes()).digest())

print(h.hexdigest())
PY
}

echo "ready"

while true; do
  if [[ -f "$MANIFEST" ]]; then
    fp="$(fingerprint || true)"

    if [[ -n "$fp" && "$fp" != "INVALID_MANIFEST" && "$fp" != "$last_fingerprint" ]]; then
      echo "===== NEW DELIVERY DETECTED $(date '+%Y-%m-%d %H:%M:%S') ====="
      echo "Fingerprint: $fp"

      sleep 2

      fp_after="$(fingerprint || true)"
      if [[ "$fp_after" != "$fp" ]]; then
        echo "RESULT=CHANGED_DURING_SETTLE"
        echo "Delivery changed while settling; waiting for next poll."
        sleep "$POLL_SECONDS"
        continue
      fi

      if [[ ! -x "$DELIVERY" ]]; then
        echo "RESULT=FAILED"
        echo "ERROR: delivery script missing or not executable: $DELIVERY"
        sleep "$POLL_SECONDS"
        continue
      fi

      set +e
      "$DELIVERY"
      rc=$?
      set -e

      case "$rc" in
        0)
          echo "===== DELIVERY SUCCESSFUL ====="
          last_fingerprint="$fp"

          if [[ -f "$MANIFEST" ]]; then
            archive="$STATE/processed-manifests"
            mkdir -p "$archive"
            stamp="$(date '+%Y%m%d-%H%M%S')"
            cp "$MANIFEST" "$archive/${stamp}-${fp}.json"
            rm -f "$MANIFEST"
          fi
          ;;
        10)
          echo "===== DELIVERY DEFERRED / RETRY ====="
          echo "Manifest retained; another delivery is active."
          sleep "$BUSY_RETRY_SECONDS"
          ;;
        *)
          echo "===== DELIVERY FAILED rc=$rc ====="
          echo "Manifest retained for retry/correction."
          sleep "$POLL_SECONDS"
          ;;
      esac
    elif [[ "$fp" == "INVALID_MANIFEST" ]]; then
      echo "RESULT=FAILED"
      echo "ERROR: manifest is invalid JSON; waiting for correction."
    fi
  fi

  sleep "$POLL_SECONDS"
done
