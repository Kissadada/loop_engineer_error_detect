import subprocess
import sys
from datetime import datetime, timedelta, timezone

from error_burst_detector import (
    WINDOW_SECONDS,
    detect_bursts,
    format_alert,
    parse_log_line,
    read_log_entries,
    write_alerts,
)

BASE = datetime(2026, 7, 29, 15, 0, 0, tzinfo=timezone.utc)


def make_entries(offsets_seconds, severity="ERROR", detail="x"):
    return [
        parse_log_line(
            f"{(BASE + timedelta(seconds=s)).strftime('%Y-%m-%dT%H:%M:%SZ')} [{severity}] {detail}"
        )
        for s in offsets_seconds
    ]


def test_parse_log_line():
    entry = parse_log_line("2026-07-29T15:27:53Z [ERROR] Database connection failed")
    assert entry.severity == "ERROR"
    assert entry.detail == "Database connection failed"
    assert entry.timestamp == datetime(2026, 7, 29, 15, 27, 53, tzinfo=timezone.utc)


def test_parse_log_line_malformed_returns_none():
    assert parse_log_line("") is None
    assert parse_log_line("not a valid line") is None


def test_burst_detected_when_ten_errors_within_five_minutes():
    entries = make_entries(range(0, 200, 20))  # 10 ERRORs, 20s apart, spans 180s
    bursts = detect_bursts(entries)
    assert len(bursts) == 1
    assert bursts[0].count == 10


def test_custom_threshold_and_window_override_defaults():
    entries = make_entries(range(0, 80, 20))  # 4 ERRORs, 20s apart, spans 60s

    # Below the default threshold (10), no burst.
    assert detect_bursts(entries) == []

    # A lower threshold turns the same entries into a burst.
    bursts = detect_bursts(entries, threshold=4)
    assert len(bursts) == 1
    assert bursts[0].count == 4

    # A narrower window (30s) excludes some of the same entries, so 4 never
    # co-occur and no burst is detected even with threshold=4.
    assert detect_bursts(entries, window_seconds=30, threshold=4) == []


def test_no_burst_when_errors_spread_out():
    entries = make_entries(range(0, 3000, 300))  # 300s apart, never 10 within 5 min
    bursts = detect_bursts(entries)
    assert bursts == []


def test_no_burst_below_threshold():
    entries = make_entries(range(0, 180, 20))  # 9 ERRORs within window
    bursts = detect_bursts(entries)
    assert bursts == []


def test_one_alert_per_sustained_burst_not_per_line():
    # 15 ERRORs 20s apart: all fall within one 5-minute window, so this is
    # a single continuous burst and should yield exactly one alert.
    entries = make_entries(range(0, 300, 20))
    bursts = detect_bursts(entries)
    assert len(bursts) == 1


def test_burst_end_and_count_keep_growing_past_one_window():
    # 60 ERRORs 20s apart span 1180s (~19.7 min) of continuous high rate,
    # nearly 4x the 300s window. The burst must stay open and its end/count
    # must keep tracking the actual last error, not freeze at the moment
    # the window first reached threshold (that was the bug: a burst could
    # silently run far longer than the window without the report reflecting
    # it, capping duration at window_seconds and count at ~threshold).
    entries = make_entries(range(0, 1200, 20))
    bursts = detect_bursts(entries)
    assert len(bursts) == 1

    burst = bursts[0]
    assert burst.count == len(entries)
    assert burst.end == entries[-1].timestamp
    assert (burst.end - burst.start).total_seconds() > WINDOW_SECONDS


def test_burst_closes_when_rate_drops_then_reopens_as_new_burst():
    # A sustained burst that dips below threshold, then resumes, should be
    # reported as two separate closed bursts, not one that silently
    # swallows the gap.
    high_rate = list(range(0, 200, 20))  # 10 ERRORs, crosses threshold
    gap = list(range(200, 800, 300))  # sparse, keeps window below threshold
    high_rate_again = list(range(800, 1000, 20))  # 10 more ERRORs
    entries = make_entries(high_rate + gap + high_rate_again)

    bursts = detect_bursts(entries)
    assert len(bursts) == 2
    assert bursts[0].end < bursts[1].start


def test_two_separate_bursts_yield_two_alerts():
    burst1 = range(0, 200, 20)  # 10 ERRORs
    burst2 = range(2000, 2200, 20)  # 10 more ERRORs, well outside first window
    entries = make_entries(list(burst1) + list(burst2))
    bursts = detect_bursts(entries)
    assert len(bursts) == 2


