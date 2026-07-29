#!/usr/bin/env bash
# End-to-end smoke test: runs error_burst_detector.py against a small
# synthetic log and checks it exits 0 and emits an ALERT line.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

LOG_FILE="$TMP_DIR/smoke.log"
OUT_FILE="$TMP_DIR/alerts.txt"

cat > "$LOG_FILE" <<'EOF'
2026-07-29T11:55:00Z [INFO] Service started
2026-07-29T12:00:00Z [ERROR] synthetic failure 0
2026-07-29T12:00:20Z [ERROR] synthetic failure 1
2026-07-29T12:00:40Z [ERROR] synthetic failure 2
2026-07-29T12:01:00Z [ERROR] synthetic failure 3
2026-07-29T12:01:20Z [ERROR] synthetic failure 4
2026-07-29T12:01:40Z [ERROR] synthetic failure 5
2026-07-29T12:02:00Z [ERROR] synthetic failure 6
2026-07-29T12:02:20Z [ERROR] synthetic failure 7
2026-07-29T12:02:40Z [ERROR] synthetic failure 8
2026-07-29T12:03:00Z [ERROR] synthetic failure 9
2026-07-29T12:10:00Z [INFO] Recovered
EOF

START=$SECONDS

if ! python3 "$SCRIPT_DIR/error_burst_detector.py" "$LOG_FILE" "$OUT_FILE"; then
    echo "FAIL: error_burst_detector.py exited non-zero"
    exit 1
fi

ELAPSED=$((SECONDS - START))

if ! grep -q "^ALERT " "$OUT_FILE"; then
    echo "FAIL: no ALERT line found in $OUT_FILE"
    cat "$OUT_FILE"
    exit 1
fi

echo "PASS: smoke test succeeded in ${ELAPSED}s"
