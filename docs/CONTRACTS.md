# Canonical contract

The approved architecture is defined in [DESIGN.md](DESIGN.md). This document records only the v1 contract compatibility policy.

- `schemas/bundle-v1.schema.json` is the portable JSON Schema.
- `local_vllm_dashboard.contracts.Bundle` is the Python validation model.
- Files under `tests/fixtures/contracts/v1/` are representative payloads.
- v1 rejects unknown fields except inside explicit `extensions` maps.
- Optional fields and new controlled-vocabulary values may be added within v1.
- Existing field removal, required-field additions, type changes, or semantic changes require a new major contract version.
- Historical accepted payloads are interpreted using their declared contract version and are not rewritten.

Regenerate the checked-in schema with:

```text
uv run python scripts/generate_contract_schema.py
```