def test_non_error_lines_are_ignored():
    entries = make_entries(range(0, 200, 20), severity="WARN")
    bursts = detect_bursts(entries)
    assert bursts == []


def test_format_alert():
    entries = make_entries(range(0, 200, 20))
    bursts = detect_bursts(entries)
    line = format_alert(bursts[0])
    assert line.startswith("ALERT 10 ERROR lines between ")
    assert "2026-07-29T15:00:00Z" in line
    assert "2026-07-29T15:03:00Z" in line


def test_sample_log_file_produces_three_bursts():
    entries = read_log_entries("sample_log.txt")
    bursts = detect_bursts(entries)
    assert len(bursts) == 3

    # One of the bursts is a sustained burst that runs longer than the
    # 5-minute window itself (regression check for the bug where a burst's
    # reported end froze at the moment threshold was first crossed instead
    # of tracking how long the burst actually continued).
    durations = [(b.end - b.start).total_seconds() for b in bursts]
    assert any(d > 300 for d in durations)


def test_sparse_errors_in_log_file_no_alert(tmp_path):
    log_file = tmp_path / "sparse.log"
    lines = [
        f"{(BASE + timedelta(seconds=s)).strftime('%Y-%m-%dT%H:%M:%SZ')} [ERROR] sparse failure"
        for s in range(0, 3000, 300)  # one ERROR every 5 minutes, never 10 in-window
    ]
    log_file.write_text("\n".join(lines) + "\n")

    entries = read_log_entries(str(log_file))
    bursts = detect_bursts(entries)
    assert bursts == []


def test_read_log_entries_sorts_out_of_order_lines(tmp_path):
    # 10 ERRORs 20s apart, written to the file in reverse chronological order.
    offsets = list(range(0, 200, 20))
    lines = [
        f"{(BASE + timedelta(seconds=s)).strftime('%Y-%m-%dT%H:%M:%SZ')} [ERROR] x"
        for s in reversed(offsets)
    ]
    log_file = tmp_path / "unordered.log"
    log_file.write_text("\n".join(lines) + "\n")

    entries = read_log_entries(str(log_file))
    assert [e.timestamp for e in entries] == sorted(e.timestamp for e in entries)

    bursts = detect_bursts(entries)
    assert len(bursts) == 1
    assert bursts[0].count == 10


def test_read_log_entries_warns_on_skipped_lines(tmp_path, capsys):
    log_file = tmp_path / "bad.log"
    log_file.write_text("not a valid line\nalso bad\n")

    entries = read_log_entries(str(log_file))
    assert entries == []
    assert "skipped 2 unparseable line(s)" in capsys.readouterr().out


def test_write_alerts(tmp_path):
    entries = make_entries(range(0, 200, 20))
    bursts = detect_bursts(entries)
    out_file = tmp_path / "alerts.txt"

    write_alerts(bursts, str(out_file))

    assert out_file.read_text() == format_alert(bursts[0]) + "\n"


def test_main_end_to_end(tmp_path):
    out_file = tmp_path / "burst.txt"
    result = subprocess.run(
        [sys.executable, "error_burst_detector.py", "sample_log.txt", str(out_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Detected 3 burst(s)" in result.stdout
    lines = out_file.read_text().splitlines()
    assert len(lines) == 3
    assert all(line.startswith("ALERT ") for line in lines)


def test_main_rejects_non_positive_threshold(tmp_path):
    out_file = tmp_path / "burst.txt"
    result = subprocess.run(
        [
            sys.executable,
            "error_burst_detector.py",
            "sample_log.txt",
            str(out_file),
            "--threshold",
            "0",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--threshold must be a positive integer" in result.stderr


def test_main_rejects_non_positive_window(tmp_path):
    out_file = tmp_path / "burst.txt"
    result = subprocess.run(
        [
            sys.executable,
            "error_burst_detector.py",
            "sample_log.txt",
            str(out_file),
            "--window-minutes",
            "-1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--window-minutes must be a positive number" in result.stderr


def test_mixed_severity_log_file_ignores_non_errors(tmp_path):
    log_file = tmp_path / "mixed.log"
    lines = []
    for s in range(0, 200, 20):
        ts = (BASE + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f"{ts} [INFO] heartbeat")
        lines.append(f"{ts} [WARN] elevated latency")
        lines.append(f"{ts} [DEBUG] trace detail")
    log_file.write_text("\n".join(lines) + "\n")

    entries = read_log_entries(str(log_file))
    bursts = detect_bursts(entries)
    assert bursts == []
