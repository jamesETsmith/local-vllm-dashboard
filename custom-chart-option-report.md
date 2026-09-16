# Custom comparison chart type report

## Summary

Added an accessible chart type selector to Custom Comparison with bar and line options. Bar remains the default. Both chart types preserve result labels, values, tooltips, keyboard activation, run-detail links, and responsive layout.

## Tests

- Baseline: `uv run pytest tests/dashboard/test_rendering.py`, 12 passed.
- Regression test before implementation: 1 failed and 1 passed, with the missing bar chart control as expected.
- Focused checks after each change: all selected custom comparison and documentation tests passed.
- Final: `uv run poe check`, formatting, lint, types, and all 97 tests passed with one existing Starlette deprecation warning.

## Full output

Final check output: `/tmp/custom-chart-option-check.txt`
