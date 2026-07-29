---
name: pre-deploy-check
description: >
  Run this repo's full pre-deploy verification: ruff lint + format check,
  the pytest suite, the end-to-end smoke test, and a scan for stray debug
  prints. Use before saying any change is ready to ship, before a commit
  that touches error_burst_detector.py or its tests, or whenever the user
  asks to "check it's ready" / "run the pre-deploy checks."
user_invocable: true
---

# Pre-Deploy Check Skill

Runs the same four checks every time, in order, and gives a single go/no-go
verdict. Don't skip a step because an earlier one failed — run all four,
then report everything that's wrong at once.

## 0. Ensure tooling is available

This repo pins its dev tooling in `pyproject.toml` (`[dependency-groups] dev
= ["ruff==0.16.0"]`) and uses a local `.venv` rather than system Python
(Homebrew's Python is externally managed — plain `pip install` will fail
with a PEP 668 error).

```bash
test -d .venv || python3 -m venv .venv
./.venv/bin/python -m pip show ruff  >/dev/null 2>&1 || ./.venv/bin/python -m pip install -q ruff==0.16.0
./.venv/bin/python -m pip show pytest >/dev/null 2>&1 || ./.venv/bin/python -m pip install -q pytest
```

## 1. Lint + format (ruff, config pinned in `pyproject.toml`)

```bash
./.venv/bin/ruff check .
./.venv/bin/ruff format --check --diff .
```

Both must report clean. If `ruff check` finds real issues, fix them
directly (see the `simplify` skill's spirit: fix, don't suppress with
`# noqa` unless the rule is a genuine false positive — explain why if you
do). If `ruff format` wants changes, run `./.venv/bin/ruff format .` and
re-check.

## 2. Test suite

```bash
./.venv/bin/python -m pytest -q
```

All tests must pass. A skipped or xfailed test is not a pass — investigate
before proceeding.

## 3. Smoke test

```bash
./smoke_test.sh
```

Must exit 0 and print `PASS:`. It runs `error_burst_detector.py`
end-to-end against a synthetic log and checks for an `ALERT` line; it
should finish in well under 5 seconds. If it hangs or takes noticeably
longer, treat that as a failure worth investigating, not just a slow pass.

## 4. Stray debug prints

Search for debug leftovers, then triage each hit by hand — don't just
count matches:

```bash
grep -rnE 'print\(|breakpoint\(\)|import pdb|pdb\.set_trace|ipdb' \
    --include='*.py' . | grep -v '\.venv/'
```

**Known intentional print — not a finding:** `error_burst_detector.py`'s
`main()` has one `print(f"Detected {len(bursts)} burst(s)...")` — that's
the CLI's normal user-facing status output, not debug scaffolding. Leave
it.

Flag anything else: prints inside `parse_log_line`, `read_log_entries`,
`detect_bursts`, `format_alert`, or `write_alerts` (the library functions
have no business writing to stdout), anything that dumps a raw variable
or a loop-internal value, or anything containing `DEBUG`/`XXX`/`TEMP`. Ask
before removing if you're not sure whether it's load-bearing output vs.
leftover debugging.

## Output

Report a single verdict, not a play-by-play:

```markdown
## Pre-Deploy Check: PASS | FAIL

- Lint (ruff check):    pass/fail
- Format (ruff format): pass/fail
- Tests (pytest):       N passed / M failed
- Smoke test:           pass/fail (Xs)
- Debug prints:         clean | N flagged (list them)

(If FAIL: what's broken and the smallest fix, not a rewrite.)
```

## Rules

- Run all four checks even if the first one fails — one combined report,
  not four separate interruptions.
- Don't mark PASS if you didn't actually run a step (e.g., couldn't run
  the smoke test because bash wasn't available) — say so explicitly
  instead of assuming it would have passed.
- Fixes should be surgical: this skill verifies, it doesn't refactor. If a
  real lint/test failure needs more than a small fix, stop and report
  rather than expanding scope.
