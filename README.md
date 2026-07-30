# Error Detector Project

Detects bursts of `ERROR` log lines within a sliding time window (default:
10+ lines in 5 minutes, both configurable) and writes one alert line per
burst to an output file.

## Log format

```
2026-07-29T15:27:53Z [ERROR] Detail message here
```

`<ISO8601 timestamp>Z [SEVERITY] <detail>`

## Usage

```bash
python3 error_burst_detector.py <input.log> <output.txt> [--threshold N] [--window-minutes M]
```

`--threshold` (default `10`) and `--window-minutes` (default `5`) override
the burst definition without touching code.

Example:

```bash
python3 error_burst_detector.py sample_log.txt burst.txt
```

Output (`burst.txt`), one line per burst:

```
ALERT 12 ERROR lines between 2026-07-29T15:27:00Z and 2026-07-29T15:30:40Z
ALERT 33 ERROR lines between 2026-07-29T16:02:00Z and 2026-07-29T16:10:00Z
ALERT 12 ERROR lines between 2026-07-29T16:21:00Z and 2026-07-29T16:24:40Z
```

Custom threshold/window:

```bash
python3 error_burst_detector.py sample_log.txt burst.txt --threshold 3 --window-minutes 1
```

## Files

- `error_burst_detector.py` — parser + sliding-window burst detector + CLI
- `test_error_burst_detector.py` — pytest suite
- `sample_log.txt` — sample log with three deliberate bursts (one sustained
  past the 5-minute window), for manual testing
- `smoke_test.sh` — end-to-end smoke test (runs the CLI against a synthetic
  log with a short burst and a 7-minute sustained burst, and checks the
  sustained burst's alert reflects its true length)
- `run_checks.sh` — lint, tests, smoke test, in order
- `pyproject.toml` — pinned ruff config

## Development

```bash
python3 -m venv .venv
./.venv/bin/pip install ruff==0.16.0 pytest
```

Run everything:

```bash
bash run_checks.sh
```

Runs lint → unit tests → smoke test, in that order, stopping on first
failure. Exits 0 and prints `ALL CHECKS PASSED` only if everything passes.

## Working as loop engineering

This project is meant to be iterated on in a verify-then-stop loop, not by
eyeballing individual test output:

1. Make a change.
2. Run `bash run_checks.sh`.
3. If it fails, fix only what's broken — no drive-by refactors — and re-run.
4. Only consider the change done once it prints `ALL CHECKS PASSED`.

`run_checks.sh` is the single source of truth for "is this ready" — lint,
tests, and the smoke test all have to agree, in that order, with no partial
credit. The `.claude/skills/pre-deploy-check/` skill packages this same
sequence (plus a stray-debug-print check) so it doesn't need to be
re-explained each session — invoke it, or just run `run_checks.sh` directly,
before calling any change ready to ship.
