import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.contracts.schema import render_bundle_v1_schema

FIXTURES = Path(__file__).parent / "fixtures" / "contracts" / "v1"
SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "bundle-v1.schema.json"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize("name", ["performance.json", "accuracy.json"])
def test_valid_fixtures_round_trip(name: str) -> None:
    bundle = Bundle.model_validate(load_fixture(name))

    assert Bundle.model_validate_json(bundle.canonical_json()) == bundle


@pytest.mark.parametrize("name", ["performance.json", "accuracy.json"])
def test_idempotency_key_is_deterministic(name: str) -> None:
    bundle = Bundle.model_validate(load_fixture(name))
    calculated = bundle.calculated_idempotency_key()
    updated = bundle.model_copy(update={"idempotency_key": calculated})

    assert updated.has_valid_idempotency_key()
    reparsed = Bundle.model_validate_json(updated.canonical_json())
    assert reparsed.calculated_idempotency_key() == calculated


def test_unknown_fields_are_rejected() -> None:
    data = load_fixture("performance.json")
    data["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Bundle.model_validate(data)


def test_unknown_metric_names_are_rejected() -> None:
    data = load_fixture("performance.json")
    data["observations"][0]["metrics"][0]["name"] = "unknown_metric"

    with pytest.raises(ValidationError, match="Input should be"):
        Bundle.model_validate(data)


def test_nonempty_custom_units_are_accepted() -> None:
    data = load_fixture("performance.json")
    data["observations"][0]["metrics"][0]["unit"] = "widgets/fortnight"

    bundle = Bundle.model_validate(data)

    assert bundle.observations[0].metrics[0].unit == "widgets/fortnight"


def test_empty_units_are_rejected() -> None:
    data = load_fixture("performance.json")
    data["observations"][0]["metrics"][0]["unit"] = ""

    with pytest.raises(ValidationError, match="at least 1 character"):
        Bundle.model_validate(data)


def test_duplicate_observation_ids_are_rejected() -> None:
    data = load_fixture("performance.json")
    data["observations"].append(data["observations"][0])

    with pytest.raises(ValidationError, match="observation_id values must be unique"):
        Bundle.model_validate(data)


def test_duplicate_metric_identities_are_rejected() -> None:
    data = load_fixture("performance.json")
    data["observations"][0]["metrics"].append(data["observations"][0]["metrics"][0])

    with pytest.raises(ValidationError, match="metric name and aggregation pairs must be unique"):
        Bundle.model_validate(data)


def test_inverted_run_timestamps_are_rejected() -> None:
    data = load_fixture("performance.json")
    data["run"]["completed_at"] = "2026-07-23T13:01:02Z"

    with pytest.raises(ValidationError, match="completed_at must not precede started_at"):
        Bundle.model_validate(data)


def test_vllm_requires_commit_or_image() -> None:
    data = load_fixture("performance.json")
    data["run"]["vllm"] = {}

    with pytest.raises(ValidationError, match="at least one of commit or image is required"):
        Bundle.model_validate(data)


def test_checked_in_schema_is_current() -> None:
    assert SCHEMA_PATH.read_text() == render_bundle_v1_schema()
