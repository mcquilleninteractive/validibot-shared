"""Tests for validation envelope models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from validibot_shared.canonicalization import (
    compute_callback_nonce_commitment,
    sha256_hex_for_model,
)
from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    InputFileItem,
    MessageLocation,
    ResourceFileItem,
    Severity,
    SupportedMimeType,
    ValidationArtifact,
    ValidationCallback,
    ValidationInputEnvelope,
    ValidationMessage,
    ValidationOutputEnvelope,
    ValidationStatus,
    ValidatorType,
)

TEST_CALLBACK_NONCE = "A" * 43
TEST_CALLBACK_NONCE_COMMITMENT = compute_callback_nonce_commitment(
    TEST_CALLBACK_NONCE,
)


def _base_input_envelope_kwargs():
    return {
        "run_id": "run-42",
        "validator": {
            "id": "val-1",
            "type": ValidatorType.ENERGYPLUS,
            "version": "1.0",
        },
        "org": {"id": "org-1", "name": "ValidiBot"},
        "workflow": {"id": "wf-1", "step_id": "step-1", "step_name": "Validate"},
        "input_files": [
            InputFileItem(
                name="model.idf",
                mime_type=SupportedMimeType.ENERGYPLUS_IDF,
                role="primary-model",
                port_key="primary_model",
                uri="gs://bucket/model.idf",
                size_bytes=123,
                sha256="1" * 64,
                storage_version="1700000000000000",
            )
        ],
        "context": ExecutionContext(
            callback_url="https://example.com/callback",
            callback_id="execution-attempt-attempt-42",
            callback_nonce=TEST_CALLBACK_NONCE,
            callback_nonce_commitment=TEST_CALLBACK_NONCE_COMMITMENT,
            execution_bundle_uri="gs://bucket/run-42/",
            execution_attempt_id="attempt-42",
            step_run_id="step-run-42",
            attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
            expected_output_uri="gs://bucket/run-42/output.json",
        ),
    }


def _output_identity_kwargs():
    """Return the immutable execution-attempt identity required on outputs."""
    return {
        "step_run_id": "step-run-99",
        "execution_attempt_id": "attempt-99",
        "attempt_contract_version": ATTEMPT_CONTRACT_VERSION,
        "input_envelope_sha256": "a" * 64,
        "output_uri": "gs://bucket/run-99/output.json",
    }


def test_validation_input_envelope_defaults_schema_version():
    """ValidationInputEnvelope should have default schema version."""
    envelope = ValidationInputEnvelope(**_base_input_envelope_kwargs())

    assert envelope.schema_version == "validibot.input.v1"
    assert envelope.input_files[0].role == "primary-model"
    assert envelope.input_files[0].port_key == "primary_model"
    assert envelope.inputs == {}


def test_strict_attempt_fixture_has_the_cross_repo_canonical_digest():
    """All producers and consumers must hash the same attempt fixture bytes."""
    envelope = ValidationInputEnvelope(
        run_id="run-fixture",
        validator={
            "id": "validator-fixture",
            "type": ValidatorType.FMU,
            "version": "1",
        },
        org={"id": "org-fixture", "name": "Fixture Org"},
        workflow={
            "id": "workflow-fixture",
            "step_id": "step-fixture",
            "step_name": "Fixture Step",
        },
        input_files=[
            {
                "name": "model.fmu",
                "mime_type": SupportedMimeType.FMU,
                "role": "fmu",
                "port_key": "fmu_model",
                "uri": "gs://fixture/runs/run-fixture/model.fmu",
                "size_bytes": 12,
                "sha256": "1" * 64,
                "storage_version": "1700000000000000",
            },
        ],
        inputs={"alpha": 1},
        context={
            "execution_attempt_id": "attempt-fixture",
            "step_run_id": "step-run-fixture",
            "attempt_contract_version": ATTEMPT_CONTRACT_VERSION,
            "expected_output_uri": "gs://fixture/runs/run-fixture/output.json",
            "execution_bundle_uri": "gs://fixture/runs/run-fixture/",
            "callback_url": "https://example.com/callback",
            "callback_id": "execution-attempt-attempt-fixture",
            "callback_nonce": ("AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"),
            "callback_nonce_commitment": compute_callback_nonce_commitment(
                "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
            ),
        },
    )

    assert sha256_hex_for_model(envelope) == (
        "a212b9aaad3aca508a88608d70fd75b5642a8c0e20876308887789dc5bbfb64d"
    )


def test_input_file_item_requires_and_carries_port_key():
    """Every submitted file must carry its declared selection identity."""
    item = InputFileItem(
        name="model.idf",
        mime_type=SupportedMimeType.ENERGYPLUS_IDF,
        role="primary-model",
        port_key="primary_model",
        uri="gs://bucket/model.idf",
        size_bytes=123,
        sha256="1" * 64,
        storage_version="1700000000000000",
    )

    assert item.port_key == "primary_model"


def test_resource_file_item_requires_and_carries_port_key():
    """Every resource file must carry its declared selection identity."""
    item = ResourceFileItem(
        id="resource-1",
        name="weather.epw",
        type="energyplus_weather",
        port_key="weather_file",
        uri="gs://bucket/weather.epw",
        size_bytes=456,
        sha256="2" * 64,
        storage_version="1700000000000001",
    )

    assert item.port_key == "weather_file"


def test_input_file_item_forbids_extra_fields():
    """InputFileItem should forbid extra fields."""
    with pytest.raises(ValidationError):
        InputFileItem(
            name="model.idf",
            mime_type=SupportedMimeType.ENERGYPLUS_IDF,
            role="primary-model",
            port_key="primary_model",
            uri="gs://bucket/model.idf",
            size_bytes=123,
            sha256="1" * 64,
            storage_version="1700000000000000",
            extra_field="not-allowed",
        )


@pytest.mark.parametrize("missing", ["size_bytes", "sha256", "storage_version"])
def test_input_file_item_requires_every_integrity_field(missing):
    """A producer cannot emit a weaker file contract by omitting identity."""
    payload = {
        "name": "model.idf",
        "mime_type": SupportedMimeType.ENERGYPLUS_IDF,
        "role": "primary-model",
        "port_key": "primary_model",
        "uri": "gs://bucket/model.idf",
        "size_bytes": 123,
        "sha256": "1" * 64,
        "storage_version": "1700000000000000",
    }
    payload.pop(missing)

    with pytest.raises(ValidationError):
        InputFileItem(**payload)


@pytest.mark.parametrize("name", ["", ".", "..", "../model.idf", "a/b.idf", "a\\b.idf"])
def test_file_item_names_must_be_safe_leaf_names(name):
    """Logical names cannot redirect backend materialization outside its workspace."""
    with pytest.raises(ValidationError):
        InputFileItem(
            name=name,
            mime_type=SupportedMimeType.ENERGYPLUS_IDF,
            port_key="primary_model",
            uri="gs://bucket/model.idf",
            size_bytes=123,
            sha256="1" * 64,
            storage_version="1700000000000000",
        )


def test_file_item_rejects_malformed_integrity_values():
    """Negative sizes, non-SHA digests, and empty versions fail at parsing."""
    with pytest.raises(ValidationError):
        InputFileItem(
            name="model.idf",
            mime_type=SupportedMimeType.ENERGYPLUS_IDF,
            port_key="primary_model",
            uri="gs://bucket/model.idf",
            size_bytes=-1,
            sha256="not-a-sha256",
            storage_version="",
        )


def test_validation_artifact_requires_byte_and_storage_identity():
    """Output artifacts use the same mandatory integrity contract as inputs."""
    artifact = ValidationArtifact(
        name="report.csv",
        type="timeseries-csv",
        mime_type="text/csv",
        uri="gs://bucket/outputs/report.csv",
        size_bytes=456,
        sha256="2" * 64,
        storage_version="1700000000000001",
    )

    assert artifact.size_bytes == 456
    assert artifact.sha256 == "2" * 64

    with pytest.raises(ValidationError):
        ValidationArtifact(
            name="report.csv",
            type="timeseries-csv",
            uri="gs://bucket/outputs/report.csv",
        )


def test_validation_message_location_optional_fields():
    """MessageLocation should support optional fields."""
    location = MessageLocation(
        file_role="weather",
        line=10,
        column=2,
        path="/Objects/1",
    )
    assert location.file_role == "weather"


def test_validation_output_envelope_defaults_and_status_enum():
    """ValidationOutputEnvelope should have defaults and use status enum."""
    timing = {
        "queued_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        "started_at": datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
        "finished_at": datetime(2024, 1, 1, 12, 2, 0, tzinfo=UTC),
    }

    envelope = ValidationOutputEnvelope(
        run_id="run-99",
        **_output_identity_kwargs(),
        validator={
            "id": "val-1",
            "type": ValidatorType.ENERGYPLUS,
            "version": "1.0",
        },
        status=ValidationStatus.SUCCESS,
        timing=timing,
    )

    assert envelope.schema_version == "validibot.output.v1"
    assert envelope.messages == []
    assert envelope.metrics == []
    assert envelope.outputs is None


def test_validation_output_envelope_rejects_invalid_status():
    """ValidationOutputEnvelope should reject invalid status."""
    timing = {"queued_at": None, "started_at": None, "finished_at": None}

    with pytest.raises(ValidationError):
        ValidationOutputEnvelope(
            run_id="run-100",
            **_output_identity_kwargs(),
            validator={
                "id": "val-1",
                "type": ValidatorType.ENERGYPLUS,
                "version": "1.0",
            },
            status="bad-status",  # type: ignore[arg-type]
            timing=timing,
        )


def test_validation_callback_serialization():
    """ValidationCallback should serialize correctly."""
    callback = ValidationCallback(
        run_id="run-101",
        callback_id="execution-attempt-attempt-101",
        callback_nonce=TEST_CALLBACK_NONCE,
        status=ValidationStatus.FAILED_RUNTIME,
        result_uri="gs://bucket/run-101/output.json",
    )

    assert callback.status is ValidationStatus.FAILED_RUNTIME


def test_validation_message_enforces_severity_enum():
    """ValidationMessage should enforce severity enum."""
    message = ValidationMessage(
        severity=Severity.ERROR,
        code="E100",
        text="Something went wrong",
    )

    assert message.severity is Severity.ERROR

    with pytest.raises(ValidationError):
        ValidationMessage(severity="fatal", text="not allowed")  # type: ignore[arg-type]
