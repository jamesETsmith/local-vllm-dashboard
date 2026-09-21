# Performance chart x-axis options report

## Summary

Added accessible X-axis and Y-axis dropdown menus to the Performance dashboard. The X-axis offers concurrency, P50 interactivity, and P99 interactivity; the Y-axis offers total token throughput, output token throughput, TTFT, and TPOT. Interactivity is calculated from output tokens and the matching end-to-end latency percentile, without substituting TPOT or another latency metric. Results missing the required values are omitted from the selected interactivity view.

## Tests

- Baseline: `uv run pytest tests/dashboard/test_chart.py tests/dashboard/test_rendering.py`, 14 passed.
- Regression tests failed before implementation for chart payload preservation and rendered axis controls as expected.
- Focused chart, contract, rendering, documentation, and JavaScript syntax checks passed after each change.
- Final: `uv run poe check`, formatting, lint, types, and all 97 tests passed with one existing Starlette deprecation warning.
- Security: `uv run poe security` passed with no issues.

## Full output

- Final checks: `/tmp/issue-35-full-check.txt`
- Security checks: `/tmp/issue-35-security.txt`
