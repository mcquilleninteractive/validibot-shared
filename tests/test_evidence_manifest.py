"""Tests for the minimal permanent evidence-receipt contract.

The manifest is deliberately smaller than the run model. This suite protects
the public boundary: the receipt contains only run outcome, workflow-step
identity (including the optional backend image digest), and canonical
input/output digests, while rejecting lineage, workflow configuration,
retention settings, and other durable extras.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from validibot_shared.evidence import (
    SCHEMA_VERSION,
    EvidenceManifest,
    WorkflowReceipt,
    WorkflowStepReceipt,
)


def _minimal_manifest() -> EvidenceManifest:
    """Build the smallest valid receipt used by shape-focused tests."""

    return EvidenceManifest(
        run_id="run-123",
        completed_at="2026-08-02T04:12:55+00:00",
        status="SUCCEEDED",
        workflow=WorkflowReceipt(
            slug="energyplus-baseline",
            version="12",
            steps=[
                WorkflowStepReceipt(
                    key="validate_input",
                    status="SUCCEEDED",
                    validator="input-contract",
                    validator_version="1.0.0",
                ),
            ],
        ),
        input_sha256="a" * 64,
        output_envelope_sha256="b" * 64,
    )


class TestSchemaIdentity:
    """The published schema URL is the manifest's only schema identity."""

    def test_schema_url_defaults_to_published_v2_document(self):
        """Every new receipt points at the resolvable v2 schema."""

        manifest = _minimal_manifest()

        assert manifest.schema_url == SCHEMA_VERSION
        assert manifest.model_dump(mode="json", by_alias=True)["$schema"] == (
            SCHEMA_VERSION
        )

    def test_old_opaque_schema_label_is_rejected(self):
        """The incompatible v1 shape cannot be mistaken for the new contract."""

        with pytest.raises(ValidationError):
            EvidenceManifest(
                **{
                    **_minimal_manifest().model_dump(mode="python"),
                    "$schema": "validibot.evidence.v1",
                },
            )


class TestMinimalShape:
    """The receipt contains exactly the fields required to explain a run."""

    def test_top_level_keys_are_minimal(self):
        """Lineage and workflow configuration cannot enter the durable shape."""

        assert set(_minimal_manifest().model_dump(mode="json", by_alias=True)) == {
            "$schema",
            "run_id",
            "completed_at",
            "status",
            "workflow",
            "input_sha256",
            "output_envelope_sha256",
        }

    def test_workflow_steps_preserve_order_and_identity(self):
        """The ordered step projection explains which validators ran."""

        manifest = _minimal_manifest()
        manifest = manifest.model_copy(
            update={
                "workflow": WorkflowReceipt(
                    slug="workflow",
                    version="2",
                    steps=[
                        WorkflowStepReceipt(
                            key="first",
                            status="SUCCEEDED",
                            validator="one",
                            validator_version="1.0.0",
                        ),
                        WorkflowStepReceipt(
                            key="second",
                            status="FAILED",
                            validator="two",
                            validator_version="2.0.0",
                        ),
                    ],
                ),
            },
        )

        assert [step.key for step in manifest.workflow.steps] == ["first", "second"]
        assert manifest.workflow.steps[1].status == "FAILED"

    def test_backend_image_digest_is_optional_step_identity(self):
        """A captured image distinguishes rebuilt backends without adding telemetry."""

        manifest = _minimal_manifest().model_copy(
            update={
                "workflow": WorkflowReceipt(
                    slug="workflow",
                    version="2",
                    steps=[
                        WorkflowStepReceipt(
                            key="first",
                            status="SUCCEEDED",
                            validator="one",
                            validator_version="1.0.0",
                            backend_image_digest=(
                                "registry.example/one@sha256:" + "a" * 64
                            ),
                        ),
                    ],
                ),
            },
        )

        assert manifest.workflow.steps[0].backend_image_digest == (
            "registry.example/one@sha256:" + "a" * 64
        )

    def test_payload_hashes_are_optional_but_strict_when_present(self):
        """Runs without one side of payload data still have a valid receipt."""

        manifest = _minimal_manifest().model_copy(
            update={"input_sha256": None, "output_envelope_sha256": None},
        )

        assert manifest.input_sha256 is None
        assert manifest.output_envelope_sha256 is None

        with pytest.raises(ValidationError):
            EvidenceManifest(
                **{
                    **_minimal_manifest().model_dump(mode="python"),
                    "input_sha256": "not-a-hash",
                },
            )

    def test_unknown_top_level_keys_are_rejected(self):
        """A producer cannot silently add lineage or configuration fields."""

        with pytest.raises(ValidationError):
            EvidenceManifest(
                **_minimal_manifest().model_dump(mode="python"),
                lineage=[],
            )

    def test_receipt_is_frozen(self):
        """The object cannot change after the bytes destined for hashing are built."""

        manifest = _minimal_manifest()

        with pytest.raises(ValidationError):
            manifest.status = "FAILED"
