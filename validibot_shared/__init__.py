"""Shared domain models and utilities for Validibot."""

from validibot_shared.canonicalization import (
    canonicalize_dict,
    canonicalize_model,
    compute_callback_nonce_commitment,
    sha256_hex_for_dict,
    sha256_hex_for_model,
)
from validibot_shared.energyplus.models import (
    EnergyPlusSimulationLogs,
    EnergyPlusSimulationMetrics,
    EnergyPlusSimulationOutputs,
)
from validibot_shared.evidence import (
    SCHEMA_VERSION as EVIDENCE_SCHEMA_VERSION,
)
from validibot_shared.evidence import (
    EvidenceManifest,
    WorkflowReceipt,
    WorkflowStepReceipt,
)
from validibot_shared.fmu.models import FMUProbeResult, FMUVariableMeta
from validibot_shared.portfolio_manager import (
    ExpectedBuildingsList,
    PortfolioManagerInputEnvelope,
    PortfolioManagerInputs,
    PortfolioManagerOutputEnvelope,
    PortfolioManagerOutputs,
    PortfolioManagerPropertyResult,
)
from validibot_shared.shacl.envelopes import (
    SHACLInputEnvelope,
    SHACLInputs,
    SHACLOutputEnvelope,
    SHACLOutputs,
    SHACLSparqlAssertionSpec,
)

__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "canonicalize_dict",
    "canonicalize_model",
    "compute_callback_nonce_commitment",
    "EnergyPlusSimulationLogs",
    "EnergyPlusSimulationMetrics",
    "EnergyPlusSimulationOutputs",
    "EvidenceManifest",
    "FMUProbeResult",
    "FMUVariableMeta",
    "ExpectedBuildingsList",
    "PortfolioManagerInputEnvelope",
    "PortfolioManagerInputs",
    "PortfolioManagerOutputEnvelope",
    "PortfolioManagerOutputs",
    "PortfolioManagerPropertyResult",
    "SHACLInputEnvelope",
    "SHACLInputs",
    "SHACLOutputEnvelope",
    "SHACLOutputs",
    "SHACLSparqlAssertionSpec",
    "sha256_hex_for_dict",
    "sha256_hex_for_model",
    "WorkflowReceipt",
    "WorkflowStepReceipt",
]
