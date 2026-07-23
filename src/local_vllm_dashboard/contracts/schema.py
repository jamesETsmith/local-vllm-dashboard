import json

from local_vllm_dashboard.contracts.v1 import Bundle


def render_bundle_v1_schema() -> str:
    schema = Bundle.model_json_schema(
        mode="validation",
        ref_template="#/$defs/{model}",
    )
    schema["$id"] = "urn:local-vllm-dashboard:contracts:bundle:v1"
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"
