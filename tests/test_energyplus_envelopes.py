"""Verify the strict EnergyPlus input and output wire contracts.

These tests protect the cross-repository boundary shared by Django and the
EnergyPlus backend.  Extra fields must remain forbidden while review settings,
execution evidence, nullable metrics, and artifact presence round-trip exactly.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from validibot_shared.canonicalization import compute_callback_nonce_commitment
from validibot_shared.energyplus.envelopes import (
    EnergyPlusInputEnvelope,
    EnergyPlusInputs,
    EnergyPlusOutputEnvelope,
    EnergyPlusOutputs,
)
from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    InputFileItem,
    SupportedMimeType,
    ValidationStatus,
    ValidatorType,
)

# Test constants to avoid magic values
DEFAULT_TIMESTEP_PER_HOUR = 4
TEST_TIMESTEP_PER_HOUR = 6
TEST_ELECTRICITY_KWH = 123.4
TEST_EXECUTION_SECONDS = 12.5
TEST_EUI_KWH_M2 = 10.5
TEST_CALLBACK_NONCE = "A" * 43
TEST_CALLBACK_NONCE_COMMITMENT = compute_callback_nonce_commitment(
    TEST_CALLBACK_NONCE,
)


def _base_input_envelope_kwargs():
    return {
        "run_id": "run-1",
        "validator": {
            "id": "val-1",
            "type": ValidatorType.ENERGYPLUS,
            "version": "1.0",
        },
        "org": {"id": "org-1", "name": "ValidiBot"},
        "workflow": {"id": "wf-1", "step_id": "step-1", "step_name": "EnergyPlus"},
        "input_files": [
            InputFileItem(
                name="model.idf",
                mime_type=SupportedMimeType.ENERGYPLUS_IDF,
                role="primary-model",
                uri="gs://bucket/model.idf",
                size_bytes=123,
                sha256="1" * 64,
                storage_version="1700000000000000",
            )
        ],
        "context": ExecutionContext(
            callback_url="https://example.com/callback",
            callback_id="execution-attempt-attempt-1",
            callback_nonce=TEST_CALLBACK_NONCE,
            callback_nonce_commitment=TEST_CALLBACK_NONCE_COMMITMENT,
            execution_bundle_uri="gs://bucket/run-1/",
            execution_attempt_id="attempt-1",
            step_run_id="step-run-1",
            attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
            expected_output_uri="gs://bucket/run-1/output.json",
            timeout_seconds=600,
            tags=["smoke"],
        ),
    }


def test_energyplus_inputs_defaults():
    """EnergyPlusInputs should have sensible defaults."""
    inputs = EnergyPlusInputs()

    assert inputs.timestep_per_hour == DEFAULT_TIMESTEP_PER_HOUR
    assert inputs.run_period_days is None
    assert inputs.invocation_mode == "cli"
    assert inputs.idf_checks == []
    assert inputs.run_simulation is True
    assert inputs.review_profile == "standard"


def test_energyplus_inputs_validation():
    """EnergyPlusInputs should reject invalid values."""
    with pytest.raises(ValidationError):
        EnergyPlusInputs(timestep_per_hour=0)

    with pytest.raises(ValidationError):
        EnergyPlusInputs(invocation_mode="invalid-mode")

    with pytest.raises(ValidationError):
        EnergyPlusInputs(idf_checks=["not-a-review-check"])

    with pytest.raises(ValidationError):
        EnergyPlusInputs(review_profile="not-a-profile")

    with pytest.raises(ValidationError):
        EnergyPlusInputs(unknown="nope")


def test_energyplus_inputs_accept_review_readiness_settings():
    """Review settings should cross the wire as a strict typed contract."""
    inputs = EnergyPlusInputs(
        idf_checks=["duplicate-names", "hvac-sizing", "schedule-coverage"],
        run_simulation=False,
        review_profile="leed_review",
    )

    assert inputs.idf_checks == [
        "duplicate-names",
        "hvac-sizing",
        "schedule-coverage",
    ]
    assert inputs.run_simulation is False
    assert inputs.review_profile == "leed_review"


def test_energyplus_input_envelope_uses_typed_inputs():
    """EnergyPlusInputEnvelope should parse inputs into EnergyPlusInputs."""
    data = _base_input_envelope_kwargs()
    envelope = EnergyPlusInputEnvelope(
        **data,
        inputs={"timestep_per_hour": TEST_TIMESTEP_PER_HOUR},
    )

    assert isinstance(envelope.inputs, EnergyPlusInputs)
    assert envelope.inputs.timestep_per_hour == TEST_TIMESTEP_PER_HOUR


def test_energyplus_input_envelope_rejects_invalid_inputs():
    """EnergyPlusInputEnvelope should reject invalid input configurations."""
    data = _base_input_envelope_kwargs()

    with pytest.raises(ValidationError):
        EnergyPlusInputEnvelope(
            **data,
            inputs={"timestep_per_hour": 1, "invocation_mode": "bad"},
        )


def test_energyplus_outputs_compose_nested_models():
    """EnergyPlusOutputs should compose nested models correctly."""
    outputs = EnergyPlusOutputs(
        outputs={"eplusout_sql": "outputs/eplusout.sql", "eplusout_err": None},
        metrics={"site_electricity_kwh": TEST_ELECTRICITY_KWH},
        logs={"stdout_tail": "log tail"},
        energyplus_returncode=0,
        execution_seconds=TEST_EXECUTION_SECONDS,
        invocation_mode="python_api",
        energyplus_binary_version="25.2.0",
        energyplus_binary_build="cf7368216c",
        idd_version="25.2.0",
        idd_build="cf7368216c",
        idd_path="/opt/energyplus/Energy+.idd",
        idf_version="25.2",
        version_match=True,
        completed_successfully=True,
        warning_count=2,
        review_issue_count=1,
        has_sql_output=True,
        has_err_output=True,
    )

    assert isinstance(outputs.outputs.eplusout_sql, Path)
    assert outputs.metrics.site_electricity_kwh == TEST_ELECTRICITY_KWH
    assert outputs.logs.stdout_tail == "log tail"
    assert outputs.execution_seconds == TEST_EXECUTION_SECONDS
    assert outputs.version_match is True
    assert outputs.completed_successfully is True
    assert outputs.warning_count == 2
    assert outputs.has_sql_output is True


def test_energyplus_outputs_forbid_extra_fields():
    """EnergyPlusOutputs should forbid extra fields."""
    with pytest.raises(ValidationError):
        EnergyPlusOutputs(
            energyplus_returncode=0,
            execution_seconds=1.0,
            invocation_mode="cli",
            unknown="nope",
        )


def test_energyplus_output_envelope_accepts_typed_outputs():
    """EnergyPlusOutputEnvelope should accept typed outputs."""
    envelope = EnergyPlusOutputEnvelope(
        run_id="run-2",
        step_run_id="step-run-2",
        execution_attempt_id="attempt-2",
        attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
        input_envelope_sha256="a" * 64,
        output_uri="gs://bucket/run-2/output.json",
        validator={
            "id": "val-1",
            "type": ValidatorType.ENERGYPLUS,
            "version": "1.0",
        },
        status=ValidationStatus.SUCCESS,
        timing={"queued_at": None, "started_at": None, "finished_at": None},
        outputs={
            "outputs": {"eplusout_sql": "outputs/eplusout.sql"},
            "metrics": {"site_eui_kwh_m2": TEST_EUI_KWH_M2},
            "energyplus_returncode": 0,
            "execution_seconds": 3.2,
            "invocation_mode": "cli",
        },
    )

    assert isinstance(envelope.outputs, EnergyPlusOutputs)
    assert envelope.outputs.outputs.eplusout_sql.name == "eplusout.sql"
    assert envelope.outputs.metrics.site_eui_kwh_m2 == TEST_EUI_KWH_M2
