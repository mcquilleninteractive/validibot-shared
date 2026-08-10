"""
Pydantic envelopes for FMU Advanced validator jobs.

The FMU validator is an Advanced validator - it runs in a separate
container/service rather than within the Django app. These schemas define
the contract between Django and the FMU validator container:
- Input envelope: FMU URI plus resolved input values and simulation config
- Output envelope: FMU outputs, metrics, messages, and artifacts

Inputs/outputs use native FMU variable names as declared in the FMU's
modelDescription.xml (e.g. "h" or "Temperature"). The core Django app
resolves these names when building the envelope and when ingesting results.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    InputFileItem,
    SupportedMimeType,
    ValidationInputEnvelope,
    ValidationOutputEnvelope,
    ValidatorType,
)


class FMUSimulationConfig(BaseModel):
    """Simulation configuration for FMU runs."""

    start_time: float = Field(
        default=0.0,
        description="Simulation start time (seconds).",
        ge=0,
    )
    stop_time: float = Field(
        default=1.0,
        description="Simulation stop time (seconds).",
        gt=0,
    )
    step_size: float = Field(
        default=0.01,
        description="Communication step size (seconds).",
        gt=0,
    )
    tolerance: float | None = Field(
        default=None,
        description="Solver tolerance, if supported by the FMU.",
        gt=0,
    )


class FMUInputs(BaseModel):
    """Resolved inputs plus simulation config, keyed by native FMU variable names."""

    input_values: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Input values keyed by native FMU variable "
            "names (from modelDescription.xml)."
        ),
    )
    simulation: FMUSimulationConfig = Field(
        default_factory=FMUSimulationConfig,
        description="Simulation time/step configuration.",
    )
    output_variables: list[str] = Field(
        default_factory=list,
        description=(
            "Native FMU variable names to capture as outputs. "
            "Empty means all output variables from modelDescription.xml."
        ),
    )


class FMUOutputs(BaseModel):
    """FMU execution results keyed by native FMU variable names."""

    output_values: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Output values keyed by native FMU variable "
            "names (from modelDescription.xml)."
        ),
    )
    fmu_guid: str | None = Field(default=None, description="FMU GUID, if reported.")
    fmi_version: str | None = Field(default=None, description="FMI version.")
    model_name: str | None = Field(default=None, description="FMU model name.")
    execution_seconds: float = Field(
        description="Wall-clock execution time (seconds).",
        ge=0,
    )
    simulation_time_reached: float = Field(
        description="Simulation time reached before completion/stop.",
        ge=0,
    )
    fmu_log: str | None = Field(
        default=None,
        description="Optional FMU log output.",
    )


class FMUInputEnvelope(ValidationInputEnvelope):
    """Input envelope for FMU validator containers."""

    inputs: FMUInputs


class FMUOutputEnvelope(ValidationOutputEnvelope):
    """Output envelope from FMU validator containers.

    Note: outputs can be None for failure cases where simulation didn't complete.
    """

    outputs: FMUOutputs | None = None


def build_fmu_input_envelope(
    *,
    run_id: str,
    validator,
    org_id: str,
    org_name: str,
    workflow_id: str,
    step_id: str,
    step_name: str | None,
    fmu_uri: str,
    fmu_size_bytes: int,
    fmu_sha256: str,
    fmu_storage_version: str,
    input_values: dict[str, Any],
    callback_url: str,
    execution_bundle_uri: str,
    execution_attempt_id: str,
    step_run_id: str,
    expected_output_uri: str,
    callback_id: str | None = None,
    callback_nonce: str | None = None,
    callback_nonce_commitment: str | None = None,
    skip_callback: bool = False,
    simulation: FMUSimulationConfig | None = None,
    output_variables: list[str] | None = None,
) -> FMUInputEnvelope:
    """
    Build an FMUInputEnvelope from Django validation data.

    Args:
        run_id: ValidationRun ID
        validator: Validator-like object (id/type/version attrs)
        org_id: Organization ID
        org_name: Organization name
        workflow_id: Workflow ID
        step_id: Workflow step ID
        step_name: Optional step name
        fmu_uri: FMU storage URI (gs://... or local path in dev)
        fmu_size_bytes: Expected exact FMU size and streaming ceiling
        fmu_sha256: Expected SHA-256 of the FMU bytes
        fmu_storage_version: Immutable provider version for the FMU object
        input_values: Resolved inputs keyed by native FMU variable name
        callback_url: URL to POST callback
        callback_id: Attempt-bound callback idempotency identifier
        callback_nonce: Per-attempt secret returned in the callback payload
        callback_nonce_commitment: Public commitment to ``callback_nonce``
        skip_callback: True for synchronous execution
        execution_bundle_uri: Base URI/path for this run's files
        simulation: Optional FMUSimulationConfig
        output_variables: Optional list of native FMU variable
            names to capture (empty=all outputs)
    """

    input_files = [
        InputFileItem(
            name="model.fmu",
            mime_type=SupportedMimeType.FMU,
            role="fmu",
            port_key="fmu_model",
            uri=fmu_uri,
            size_bytes=fmu_size_bytes,
            sha256=fmu_sha256,
            storage_version=fmu_storage_version,
        )
    ]

    envelope_inputs = FMUInputs(
        input_values=input_values,
        simulation=simulation or FMUSimulationConfig(),
        output_variables=output_variables or [],
    )

    context = ExecutionContext(
        execution_attempt_id=execution_attempt_id,
        step_run_id=step_run_id,
        attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
        expected_output_uri=expected_output_uri,
        callback_id=callback_id,
        callback_nonce=callback_nonce,
        callback_nonce_commitment=callback_nonce_commitment,
        callback_url=callback_url,
        execution_bundle_uri=execution_bundle_uri,
        skip_callback=skip_callback,
    )

    envelope = FMUInputEnvelope(
        run_id=run_id,
        validator={
            "id": str(validator.id),
            "type": ValidatorType(validator.validation_type),
            "version": getattr(validator, "version", "1.0.0"),
        },
        org={
            "id": org_id,
            "name": org_name,
        },
        workflow={
            "id": workflow_id,
            "step_id": step_id,
            "step_name": step_name,
        },
        input_files=input_files,
        inputs=envelope_inputs,
        context=context,
    )

    return envelope
