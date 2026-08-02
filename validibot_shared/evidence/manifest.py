"""The minimal permanent evidence-receipt schema.

The manifest is deliberately a small, storage-free record of what happened in
one validation run. It contains the run outcome, the workflow steps that ran,
and one digest for the canonical submitted input and output envelope. Raw
payloads, workflow configuration, retention policy, and artifact provenance
belong outside this permanent receipt.

The credential that accompanies a manifest carries the integrity binding:
``manifestHash = SHA-256(canonical manifest bytes)``. The hash is not repeated
inside the manifest.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "https://validibot.com/schemas/evidence-manifest-v2.json"
_SHA256_PATTERN = r"^[0-9a-fA-F]{64}$"


class WorkflowStepReceipt(BaseModel):
    """The smallest useful description of one executed workflow step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    status: str = Field(min_length=1)
    validator: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    backend_image_digest: str | None = Field(
        default=None,
        max_length=512,
        description=(
            "Resolved container image identity for the backend that ran the step, "
            "when captured."
        ),
    )


class WorkflowReceipt(BaseModel):
    """The workflow identity and ordered executable steps for a run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str = Field(min_length=1)
    version: str = Field(min_length=1)
    steps: list[WorkflowStepReceipt] = Field(default_factory=list)


class EvidenceManifest(BaseModel):
    """Minimal permanent receipt for one completed validation run."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

    schema_url: Literal[SCHEMA_VERSION] = Field(
        default=SCHEMA_VERSION,
        alias="$schema",
        description="Canonical URL of the published manifest schema.",
    )
    run_id: str = Field(min_length=1)
    completed_at: str = Field(min_length=1)
    status: str = Field(min_length=1)
    workflow: WorkflowReceipt
    input_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
        description="SHA-256 of the canonical submitted input representation.",
    )
    output_envelope_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
        description="SHA-256 of the canonical output envelope, when produced.",
    )


__all__ = [
    "SCHEMA_VERSION",
    "EvidenceManifest",
    "WorkflowReceipt",
    "WorkflowStepReceipt",
]
