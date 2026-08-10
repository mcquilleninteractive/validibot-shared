"""
Pydantic schemas for validator backend execution envelopes.

These schemas define the contract between Django-side advanced validators and
external validator backends. In the core ``validibot`` codebase,
``AdvancedValidator`` is the trusted Django-side class that prepares the run,
builds the envelope, launches external work through an execution backend, and
processes the output. A validator backend, or future ``ValidatorBackend``
protocol, is the external implementation it delegates to, usually a container
or cloud job. The backend receives only this envelope boundary, not the full
Django submission, workflow, permissions, or billing state.

This library is used by both the Django app and validator backends
to ensure type safety and contract consistency across the execution boundary.

## Deployment Modes

This module supports multiple deployment modes:

1. **GCP deployment**: Uses gs:// URIs for Google Cloud Storage
2. **Self-hosted Docker** (default): Uses file:// URIs for local filesystem

The envelope schemas are storage-agnostic - they accept any valid URI. The
actual storage handling is done by the validators' storage_client module.

## Architecture Overview

This module provides a type-safe interface for communication between the Django
app and validator backends:

**GCP Mode (async with callbacks):**
1. Django creates input.json with files, config, callback URL
2. Django uploads to GCS and triggers validator backend runtime
3. Validator downloads inputs, runs validation, uploads outputs
4. Validator POSTs minimal callback to Django when complete
5. Django receives callback and loads full output.json from GCS

**Self-hosted Mode (sync execution):**
1. Django creates input.json with files, config
2. Django uploads to local storage and runs Docker container synchronously
3. Validator reads inputs, runs validation, writes outputs to local storage
4. Docker container exits, Django reads output.json directly

## Why Three Separate Fields: input_files, resource_files, and inputs?

- **input_files**: User-submitted files (IDF, FMU, XML, etc.)
  - Files uploaded by users as part of their submission
  - Role field distinguishes file purposes (e.g., 'primary-model')

- **resource_files**: Auxiliary files needed by validators (weather files, libraries)
  - Managed by system admins, not user-submitted
  - Examples: EPW weather files for EnergyPlus, FMU libraries for FMU
  - Stored in ValidatorResourceFile model with org/system scoping

- **inputs**: Domain-specific configuration parameters
  - Base class uses dict[str, Any] for flexibility
  - Subclasses override with typed Pydantic models (e.g., EnergyPlusInputs)
  - Examples: timestep settings, output variables, simulation options

This separation keeps user submissions, system resources, and config distinct.

## Why Separate outputs Field?

- **messages/metrics/artifacts**: Generic outputs (errors, warnings, values)
  - Available on all validators for consistent reporting

- **outputs**: Domain-specific detailed results
  - Base class uses dict[str, Any] | None for flexibility
  - Subclasses override with typed models (e.g., EnergyPlusOutputs
    with returncode, logs, file paths)
  - Optional because not all validators produce detailed domain-specific data

## Subclassing Pattern

Domain-specific validators (energyplus, fmu, xml) create typed subclasses:

```python
# In energyplus/envelopes.py
class EnergyPlusInputs(BaseModel):
    timestep_per_hour: int = 4
    invocation_mode: Literal["python_api", "cli"] = "cli"
    # ... other EnergyPlus-specific config

class EnergyPlusInputEnvelope(ValidationInputEnvelope):
    inputs: EnergyPlusInputs  # Override dict[str, Any] with typed version!

class EnergyPlusOutputs(BaseModel):
    energyplus_returncode: int
    execution_seconds: float
    # ... other EnergyPlus-specific results

class EnergyPlusOutputEnvelope(ValidationOutputEnvelope):
    outputs: EnergyPlusOutputs  # Override dict[str, Any] with typed version!
```

Django deserializes using the correct subclass based on validator.type.

## Why ValidationCallback?

The callback is a minimal async notification sent from the validator backend
back to the Django app when work completes. It contains only:
- run_id: Which job finished
- callback_id: Which execution attempt is delivering the result
- callback_nonce: Proof that the sender received that attempt's input envelope
- status: success/failed_validation/failed_runtime/cancelled
- result_uri: Storage path to full output.json

This avoids redundant data transfer since the full output.json is already in storage.
The callback enables async execution (validator POSTs when done) instead of the
Django app having to poll job status repeatedly.

See docs/adr/2025-12-04-validator-job-interface.md in the validibot repository
for the full specification.
"""

