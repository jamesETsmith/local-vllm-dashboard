from pathlib import Path

from local_vllm_dashboard.contracts.schema import render_bundle_v1_schema

SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "bundle-v1.schema.json"


def main() -> None:
    SCHEMA_PATH.write_text(render_bundle_v1_schema())


if __name__ == "__main__":
    main()
