"""Typed contracts for the Portfolio Manager validator backend."""

from validibot_shared.portfolio_manager.envelopes import (
    EBL_SCHEMA_VERSION,
    PORTFOLIO_MANAGER_PROPERTY_RESULTS_SCHEMA_VERSION,
    ExpectedBuilding,
    ExpectedBuildingIdField,
    ExpectedBuildingsList,
    GrossFloorAreaBasis,
    PortfolioManagerFinding,
    PortfolioManagerInputEnvelope,
    PortfolioManagerInputs,
    PortfolioManagerOutputEnvelope,
    PortfolioManagerOutputs,
    PortfolioManagerPropertyResult,
    build_portfolio_manager_input_envelope,
    mime_type_for_portfolio_manager_filename,
    validate_expected_buildings_list_json,
)

__all__ = [
    "EBL_SCHEMA_VERSION",
    "PORTFOLIO_MANAGER_PROPERTY_RESULTS_SCHEMA_VERSION",
    "ExpectedBuilding",
    "ExpectedBuildingIdField",
    "ExpectedBuildingsList",
    "GrossFloorAreaBasis",
    "PortfolioManagerFinding",
    "PortfolioManagerInputEnvelope",
    "PortfolioManagerInputs",
    "PortfolioManagerOutputEnvelope",
    "PortfolioManagerOutputs",
    "PortfolioManagerPropertyResult",
    "build_portfolio_manager_input_envelope",
    "mime_type_for_portfolio_manager_filename",
    "validate_expected_buildings_list_json",
]
