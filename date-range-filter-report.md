# Dashboard date range filter report

## Summary

Added inclusive completion-date filters to the Performance, Accuracy, and Raw Data Table views. Dashboard pages default to the last four weeks, while explicitly clearing both fields shows all dates. Date selections automatically refresh the dashboard, apply to CSV downloads, tolerate invalid query values by treating them as unset, and are documented in the shared Help and agent guide.

## Tests

- Regression test before implementation: 1 failed and 4 passed because date filters were not accepted.
- Focused checks after each change: all 20 dashboard repository and rendering tests passed.
- Default-range regression test before implementation: 1 failed and 14 passed as expected.
- Final: `uv run poe check`, formatting, lint, types, and all 101 tests passed with one existing Starlette deprecation warning.

## Full output

Final check output: `/tmp/issue-36-check.txt`