from __future__ import annotations

import hmac
from datetime import datetime  # noqa: TC003
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from validibot_shared.canonicalization import compute_callback_nonce_commitment

ATTEMPT_CONTRACT_VERSION = "validibot.attempt.v2"
CALLBACK_NONCE_MIN_LENGTH = 43
CALLBACK_NONCE_MAX_LENGTH = 512
CALLBACK_NONCE_PATTERN = r"^[A-Za-z0-9_-]+$"

# ==============================================================================
# Shared Enums
# ==============================================================================


class Severity(str, Enum):
    """Severity level for validation messages."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ValidatorType(str, Enum):
    """
    Canonical validator types used across Django and validator backends.

    These values align with Django's ValidationType TextChoices and should be
    used anywhere we serialize validator identifiers in envelopes.
    """

    BASIC = "BASIC"
    JSON_SCHEMA = "JSON_SCHEMA"
    XML_SCHEMA = "XML_SCHEMA"
    SCHEMATRON = "SCHEMATRON"
    SHACL = "SHACL"
    ENERGYPLUS = "ENERGYPLUS"
    FMU = "FMU"
    CUSTOM_VALIDATOR = "CUSTOM_VALIDATOR"
    AI_ASSIST = "AI_ASSIST"
    PORTFOLIO_MANAGER = "PORTFOLIO_MANAGER"
    PDF = "PDF"


# ==============================================================================
# Input Envelope (validibot.input.v1)
# ==============================================================================


class SupportedMimeType(str, Enum):
    """
    Supported MIME types for file inputs.

    We only accept specific file types that our validators know how to process.
    """

    # XML documents
    APPLICATION_XML = "application/xml"
    TEXT_XML = "text/xml"

    # EnergyPlus files
    ENERGYPLUS_IDF = "application/vnd.energyplus.idf"  # IDF text format
    ENERGYPLUS_EPJSON = "application/vnd.energyplus.epjson"  # epJSON format
    ENERGYPLUS_EPW = "application/vnd.energyplus.epw"  # Weather data

    # FMU files
    FMU = "application/vnd.fmi.fmu"  # Functional Mock-up Unit

    # RDF serializations (SHACL validator). The concrete parse format is
    # carried by SHACLInputs.submission_format; these MIME types let the RDF
    # submission ride the typed InputFileItem.mime_type field like any other
    # validator input.
    RDF_TURTLE = "text/turtle"
    RDF_XML = "application/rdf+xml"
    RDF_JSON_LD = "application/ld+json"
    RDF_N_TRIPLES = "application/n-triples"
    RDF_N_QUADS = "application/n-quads"

    # ENERGY STAR Portfolio Manager report carriers.
    MICROSOFT_EXCEL_XLS = "application/vnd.ms-excel"
    MICROSOFT_EXCEL_XLSX = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    APPLICATION_ZIP = "application/zip"
    APPLICATION_JSON = "application/json"

    # Engineering document packages and neutral CAD payloads.
    APPLICATION_PDF = "application/pdf"
    MODEL_STEP = "model/step"
    APPLICATION_P21 = "application/p21"


def _safe_leaf_name(value: str) -> str:
    """Return ``value`` when it is one safe logical filename.

    Storage URIs carry provider paths; item names are deliberately only leaf
    names so a backend can materialize them below its own attempt workspace.
    """
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        msg = f"File item name must be a safe logical leaf name: {value!r}"
        raise ValueError(msg)
    return value


class IntegrityBoundFile(BaseModel):
    """Required byte identity shared by every file-bearing envelope item.

    ``size_bytes`` is both the expected exact length and the runtime's hard
    streaming ceiling. ``sha256`` identifies the bytes the producer committed
    to. ``storage_version`` pins the provider-specific immutable object
    identity (for example a GCS generation or ``sha256:<digest>`` for an
    attempt-local read-only file).
    """

    size_bytes: int = Field(
        ge=0,
        description="Expected exact file size and hard streaming ceiling.",
    )
    sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Lowercase SHA-256 hex digest of the exact file bytes.",
    )
    storage_version: str = Field(
        min_length=1,
        max_length=512,
        description="Provider-specific immutable object/version identity.",
    )

    model_config = {"extra": "forbid"}


class InputFileItem(IntegrityBoundFile):
    """
    A user-submitted file input for the validator.

    Files are stored in GCS/local storage and referenced by URI. The 'role' field
    allows validators to understand what each file is for (e.g., 'primary-model').

    Note: Auxiliary files like weather files are in resource_files, not input_files.
    """

    name: str = Field(description="Safe logical leaf name of the file")

    mime_type: SupportedMimeType = Field(description="MIME type of the file")

    role: str | None = Field(
        default=None,
        description="Validator-specific role (e.g., 'primary-model', 'config')",
    )

    port_key: str | None = Field(
        default=None,
        description=(
            "Declared Validibot file-port key that produced this envelope item "
            "(e.g., 'primary_model')."
        ),
    )

    uri: str = Field(
        description="Storage URI to the file (gs:// or file:// for self-hosted)"
    )

    @field_validator("name")
    @classmethod
    def _validate_safe_name(cls, value: str) -> str:
        """Reject paths so runtimes choose the destination directory."""
        return _safe_leaf_name(value)


class ResourceFileItem(IntegrityBoundFile):
    """
    A resource file needed by the validator.

    Resource files are auxiliary files that validators need to run, but are not
    submission data. Examples: weather files for EnergyPlus, libraries for FMU.

    Unlike InputFileItem (which is per-submission), resource files are reusable
    across validations and managed via the Validator Library UI in Django.

    The 'type' field indicates what kind of resource this is (weather, library, etc.)
    and validators use this to locate the appropriate file for their needs.
    """

    id: str = Field(description="Resource file UUID from Django database")

    name: str = Field(description="Safe logical leaf name of the resource")

    type: str = Field(
        description="Resource type (e.g., 'weather', 'library', 'config')"
    )

    port_key: str | None = Field(
        default=None,
        description=(
            "Declared Validibot file-port key that produced this resource item "
            "(e.g., 'weather_file')."
        ),
    )

    uri: str = Field(
        description="Storage URI to the file (gs:// or file:// for self-hosted)"
    )

    @field_validator("name")
    @classmethod
    def _validate_safe_name(cls, value: str) -> str:
        """Reject resource names that could escape the runtime workspace."""
        return _safe_leaf_name(value)

    model_config = {"extra": "forbid"}


class ValidatorInfo(BaseModel):
    """
    Information about the validator being executed.

    This identifies which validator backend to run and which version.
    The 'type' field determines:
    1. Which validator backend to run (e.g., 'validibot-validator-backend-energyplus')
    2. Which envelope subclass Django uses for deserialization
       (EnergyPlusInputEnvelope, FMUInputEnvelope, etc.)

    This class appears in both input and output envelopes to maintain traceability
    of which validator version produced which results.
    """

    id: str = Field(description="Validator UUID from Django database")

    type: ValidatorType = Field(
        description="Validator type (e.g., 'ENERGYPLUS', 'FMU', 'JSON_SCHEMA')"
    )

    version: str = Field(description="Validator version (e.g., '1.0.0')")

    model_config = {"extra": "forbid"}


class OrganizationInfo(BaseModel):
    """
    Information about the organization running the validation.

    Included for logging, debugging, and future multi-tenancy features.
    The name is redundant with ID but helpful for human-readable logs.
    """

    id: str = Field(description="Organization UUID from Django database")

    name: str = Field(description="Organization name (for human-readable logs)")

    model_config = {"extra": "forbid"}


class WorkflowInfo(BaseModel):
    """
    Information about the workflow and step being executed.

    Validators are executed as steps within larger workflows. This metadata
    enables tracing validation results back to their workflow context for:
    - Debugging (which workflow triggered this validation?)
    - Auditing (track all validations in a workflow)
    - UI display (show validation status within workflow visualization)
    """

    id: str = Field(description="Workflow UUID")

    step_id: str = Field(description="Workflow step UUID")

    step_name: str | None = Field(default=None, description="Human-readable step name")

    model_config = {"extra": "forbid"}


class ExecutionContext(BaseModel):
    """
    Execution context and callback information.

    This provides the validator backend with everything it needs to:
    1. Download input files from storage (execution_bundle_uri)
    2. Upload output files to storage (execution_bundle_uri)
    3. Notify Django when complete (callback_url)
    4. Respect timeout constraints (timeout_seconds)
    """

    execution_attempt_id: str = Field(
        min_length=1,
        description="ExecutionAttempt UUID selected by the trusted application.",
    )

    step_run_id: str = Field(
        min_length=1,
        description="ValidationStepRun identity this attempt executes.",
    )

    attempt_contract_version: Literal["validibot.attempt.v2"] = Field(
        description="Strict attempt I/O contract version.",
    )

    expected_output_uri: str = Field(
        min_length=1,
        description="Exact output-envelope identity selected before dispatch.",
    )

    callback_id: str | None = Field(
        default=None,
        description=(
            "Unique identifier for this callback, used for idempotency. "
            "Generated at job launch and echoed back in the callback payload. "
            "The callback handler uses this to detect and ignore duplicate deliveries."
        ),
    )

    callback_nonce: str | None = Field(
        default=None,
        min_length=CALLBACK_NONCE_MIN_LENGTH,
        max_length=CALLBACK_NONCE_MAX_LENGTH,
        pattern=CALLBACK_NONCE_PATTERN,
        repr=False,
        description=(
            "Per-attempt secret returned only in the callback payload. The raw "
            "value is removed from canonical envelope hashing."
        ),
    )

    callback_nonce_commitment: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description=("Public domain-separated SHA-256 commitment to callback_nonce."),
    )

    callback_url: HttpUrl | None = Field(
        default=None,
        description="URL to POST callback when validation completes",
    )

    skip_callback: bool = Field(
        default=False,
        description=(
            "If True, skip POSTing callback to callback_url after completion. "
            "Useful for testing where polling GCS for output.json is preferred."
        ),
    )

    execution_bundle_uri: str = Field(
        description="Storage URI to the execution bundle directory (gs:// or file://)"
    )

    timeout_seconds: int = Field(
        default=3600, description="Maximum execution time in seconds"
    )

    tags: list[str] = Field(default_factory=list, description="Execution tags")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_callback_nonce_contract(self) -> ExecutionContext:
        """Require one matching nonce pair whenever callbacks are enabled."""
        has_nonce = self.callback_nonce is not None
        has_commitment = self.callback_nonce_commitment is not None
        if has_nonce != has_commitment:
            msg = (
                "callback_nonce and callback_nonce_commitment must be provided together"
            )
            raise ValueError(msg)

        if self.callback_nonce is not None:
            expected = compute_callback_nonce_commitment(self.callback_nonce)
            if not hmac.compare_digest(expected, self.callback_nonce_commitment or ""):
                msg = "callback_nonce_commitment does not match callback_nonce"
                raise ValueError(msg)

        callback_enabled = self.callback_url is not None and not self.skip_callback
        if callback_enabled and not self.callback_id:
            msg = "callback_id is required when callbacks are enabled"
            raise ValueError(msg)
        if callback_enabled and not has_nonce:
            msg = (
                "callback_nonce and callback_nonce_commitment are required when "
                "callbacks are enabled"
            )
            raise ValueError(msg)
        return self


class ValidationInputEnvelope(BaseModel):
    """
    Base input envelope for validator backend jobs (validibot.input.v1).

    This is written to storage as input.json by Django before triggering
    the validator backend.

    ## How Subclassing Works

    Domain-specific validators create subclasses that override the 'inputs' field
    with a typed Pydantic model. The base class uses dict[str, Any] for flexibility,
    but subclasses provide type safety:

    ```python
    class EnergyPlusInputEnvelope(ValidationInputEnvelope):
        inputs: EnergyPlusInputs  # Typed override!
    ```

    This pattern allows:
    - Generic base class for all validators (this class)
    - Type-safe domain-specific subclasses (EnergyPlusInputEnvelope,
      FMUInputEnvelope, etc.)
    - Django to serialize/deserialize using the correct subclass based on
      validator.type

    ## Fields That Never Change in Subclasses

    - input_files: All validators receive files the same way
    - context: All validators use the same execution context
    - validator/org/workflow: All validators need this metadata

    ## Fields That Subclasses Override

    - inputs: Domain-specific configuration (dict[str, Any] → EnergyPlusInputs, etc.)
    """

    schema_version: Literal["validibot.input.v1"] = "validibot.input.v1"

    run_id: str = Field(description="Unique run identifier (UUID)")

    validator: ValidatorInfo

    org: OrganizationInfo

    workflow: WorkflowInfo

    input_files: list[InputFileItem] = Field(
        default_factory=list,
        description="File inputs for the validator (GCS URIs with roles)",
    )

    resource_files: list[ResourceFileItem] = Field(
        default_factory=list,
        description=(
            "Resource files needed by the validator (weather, libraries, configs). "
            "These are auxiliary files managed via Validator Library, not "
            "submission data."
        ),
    )

    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description=("Domain-specific inputs (subclasses override with typed model)"),
    )

    context: ExecutionContext

    model_config = {"extra": "forbid"}


# ==============================================================================
# Output Envelope (validibot.output.v1)
# ==============================================================================


class ValidationStatus(str, Enum):
    """Validation output status."""

    SUCCESS = "success"  # Validation completed successfully, no errors
    FAILED_VALIDATION = "failed_validation"  # Validation found errors (user's fault)
    FAILED_RUNTIME = "failed_runtime"  # Runtime error in validator (system fault)
    CANCELLED = "cancelled"  # User or system cancelled the job


class MessageLocation(BaseModel):
    """Location information for a validation message."""

    file_role: str | None = Field(
        default=None, description="Input file role (references InputFileItem.role)"
    )
    line: int | None = Field(default=None, description="Line number")
    column: int | None = Field(default=None, description="Column number")
    path: str | None = Field(
        default=None, description="Object path or XPath-like identifier"
    )

    model_config = {"extra": "forbid"}


class ValidationMessage(BaseModel):
    """A validation finding, warning, or error."""

    severity: Severity

    code: str | None = Field(
        default=None, description="Error code (e.g., 'EP001', 'FMU_INIT_ERROR')"
    )

    text: str = Field(description="Human-readable message")

    location: MessageLocation | None = Field(
        default=None, description="Location of the issue"
    )

    tags: list[str] = Field(default_factory=list, description="Message tags/categories")

    model_config = {"extra": "forbid"}


class ValidationMetric(BaseModel):
    """A computed metric from the validation/simulation."""

    name: str = Field(description="Metric name (e.g., 'zone_temp_max')")

    value: float | int | str = Field(description="Metric value")

    unit: str | None = Field(default=None, description="Unit (e.g., 'C', 'kWh', 'm2')")

    category: str | None = Field(
        default=None, description="Category (e.g., 'comfort', 'energy', 'performance')"
    )

    tags: list[str] = Field(default_factory=list, description="Metric tags")

    model_config = {"extra": "forbid"}


class ValidationArtifact(IntegrityBoundFile):
    """A file artifact produced by the validator."""

    name: str = Field(description="Safe logical artifact leaf name")

    type: str = Field(
        description=(
            "Artifact type (e.g., 'simulation-db', 'report-html', 'timeseries-csv')"
        )
    )

    mime_type: str | None = Field(
        default=None, description="MIME type (e.g., 'application/x-sqlite3')"
    )

    uri: str = Field(
        description="Storage URI to the artifact (gs:// or file:// for self-hosted)"
    )

    @field_validator("name")
    @classmethod
    def _validate_safe_name(cls, value: str) -> str:
        """Reject artifact names that could be interpreted as paths."""
        return _safe_leaf_name(value)


class RawOutputs(BaseModel):
    """Information about raw output files."""

    format: Literal["directory", "archive"] = Field(
        description="Format of raw outputs (directory or archive)"
    )

    manifest_uri: str = Field(
        description="Storage URI to the manifest file (gs:// or file://)"
    )

    model_config = {"extra": "forbid"}


class ValidationTiming(BaseModel):
    """Timing information for the validation run."""

    queued_at: datetime | None = Field(
        default=None, description="When the job was queued (ISO8601)"
    )

    started_at: datetime | None = Field(
        default=None, description="When execution started (ISO8601)"
    )

    finished_at: datetime | None = Field(
        default=None, description="When execution finished (ISO8601)"
    )

    model_config = {"extra": "forbid"}


class ValidationOutputEnvelope(BaseModel):
    """
    Base output envelope for validator backend jobs (validibot.output.v1).

    This is written to storage as output.json by the validator backend
    after completion.

    ## How Subclassing Works

    Domain-specific validators create subclasses that override the 'outputs' field
    with a typed Pydantic model containing detailed domain-specific results:

    ```python
    class EnergyPlusOutputEnvelope(ValidationOutputEnvelope):
        outputs: EnergyPlusOutputs  # Typed override!
    ```

    This pattern allows:
    - Generic base class for all validators (this class)
    - Type-safe domain-specific subclasses (EnergyPlusOutputEnvelope,
      FMUOutputEnvelope, etc.)
    - Django to deserialize using the correct subclass based on validator.type

    ## Generic vs Domain-Specific Outputs

    All validators populate these **generic** fields:
    - status: SUCCESS/FAILED_VALIDATION/FAILED_RUNTIME/CANCELLED
    - messages: Errors, warnings, info (consistent across all validators)
    - metrics: Computed values like energy use, temperature ranges
    - artifacts: GCS URIs to output files (SQL, CSV reports, HTML visualizations)
    - timing: When the job was queued/started/finished

    Some validators also populate **domain-specific** outputs:
    - outputs: Detailed execution data (returncode, logs, file paths, etc.)
    - Optional because not all validators produce this level of detail

    ## Why Both metrics and outputs?

    - **metrics**: High-level computed values for UI display
      (energy use, peak temperature, etc.)
      - Always a flat list of name/value/unit tuples
      - Consistent format across all validators
      - Used for dashboards, comparisons, search

    - **outputs**: Detailed domain-specific execution data
      - Nested structure with validator-specific fields
      - Examples: EnergyPlus returncode, FMU logs, XML schema validation
      - Used for debugging, detailed analysis, reproducing results

    ## Why raw_outputs?

    Some validators produce many output files (EnergyPlus can create dozens).
    Instead of creating a ValidationArtifact for each one, we:
    1. Upload all files to GCS
    2. Create a manifest.json listing all files
    3. Set raw_outputs.manifest_uri to point to the manifest
    This keeps the envelope small while preserving access to all files.
    """

    schema_version: Literal["validibot.output.v1"] = "validibot.output.v1"

    run_id: str = Field(description="Unique run identifier (matches input)")

    step_run_id: str = Field(
        min_length=1,
        description="ValidationStepRun identity echoed from the input contract.",
    )

    execution_attempt_id: str = Field(
        min_length=1,
        description="ExecutionAttempt identity echoed from the input contract.",
    )

    attempt_contract_version: Literal["validibot.attempt.v2"] = Field(
        description="Strict attempt I/O contract version echoed from input.",
    )

    input_envelope_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Canonical SHA-256 of the exact parsed input envelope.",
    )

    output_uri: str = Field(
        min_length=1,
        description="Exact output-envelope URI selected by the input contract.",
    )

    validator: ValidatorInfo

    status: ValidationStatus

    timing: ValidationTiming

    messages: list[ValidationMessage] = Field(
        default_factory=list, description="Validation findings, warnings, errors"
    )

    metrics: list[ValidationMetric] = Field(
        default_factory=list, description="Computed metrics from the validation"
    )

    artifacts: list[ValidationArtifact] = Field(
        default_factory=list, description="Output files produced by the validator"
    )

    raw_outputs: RawOutputs | None = Field(
        default=None, description="Raw output files information"
    )

    outputs: dict[str, Any] | None = Field(
        default=None,
        description=("Domain-specific outputs (subclasses override with typed model)"),
    )

    model_config = {"extra": "forbid"}


# ==============================================================================
# Callback Payload
# ==============================================================================


class ValidationCallback(BaseModel):
    """
    Callback payload POSTed from validator backend to Django.

    Minimal payload to avoid duplication - Django loads the full output.json
    from storage after receiving this callback.
    """

    run_id: str = Field(description="Run identifier")

    callback_id: str = Field(
        min_length=1,
        description=(
            "Idempotency key echoed from the input envelope's context.callback_id. "
            "Used by the callback handler to detect and ignore duplicate deliveries."
        ),
    )

    callback_nonce: str = Field(
        min_length=CALLBACK_NONCE_MIN_LENGTH,
        max_length=CALLBACK_NONCE_MAX_LENGTH,
        pattern=CALLBACK_NONCE_PATTERN,
        repr=False,
        description=("Raw per-attempt callback secret echoed from the input envelope."),
    )

    status: ValidationStatus

    result_uri: str = Field(
        description="Storage URI to output.json (gs:// or file:// for self-hosted)"
    )

    model_config = {"extra": "forbid"}
