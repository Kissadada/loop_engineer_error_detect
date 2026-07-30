#!/usr/bin/env bash
# End-to-end smoke test: runs error_burst_detector.py against a small
# synthetic log with two bursts — a short one and one that runs well past
# the 5-minute window — and checks the CLI exits 0 and emits the right
# ALERT lines for both.
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
2026-07-29T13:00:00Z [ERROR] synthetic sustained failure 0
2026-07-29T13:00:15Z [ERROR] synthetic sustained failure 1
2026-07-29T13:00:30Z [ERROR] synthetic sustained failure 2
2026-07-29T13:00:45Z [ERROR] synthetic sustained failure 3
2026-07-29T13:01:00Z [ERROR] synthetic sustained failure 4
2026-07-29T13:01:15Z [ERROR] synthetic sustained failure 5
2026-07-29T13:01:30Z [ERROR] synthetic sustained failure 6
2026-07-29T13:01:45Z [ERROR] synthetic sustained failure 7
2026-07-29T13:02:00Z [ERROR] synthetic sustained failure 8
2026-07-29T13:02:15Z [ERROR] synthetic sustained failure 9
2026-07-29T13:02:30Z [ERROR] synthetic sustained failure 10
2026-07-29T13:02:45Z [ERROR] synthetic sustained failure 11
2026-07-29T13:03:00Z [ERROR] synthetic sustained failure 12
2026-07-29T13:03:15Z [ERROR] synthetic sustained failure 13
2026-07-29T13:03:30Z [ERROR] synthetic sustained failure 14
2026-07-29T13:03:45Z [ERROR] synthetic sustained failure 15
2026-07-29T13:04:00Z [ERROR] synthetic sustained failure 16
2026-07-29T13:04:15Z [ERROR] synthetic sustained failure 17
2026-07-29T13:04:30Z [ERROR] synthetic sustained failure 18
2026-07-29T13:04:45Z [ERROR] synthetic sustained failure 19
2026-07-29T13:05:00Z [ERROR] synthetic sustained failure 20
2026-07-29T13:05:15Z [ERROR] synthetic sustained failure 21
2026-07-29T13:05:30Z [ERROR] synthetic sustained failure 22
2026-07-29T13:05:45Z [ERROR] synthetic sustained failure 23
2026-07-29T13:06:00Z [ERROR] synthetic sustained failure 24
2026-07-29T13:06:15Z [ERROR] synthetic sustained failure 25
2026-07-29T13:06:30Z [ERROR] synthetic sustained failure 26
2026-07-29T13:06:45Z [ERROR] synthetic sustained failure 27
2026-07-29T13:07:00Z [ERROR] synthetic sustained failure 28
2026-07-29T13:10:00Z [INFO] Service stable
EOF

START=$SECONDS

if ! python3 "$SCRIPT_DIR/error_burst_detector.py" "$LOG_FILE" "$OUT_FILE"; then
    echo "FAIL: error_burst_detector.py exited non-zero"
    exit 1
fi

ELAPSED=$((SECONDS - START))

ALERT_COUNT=$(grep -c "^ALERT " "$OUT_FILE" || true)
if [ "$ALERT_COUNT" -ne 2 ]; then
    echo "FAIL: expected 2 ALERT lines, got $ALERT_COUNT"
    cat "$OUT_FILE"
    exit 1
fi

# Regression check: the second burst runs for 7 minutes (13:00:00-13:07:00),
# well past the 5-minute window. Before the fix, a burst's reported end
# froze at the moment the window first hit threshold, so the count stayed
# near 10 no matter how much longer the burst actually continued. It must
# now reflect all 29 ERROR lines in that sustained burst.
SUSTAINED_COUNT=$(awk 'NR==2{print $2}' "$OUT_FILE")
if [ "$SUSTAINED_COUNT" -ne 29 ]; then
    echo "FAIL: sustained burst should report 29 ERROR lines, got $SUSTAINED_COUNT"
    cat "$OUT_FILE"
    exit 1
fi

if ! grep -q "13:07:00Z" "$OUT_FILE"; then
    echo "FAIL: sustained burst's alert should end at 13:07:00Z (the last error), not freeze earlier"
    cat "$OUT_FILE"
    exit 1
fi

echo "PASS: smoke test succeeded in ${ELAPSED}s"
