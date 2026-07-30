#!/usr/bin/env python3
"""Detect bursts of ERROR log lines within a sliding time window (default: 10+ in 5 minutes)."""

import argparse
from collections import deque, namedtuple
from datetime import datetime, timezone

WINDOW_SECONDS = 300
THRESHOLD = 10

LogEntry = namedtuple("LogEntry", ["timestamp", "severity", "detail"])
Burst = namedtuple("Burst", ["start", "end", "count"])

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_log_line(line):
    """Parse a "<timestamp> [SEVERITY] <detail>" line into a LogEntry, or None if malformed."""
    parts = line.strip().split(maxsplit=2)
    if len(parts) < 2:
        return None
    ts_str, severity = parts[0], parts[1].strip("[]")
    detail = parts[2] if len(parts) == 3 else ""
    try:
        timestamp = datetime.strptime(ts_str, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return LogEntry(timestamp, severity, detail)


def read_log_entries(filepath):
    entries = []
    skipped = 0
    with open(filepath) as f:
        for line in f:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
            elif line.strip():
                skipped += 1
    if skipped:
        print(f"Warning: skipped {skipped} unparseable line(s) in {filepath}")
    entries.sort(key=lambda e: e.timestamp)
    return entries


def detect_bursts(entries, window_seconds=WINDOW_SECONDS, threshold=THRESHOLD):
    """Return one Burst per period where ERROR lines in a sliding window reach threshold.

    A burst stays open (accumulating count and extending its end) for as long as
    the sliding window keeps reaching threshold, even if that spans many window
    lengths, and is only closed once the rate drops back below threshold.

    Assumes entries are sorted by timestamp (read_log_entries guarantees this).
    """
    bursts = []
    window = deque()
    in_burst = False
    burst_start = None
    burst_end = None
    burst_count = 0

    for entry in entries:
        if entry.severity != "ERROR":
            continue

        window.append(entry.timestamp)
        while window and (entry.timestamp - window[0]).total_seconds() > window_seconds:
            window.popleft()

        if len(window) >= threshold:
            if not in_burst:
                burst_start = window[0]
                burst_count = len(window)
                in_burst = True
            else:
                burst_count += 1
            burst_end = entry.timestamp
        elif in_burst:
            bursts.append(Burst(start=burst_start, end=burst_end, count=burst_count))
            in_burst = False

    if in_burst:
        bursts.append(Burst(start=burst_start, end=burst_end, count=burst_count))

    return bursts


def format_alert(burst):
    start = burst.start.strftime(TIMESTAMP_FORMAT)
    end = burst.end.strftime(TIMESTAMP_FORMAT)
    return f"ALERT {burst.count} ERROR lines between {start} and {end}"


def write_alerts(bursts, output_path):
    with open(output_path, "w") as f:
        for burst in bursts:
            f.write(format_alert(burst) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", help="Path to the input log file")
    parser.add_argument("output_file", help="Path to write alert lines to")
    parser.add_argument(
        "--threshold",
        type=int,
        default=THRESHOLD,
        help=f"ERROR lines needed to trigger an alert (default: {THRESHOLD})",
    )
    parser.add_argument(
        "--window-minutes",
        type=float,
        default=WINDOW_SECONDS / 60,
        help=f"Sliding window size in minutes (default: {WINDOW_SECONDS / 60:g})",
    )
    args = parser.parse_args()

    if args.threshold <= 0:
        parser.error("--threshold must be a positive integer")
    if args.window_minutes <= 0:
        parser.error("--window-minutes must be a positive number")

    entries = read_log_entries(args.log_file)
    bursts = detect_bursts(
        entries, window_seconds=args.window_minutes * 60, threshold=args.threshold
    )
    write_alerts(bursts, args.output_file)
    print(f"Detected {len(bursts)} burst(s); alerts written to {args.output_file}")


if __name__ == "__main__":
    main()
