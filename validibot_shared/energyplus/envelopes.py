"""
EnergyPlus-specific envelope schemas for Advanced validator communication.

EnergyPlus is an Advanced validator - it runs in a separate container/service rather
than within the Django app. These schemas extend the base validation envelopes with
EnergyPlus-specific typed inputs and outputs.

## Architecture Pattern

This module demonstrates the envelope subclassing pattern:

1. **Base envelopes** (in validibot_shared.validations.envelopes):
   - ValidationInputEnvelope has inputs: dict[str, Any]
   - ValidationOutputEnvelope has outputs: dict[str, Any] | None

2. **Domain-specific envelopes** (this file):
   - EnergyPlusInputEnvelope has inputs: EnergyPlusInputs (typed override!)
   - EnergyPlusOutputEnvelope has outputs: EnergyPlusOutputs (typed override!)

This provides type safety while maintaining a consistent interface across
all Advanced validators.

## Reusing Component Models

The EnergyPlusOutputs class composes existing models from models.py:
- EnergyPlusSimulationOutputs: File paths (SQL, CSV, ERR, ESO)
- EnergyPlusSimulationMetrics: Extracted metrics (electricity, gas, EUI)
- EnergyPlusSimulationLogs: Log tails (stdout, stderr, err file)

This follows DRY principles - we don't duplicate data structures. The models.py
file contains reusable components that represent EnergyPlus simulation outputs.
These are composed within the envelope classes to provide type-safe output packaging.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from validibot_shared.energyplus.models import (
    EnergyPlusIdfCheck,
    EnergyPlusReviewProfile,
    EnergyPlusSimulationLogs,
    EnergyPlusSimulationMetrics,
    EnergyPlusSimulationOutputs,
    InvocationMode,
)
from validibot_shared.validations.envelopes import (
    ValidationInputEnvelope,
    ValidationOutputEnvelope,
)

# ==============================================================================
# EnergyPlus Input Configuration
# ==============================================================================


class EnergyPlusInputs(BaseModel):
    """
    EnergyPlus simulation configuration parameters.

    These are the settings that control how the EnergyPlus simulation runs.
    Input files (IDF model, EPW weather) are passed separately in the parent
    envelope's input_files field with roles like 'primary-model' and 'weather'.

    ## Why Separate From Input Files?

    Configuration parameters (this class) are different from input files:
    - Configuration: How to run the simulation (timesteps, invocation mode, etc.)
    - Input files: What to run (IDF model, weather data)

    This separation allows:
    - Type-safe configuration validation
    - Reusable models with different run settings
    - Clear distinction between data files and execution parameters

    ## Architecture Design

    This configuration model is separate from input files to maintain clear
    separation of concerns:
    - Configuration (this class): How to run the simulation
    - Input files (in parent envelope): What files to process

    Using a typed Pydantic model provides compile-time type checking and
    runtime validation of all configuration parameters.

    Note: The validator always returns a fixed set of output values defined
    in its catalog. Users don't need to specify which outputs they want -
    they get all defined outputs and write assertions against the ones they
    care about.
    """

    # Simulation timestep configuration
    timestep_per_hour: int = Field(
        default=4,
        description="Number of timesteps per hour (e.g., 4 = 15-minute intervals)",
        ge=1,
        le=60,
    )

    # Optional run period override
    run_period_days: int | None = Field(
        default=None,
        description="Optional override for run period length in days",
    )

    # Invocation method
    invocation_mode: InvocationMode = Field(
        default="cli",
        description="How to invoke EnergyPlus: 'cli' or 'python_api'",
    )

    idf_checks: list[EnergyPlusIdfCheck] = Field(
        default_factory=list,
        description=(
            "Validibot preflight checks to run against a working model copy; "
            "these are not EnergyPlus CLI flags"
        ),
    )

    run_simulation: bool = Field(
        default=True,
        description=(
            "Run a full weather-based simulation when true; run conversion and "
            "review preflight only when false"
        ),
    )

    review_profile: EnergyPlusReviewProfile = Field(
        default="standard",
        description="Review evidence/severity profile; does not change the engine",
    )

    model_config = {"extra": "forbid"}


# ==============================================================================
# EnergyPlus Output Data
# ==============================================================================


class EnergyPlusOutputs(BaseModel):
    """
    EnergyPlus simulation outputs and execution information.

    This contains detailed, EnergyPlus-specific results from the simulation.
    It's used as the typed 'outputs' field in EnergyPlusOutputEnvelope.

    ## Why This Class Exists

    The parent envelope (ValidationOutputEnvelope) already has generic fields
    like messages, metrics, and artifacts. This class adds EnergyPlus-specific
    execution details that don't fit the generic schema:
    - Return codes and execution timing
    - Process logs (stdout, stderr, err file)
    - Specific file paths (eplusout.sql, eplusout.err, etc.)

    ## Composing Reusable Models (DRY Principle)

    We reuse three models from models.py instead of duplicating their definitions:
    - EnergyPlusSimulationOutputs: File paths (SQL, CSV, ERR, ESO)
    - EnergyPlusSimulationMetrics: Extracted metrics (electricity, gas, EUI)
    - EnergyPlusSimulationLogs: Log tails (stdout, stderr, err file)

    This follows the composition pattern - small, focused models are composed
    into larger structures.

    ## Why Create This Class?

    The parent envelope (ValidationOutputEnvelope) provides generic validation
    outputs (messages, metrics, artifacts). This class adds EnergyPlus-specific
    execution details that don't fit the generic schema:
    - Process return codes and timing
    - Detailed file paths and logs
    - Invocation method tracking

    This separation prevents redundancy:
    - Generic validation data → parent envelope fields
    - EnergyPlus execution data → this class
    """

    # Reuse existing output file tracking from models.py
    outputs: EnergyPlusSimulationOutputs = Field(
        default_factory=EnergyPlusSimulationOutputs,
        description="Paths to EnergyPlus output files (SQL, CSV, ERR, ESO)",
    )

    # Reuse existing metrics tracking from models.py
    metrics: EnergyPlusSimulationMetrics = Field(
        default_factory=EnergyPlusSimulationMetrics,
        description="Extracted simulation metrics (energy use, etc.)",
    )

    # Reuse existing log tracking from models.py
    logs: EnergyPlusSimulationLogs | None = Field(
        default=None, description="Simulation logs (stdout, stderr, err file tails)"
    )

    # Execution metadata
    energyplus_returncode: int = Field(
        description="EnergyPlus process return code (0 = success)"
    )

    execution_seconds: float = Field(
        ge=0, description="Total simulation execution time in seconds"
    )

    invocation_mode: InvocationMode = Field(
        description="How EnergyPlus was invoked ('cli' or 'python_api')"
    )

    # Execution and version evidence. Optional strings remain explicit nulls
    # when the installed binary/model does not expose a value.
    energyplus_binary_version: str | None = None
    energyplus_binary_build: str | None = None
    idd_version: str | None = None
    idd_build: str | None = None
    idd_path: str | None = None
    idf_version: str | None = None
    version_match: bool | None = None
    completed_successfully: bool = False

    # Reviewer-grade issue summary. Counts are independent from presentation
    # filtering of individual warnings in the Django application.
    warning_count: int = Field(default=0, ge=0)
    severe_count: int = Field(default=0, ge=0)
    fatal_count: int = Field(default=0, ge=0)
    review_issue_count: int = Field(default=0, ge=0)

    # Artifact availability is reported independently of uploaded artifact
    # references so assertions can explain why a metric is unavailable.
    has_sql_output: bool = False
    has_err_output: bool = False
    has_csv_output: bool = False
    has_eso_output: bool = False

    model_config = {"extra": "forbid"}


# ==============================================================================
# EnergyPlus-Specific Envelopes
# ==============================================================================


class EnergyPlusInputEnvelope(ValidationInputEnvelope):
    """
    EnergyPlus-specific input envelope.

    This is what Django serializes and writes to storage as input.json before
    triggering an EnergyPlus validator container.

    ## Type-Safe Field Override

    The base ValidationInputEnvelope has:
    ```python
    inputs: dict[str, Any] = Field(default_factory=dict)
    ```

    We override it with a typed version:
    ```python
    inputs: EnergyPlusInputs
    ```

    This gives us:
    - Compile-time type checking in Django (mypy catches config errors)
    - Runtime validation (Pydantic validates timesteps, output variables, etc.)
    - Auto-generated documentation (API docs from Pydantic schema)
    - IDE autocomplete when building input envelopes

    ## How Data Flows

    1. Django creates this envelope:
       - input_files: [IDF with role='primary-model', EPW with role='weather']
       - inputs: EnergyPlusInputs(timestep_per_hour=4)
       - context: ExecutionContext(callback_url=..., execution_bundle_uri=...)

    2. Django serializes to JSON and uploads to storage as input.json

    3. Validator container downloads input.json and deserializes to this class

    4. Validator container extracts typed configuration from inputs field
    """

    # Override inputs field with typed EnergyPlus configuration
    inputs: EnergyPlusInputs


class EnergyPlusOutputEnvelope(ValidationOutputEnvelope):
    """
    EnergyPlus-specific output envelope.

    This is what the EnergyPlus validator container serializes and writes to
    storage as output.json after simulation completes.

    ## Type-Safe Field Override

    The base ValidationOutputEnvelope has:
    ```python
    outputs: dict[str, Any] | None = Field(default=None)
    ```

    We override it with a typed version:
    ```python
    outputs: EnergyPlusOutputs
    ```

    This gives us the same benefits as the input envelope (type checking,
    validation, docs, autocomplete).

    ## Generic vs Domain-Specific Data

    The envelope contains BOTH:

    **Generic fields** (from parent ValidationOutputEnvelope):
    - messages: ValidationMessage list (errors, warnings - consistent
      across all validators)
    - metrics: ValidationMetric list (high-level computed values for UI display)
    - artifacts: ValidationArtifact list (GCS URIs to important output files)
    - status: SUCCESS/FAILED_VALIDATION/FAILED_RUNTIME/CANCELLED

    **Domain-specific field** (this class):
    - outputs: EnergyPlusOutputs (returncode, logs, all file paths, execution time)

    ## Why Both?

    - Generic fields enable consistent UI across all validators
      (same message format, same metric format)
    - Domain-specific outputs preserve detailed execution info
      for debugging and reproduction

    ## How Data Flows

    1. Validator container runs EnergyPlus simulation

    2. Validator container creates this envelope:
       - status: SUCCESS or FAILED_VALIDATION
       - messages: [ValidationMessage(severity=ERROR, text="Missing required object")]
       - metrics: [ValidationMetric(name="electricity_kwh", value=12345, unit="kWh")]
       - outputs: EnergyPlusOutputs(energyplus_returncode=0, ...)

    3. Validator container serializes to JSON and uploads to storage as output.json

    4. Validator container POSTs minimal callback to Django (run_id, status, result_uri)

    5. Django downloads output.json and deserializes to this class
    """

    # Override outputs field with typed EnergyPlus results
    outputs: EnergyPlusOutputs
