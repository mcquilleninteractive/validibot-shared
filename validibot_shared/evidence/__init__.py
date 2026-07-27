"""Evidence-manifest schema (``validibot.evidence.v1``).

Public API for both the Validibot Django app (which generates
manifests when validation runs complete) and the Pro / external
verifiers (which sign / verify them). The schemas are intentionally
storage-agnostic and Django-free so any consumer can validate a
manifest without pulling in the application stack.
"""

from validibot_shared.evidence.manifest import (
    SCHEMA_VERSION,
    ContractConstant,
    ContractSignalMapping,
    EvidenceManifest,
    ManifestArtifactInputBinding,
    ManifestArtifactLineageEdge,
    ManifestExecutionAttempt,
    ManifestExecutionInput,
    ManifestInputRelationship,
    ManifestPayloadDigests,
    ManifestProducedArtifact,
    ManifestRetentionInfo,
    StepValidatorRecord,
    WorkflowContractSnapshot,
)

__all__ = [
    "SCHEMA_VERSION",
    "ContractConstant",
    "ContractSignalMapping",
    "EvidenceManifest",
    "ManifestArtifactInputBinding",
    "ManifestArtifactLineageEdge",
    "ManifestExecutionAttempt",
    "ManifestExecutionInput",
    "ManifestInputRelationship",
    "ManifestPayloadDigests",
    "ManifestProducedArtifact",
    "ManifestRetentionInfo",
    "StepValidatorRecord",
    "WorkflowContractSnapshot",
]
