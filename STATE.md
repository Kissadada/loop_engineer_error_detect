# STATE.md — To-do list from code review (2026-07-30)

Current state: `run_checks.sh` passes (lint, 13 unit tests, smoke test). Everything
below is a gap found on review, not a broken build.

## To do

1. **Unordered/out-of-order timestamps break the sliding window.**
   `detect_bursts` (error_burst_detector.py:41) assumes entries arrive in
   non-decreasing timestamp order — it never sorts. `read_log_entries` just
   appends in file order. If a log file has an out-of-order line (clock skew,
   merged logs from multiple sources), the `while window and (entry.timestamp
   - window[0]).total_seconds() > window_seconds` eviction can behave
   incorrectly (negative diffs, stale entries never evicted). Either sort
   entries by timestamp in `read_log_entries`/before `detect_bursts`, or
   document the ordering assumption explicitly in the README/docstring.

2. **No validation on `--threshold` / `--window-minutes`.** A `--threshold 0`
   or negative value, or a zero/negative `--window-minutes`, produces
   confusing output (e.g. threshold ≤1 flags every single ERROR line as a
   burst) instead of a clear CLI error. Consider rejecting non-positive
   values in `main()`.

3. **Malformed/skipped lines are silently dropped.** `read_log_entries`
   drops any line `parse_log_line` can't parse with no count or warning. For
   a monitoring tool, silently ignoring unparseable input could hide a
   format drift in the upstream log source. Consider printing a count of
   skipped lines (e.g. "skipped N unparseable line(s)") after reading.

4. **No test coverage for:** out-of-order timestamps, non-positive
   threshold/window CLI args, and `write_alerts`/`main()` end-to-end (only
   covered indirectly via smoke_test.sh, not pytest).

## Not doing (noted, not actionable)

- `parts[1].strip("[]")` accepts severity without surrounding brackets
  (e.g. `ERROR` instead of `[ERROR]`) — lenient by accident rather than
  design, but harmless and not worth tightening without a reported need.
