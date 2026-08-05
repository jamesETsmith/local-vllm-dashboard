# Custom Comparison implementation report

## Summary

Added a server-rendered Custom Comparison page at `/dashboard/comparison`. Users can search and select performance results across models and configurations, switch among total token throughput, output token throughput, TTFT, and TPOT, and plot the selected results together. Comparison bars link to full run details, and the layout adapts for narrower screens.

## Validation

- Focused dashboard tests: 12 passed.
- Full `uv run poe check`: formatting, linting, type checks, and 75 tests passed.
- One existing Starlette/httpx deprecation warning remains.

## Full test output

The full validation output from this implementation run is stored at `/tmp/custom-comparison-check.txt`.
