<div align="center">

# Validibot Shared

**Shared Pydantic models for Validibot validator backends**

[![PyPI version](https://badge.fury.io/py/validibot-shared.svg)](https://pypi.org/project/validibot-shared/)
[![Python versions](https://img.shields.io/pypi/pyversions/validibot-shared.svg)](https://pypi.org/project/validibot-shared/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OIDC attestation](https://img.shields.io/badge/PyPI%20attestations-enabled-2da44e.svg)](https://docs.pypi.org/attestations/)

[Installation](#installation) •
[Core Concepts](#core-concepts) •
[Usage](#usage-examples) •
[API Reference](#api-reference)

</div>

---

> [!NOTE]
> This library is part of the [Validibot](https://github.com/mcquilleninteractive/validibot) open-source data validation platform. It defines the data interchange contract between the core platform and validator backends.

---

## Part of the Validibot Project

| Repository | Description |
|------------|-------------|
| **[validibot](https://github.com/mcquilleninteractive/validibot)** | Core platform — web UI, REST API, workflow engine |
| **[validibot-cli](https://github.com/mcquilleninteractive/validibot-cli)** | Command-line interface |
| **[validibot-validator-backends](https://github.com/mcquilleninteractive/validibot-validator-backends)** | Validator backends for advanced validators (EnergyPlus™, FMU) |
| **[validibot-shared](https://github.com/mcquilleninteractive/validibot-shared)** (this repo) | Shared Pydantic models for data interchange |

---

## What is Validibot Shared?

Validibot Shared provides the Pydantic models that define how the Validibot core platform communicates with validator backends. When Validibot needs to run a complex validation (like an EnergyPlus™ simulation or FMU probe), it:

1. **Creates an input envelope** containing the files to validate and configuration
2. **Launches a validator backend** with the envelope as input
3. **Receives an output envelope** with validation results, metrics, and artifacts

This library ensures both sides speak the same language with full type safety and runtime validation.

Terminology note: in the core `validibot` codebase, `AdvancedValidator` is the Django-side validator class that prepares and launches external work. A validator backend, or future `ValidatorBackend` protocol, is the external implementation it delegates to, usually a container or cloud job. This package defines the envelope boundary between that trusted Django-side validator and the external validator backend. The backend does not receive the full Django submission, workflow, permissions, billing, or credential state unless the parent validator intentionally includes specific data in the envelope.

## Features

- **Type-safe envelopes** — Pydantic models with full IDE autocomplete and type checking
- **Runtime validation** — Automatic validation of all data at serialization boundaries
- **Domain-specific extensions** — Typed subclasses for EnergyPlus™, FMU, and custom validators
- **Lightweight** — Only depends on Pydantic, no heavy dependencies

## Disclaimer

> [!NOTE]
> This library defines data interchange models only — it does not process, store, or transmit user data. However, the models are used by validator backends that execute user-supplied files. See the [LICENSE](LICENSE) for full warranty disclaimer. The authors accept no liability for the behaviour of systems built using these models.

## Installation

```bash
# Using pip
pip install validibot-shared

# Using uv (recommended)
uv add validibot-shared

# Using poetry
poetry add validibot-shared
```

### Requirements

- Python 3.10 or later
- Pydantic 2.13 or later (< 3.0)

## Core Concepts

### The Envelope Pattern

Validibot uses an "envelope" pattern for validator communication. Every validation job is wrapped in a standardized envelope that carries:

- **Job metadata** — Run ID, validator info, execution context
- **Input files** — References to files being validated (URIs, not raw data)
- **Configuration** — Validator-specific settings
- **Results** — Status, messages, metrics, and artifacts (output only)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Validibot Core Platform                      │
│                                                                 │
│  1. Creates ValidationInputEnvelope with:                       │
│     • run_id, validator info                                    │
│     • input_files[] (GCS/S3 URIs)                               │
│     • inputs (validator-specific config)                        │
│     • callback_url for async notification                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ JSON
┌─────────────────────────────────────────────────────────────────┐
│                  Validator Backend Container                    │
│                    (EnergyPlus, FMU, etc.)                      │
│                                                                 │
│  1. Parses input envelope                                       │
│  2. Downloads input files from URIs                             │
│  3. Runs validation/simulation                                  │
│  4. Creates ValidationOutputEnvelope with results               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ JSON (callback or response)
┌─────────────────────────────────────────────────────────────────┐
│                    Validibot Core Platform                      │
│                                                                 │
│  1. Receives output envelope                                    │
│  2. Parses and validates with Pydantic                          │
│  3. Stores findings, metrics, artifacts                         │
└─────────────────────────────────────────────────────────────────┘
```

### Base Envelope Classes

The library provides these base classes in `validibot_shared.validations.envelopes`:

| Class | Purpose |
|-------|---------|
| `ValidationInputEnvelope` | Standard input format for validation jobs |
| `ValidationOutputEnvelope` | Standard output format with results |
| `ValidationCallback` | Callback payload for async job completion |

Supporting models include:

| Class | Purpose |
|-------|---------|
| `InputFileItem` | File reference with URI, MIME type, role, exact size, SHA-256, and immutable storage version |
| `ResourceFileItem` | Managed auxiliary file reference with safe name, URI, resource type, and byte identity |
| `ValidatorInfo` | Validator identification (ID, type, version) |
| `ExecutionContext` | Attempt identity, callback nonce commitment, bundle URI, and timeout |
| `ValidationMessage` | Individual finding (error, warning, info) |
| `ValidationMetric` | Named numeric metric with optional unit |
| `ValidationArtifact` | Output file reference (reports, logs, etc.) |
| `ArtifactRef` | Indexed run artifact reference for workflow/evidence control planes |
| `FilePortContract` | Shared file-port vocabulary for declared validator file inputs/outputs |

### Designing File Inputs

The shared envelope exposes file inputs as `input_files` and `resource_files`.
Validator authors should still design those files as **declared ports** in the
core platform.

A file port answers:

- what the file means to the validator (`primary_model`, `weather_file`,
  `data_graph`, `xml_document`, `schema_file`, `fmu_model`);
- how many files are valid (`1..1`, `0..1`, or a future collection);
- which envelope channel it renders into (`input_files` or `resource_files`);
- which backend role/type it uses (`primary-model`, `weather`, `fmu`,
  `data-graph`);
- which formats and MIME types are accepted;
- whether the source may be a submitted file, workflow resource, upstream
  artifact, or signal containing an artifact reference.

Keep small configuration in typed `inputs`. Use file/resource/artifact ports
for bytes. For example, EnergyPlus timestep settings belong in
`EnergyPlusInputs`; the IDF/epJSON model and EPW weather file belong in file
ports rendered to `input_files` / `resource_files`.

Backends should read files by role and `port_key` when available, not by
assuming `input_files[0]` forever. Every file item commits to an exact size,
SHA-256, and provider-specific immutable storage version; runtimes must verify
those fields while streaming before a validator parses or executes the bytes.

`ArtifactRef` and `FilePortContract` live in
`validibot_shared.validations.artifacts`. `InputFileItem` and
`ResourceFileItem` also accept an optional `port_key` so a backend or evidence
builder can correlate an envelope item back to the declared Validibot port
without relying only on backend role/type strings.

### Typed Subclassing Pattern

Domain-specific validators extend the base envelopes with typed fields. This gives you:

- **Type safety** — mypy/pyright catch errors at compile time
- **Runtime validation** — Pydantic validates all data
- **IDE support** — Full autocomplete for domain-specific fields

```python
from validibot_shared.energyplus import EnergyPlusInputEnvelope, EnergyPlusInputs

# The envelope has typed inputs instead of dict[str, Any]
envelope = EnergyPlusInputEnvelope(
    run_id="abc-123",
    inputs=EnergyPlusInputs(timestep_per_hour=4),
    # ... other fields
)

# IDE autocomplete and type checking work
timestep = envelope.inputs.timestep_per_hour  # ✓ Known to be int
```

## Package Structure

```
validibot_shared/
├── validations/           # Base validation envelope schemas
│   └── envelopes.py      # Input/output envelopes for all validators
├── energyplus/           # EnergyPlus-specific models and envelopes
│   ├── models.py         # Simulation output models (metrics, results)
│   └── envelopes.py      # Typed envelope subclasses
├── fmu/                  # FMU-specific models
│   ├── models.py         # Probe/simulation result models
│   └── envelopes.py      # FMU envelope subclasses
├── shacl/                # SHACL isolated-backend envelopes
│   └── envelopes.py      # SHACL inputs/outputs and builder
└── schematron/           # Schematron isolated-backend envelopes
    ├── envelopes.py      # Schematron inputs/outputs and builder
    └── svrl.py           # SVRL parsing helpers
```

## Usage Examples

### Creating an Input Envelope

```python
import secrets

from validibot_shared.canonicalization import compute_callback_nonce_commitment
from validibot_shared.energyplus import EnergyPlusInputEnvelope, EnergyPlusInputs
from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    InputFileItem,
    OrganizationInfo,
    SupportedMimeType,
    ValidatorInfo,
    ValidatorType,
    WorkflowInfo,
)

callback_nonce = secrets.token_urlsafe(32)

envelope = EnergyPlusInputEnvelope(
    run_id="run-123",
    validator=ValidatorInfo(
        id="v1",
        type=ValidatorType.ENERGYPLUS,
        version="24.2.0",
    ),
    org=OrganizationInfo(id="org-123", name="Example Org"),
    workflow=WorkflowInfo(
        id="workflow-456",
        step_id="step-789",
        step_name="EnergyPlus Simulation",
    ),
    input_files=[
        InputFileItem(
            name="model.idf",
            mime_type=SupportedMimeType.ENERGYPLUS_IDF,
            role="primary-model",
            uri="gs://bucket/model.idf",
            size_bytes=12345,
            sha256="0123456789abcdef" * 4,
            storage_version="1700000000000000",
        ),
    ],
    inputs=EnergyPlusInputs(timestep_per_hour=4),
    context=ExecutionContext(
        callback_url="https://api.example.com/callback",
        callback_id="execution-attempt-attempt-123",
        callback_nonce=callback_nonce,
        callback_nonce_commitment=compute_callback_nonce_commitment(callback_nonce),
        execution_bundle_uri="gs://bucket/runs/org-123/run-123/attempts/attempt-123/",
        execution_attempt_id="attempt-123",
        step_run_id="step-run-789",
        attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
        expected_output_uri=(
            "gs://bucket/runs/org-123/run-123/attempts/attempt-123/output.json"
        ),
    ),
)

# Serialize to JSON for the validator backend
json_payload = envelope.model_dump_json()
```

### Deserializing Results

```python
from validibot_shared.energyplus import EnergyPlusOutputEnvelope
from validibot_shared.validations.envelopes import ValidationStatus

# Parse JSON response from validator
envelope = EnergyPlusOutputEnvelope.model_validate_json(response_json)

# Check status
if envelope.status == ValidationStatus.SUCCESS:
    # Access typed outputs with full autocomplete
    if envelope.outputs and envelope.outputs.metrics:
        print(f"EUI: {envelope.outputs.metrics.site_eui_kwh_m2} kWh/m²")

# Iterate over validation messages
for message in envelope.messages:
    print(f"[{message.severity}] {message.text}")
```

### FMU Probe Results

```python
from validibot_shared.fmu.models import FMUProbeResult, FMUVariableMeta

# Create a successful probe result
result = FMUProbeResult.success(
    variables=[
        FMUVariableMeta(name="temperature", causality="output", value_type="Real"),
        FMUVariableMeta(name="pressure", causality="output", value_type="Real"),
    ],
    execution_seconds=0.5,
)

# Create a failure result
result = FMUProbeResult.failure(
    errors=["Invalid FMU: missing modelDescription.xml"]
)

# Serialize for response
json_response = result.model_dump_json()
```

### Creating a Custom Validator

If you're building a custom validator, create typed envelope subclasses:

```python
from pydantic import BaseModel
from validibot_shared.validations.envelopes import (
    ValidationInputEnvelope,
    ValidationOutputEnvelope,
)

# Define your validator's input configuration
class MyValidatorInputs(BaseModel):
    strict_mode: bool = False
    max_errors: int = 100

# Define your validator's output data
class MyValidatorOutputs(BaseModel):
    items_checked: int
    items_passed: int

# Create typed envelope subclasses
class MyValidatorInputEnvelope(ValidationInputEnvelope):
    inputs: MyValidatorInputs

class MyValidatorOutputEnvelope(ValidationOutputEnvelope):
    outputs: MyValidatorOutputs | None = None
```

## API Reference

### ValidationInputEnvelope

```python
class ValidationInputEnvelope(BaseModel):
    run_id: str                      # Unique identifier for this validation run
    validator: ValidatorInfo         # Validator identification
    input_files: list[InputFileItem] # Files to validate
    inputs: dict[str, Any]           # Validator-specific configuration
    context: ExecutionContext        # Callback URL, bundle URI, etc.
```

### ValidationOutputEnvelope

```python
class ValidationOutputEnvelope(BaseModel):
    run_id: str                          # Matches input run_id
    status: str                          # "success", "failure", "error"
    messages: list[ValidationMessage]    # Validation findings
    metrics: list[ValidationMetric]      # Numeric metrics
    artifacts: list[ValidationArtifact]  # Output files
    outputs: dict[str, Any] | None       # Validator-specific results
    execution_seconds: float | None      # Execution time
```

### ValidationMessage

```python
class ValidationMessage(BaseModel):
    severity: str    # "error", "warning", "info"
    code: str | None # Machine-readable code
    text: str        # Human-readable message
    location: str | None  # File/line reference
```

## Part of the Validibot Project

This library is one component of the Validibot open-source data validation platform:

| Repository | Description |
|------------|-------------|
| **[validibot](https://github.com/mcquilleninteractive/validibot)** | Core platform — web UI, REST API, workflow engine |
| **[validibot-cli](https://github.com/mcquilleninteractive/validibot-cli)** | Command-line interface |
| **[validibot-validator-backends](https://github.com/mcquilleninteractive/validibot-validator-backends)** | Validator backends for advanced validators (EnergyPlus™, FMU) |
| **[validibot-shared](https://github.com/mcquilleninteractive/validibot-shared)** (this repo) | Shared Pydantic models for data interchange |

### How It Fits Together

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              End Users                                       │
│                    (Web UI, CLI, REST API clients)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         validibot (core platform)                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Web UI  │  REST API  │  Workflow Engine  │  Built-in Validators   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│            Triggers Docker containers for advanced validations              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌─────────────────┐    ┌──────────────────────────────┐    ┌─────────────────────┐
│ validibot-cli   │    │ validibot-validator-backends │    │ validibot-shared    │
│                 │    │                              │    │  (this repo)        │
│ Terminal access │    │ EnergyPlus™, FMU             │    │                     │
│ to API          │    │ validator backends           │    │ Pydantic models     │
│                 │    │              │               │    │ (shared contract)   │
└─────────────────┘    └──────────────┼───────────────┘    └─────────────────────┘
                                │                          ▲
                                └──────────────────────────┘
                                  backends import shared
                                  models for type safety
```

## Development

```bash
# Clone the repository
git clone https://github.com/mcquilleninteractive/validibot-shared.git
cd validibot-shared

# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run python -m pytest

# Run linter
uv run ruff check .
```

## Trademarks

EnergyPlus™ is a trademark of the U.S. Department of Energy. Validibot is not affiliated with, endorsed by, or sponsored by the U.S. Department of Energy or the National Renewable Energy Laboratory (NREL).

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

[Validibot Platform](https://github.com/mcquilleninteractive/validibot) •
[Documentation](https://docs.validibot.com) •
[Report Issues](https://github.com/mcquilleninteractive/validibot-shared/issues)

</div>
