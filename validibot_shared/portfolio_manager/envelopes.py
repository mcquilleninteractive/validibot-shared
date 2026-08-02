"""Typed interchange contracts for the Portfolio Manager validator.

The Django application owns workflow policy and authoring. The isolated
backend owns parsing untrusted XLS/XLSX/XML/ZIP bytes, normalizing Portfolio
Manager metrics, resolving EBL targets, and producing deterministic facts.
These models are the strict boundary shared by both processes.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import PurePath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    InputFileItem,
    ResourceFileItem,
    SupportedMimeType,
    ValidationInputEnvelope,
    ValidationOutputEnvelope,
    ValidatorInfo,
    ValidatorType,
)

EBL_SCHEMA_VERSION = "1.0"
PORTFOLIO_MANAGER_PROPERTY_RESULTS_SCHEMA_VERSION = (
    "validibot.portfolio_manager.property_results.v1"
)

PortfolioManagerSubmissionStructure = Literal["single_report", "zip_collection"]
PortfolioManagerIdKind = Literal[
    "property_id",
    "parent_property_id",
    "standard_id",
    "custom_id",
]
MetricFieldState = Literal["absent", "clean", "alert", "not_verifiable"]
MetricValueState = Literal["absent", "value", "not_available", "invalid"]
GrossFloorAreaBasis = Literal[
    "absent",
    "self_reported",
    "buildings_and_parking_less_parking",
    "buildings_and_parking",
]
PortfolioManagerCheckPolicy = Literal["allow", "warning", "error"]
MAX_EBL_BYTES = 5_000_000
MAX_EBL_JSON_DEPTH = 12
MAX_EBL_JSON_TEXT_LENGTH = 4_096


class ExpectedBuildingIdField(BaseModel):
    """Identity field used to reconcile every EBL row with report records."""

    kind: PortfolioManagerIdKind
    name: str = Field(default="", max_length=255)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def require_named_identity(self) -> ExpectedBuildingIdField:
        """Named Standard/custom identities need the exact Portfolio Manager label."""
        if self.kind in {"standard_id", "custom_id"} and not self.name.strip():
            msg = "name is required for standard_id and custom_id identity fields"
            raise ValueError(msg)
        return self


class ExpectedBuilding(BaseModel):
    """One expected property identity and optional per-building EUIt override."""

    id_value: str = Field(min_length=1, max_length=255)
    euit: Decimal | None = Field(default=None, gt=0)

    model_config = {"extra": "forbid"}

    @field_validator("id_value")
    @classmethod
    def normalize_id_value(cls, value: str) -> str:
        """IDs are opaque strings; trimming is the only permitted normalization."""
        normalized = value.strip()
        if not normalized:
            msg = "id_value cannot be blank"
            raise ValueError(msg)
        return normalized


class ExpectedBuildingsList(BaseModel):
    """Versioned program roster accepted as the optional EBL resource."""

    schema_version: Literal["1.0"] = EBL_SCHEMA_VERSION
    id_field: ExpectedBuildingIdField
    euit_unit: Literal["kBtu/ft2/year"] = "kBtu/ft2/year"
    buildings: list[ExpectedBuilding] = Field(min_length=1, max_length=10_000)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def reject_duplicate_ids(self) -> ExpectedBuildingsList:
        """Ambiguous EBL overrides are rejected before report reconciliation."""
        ids = [building.id_value for building in self.buildings]
        if len(ids) != len(set(ids)):
            msg = "buildings contains duplicate id_value entries"
            raise ValueError(msg)
        return self


def validate_expected_buildings_list_json(
    content: bytes | str,
) -> ExpectedBuildingsList:
    """Parse the canonical EBL JSON with duplicate-key and resource bounds."""
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    if len(raw) > MAX_EBL_BYTES:
        msg = "Expected Buildings List exceeds the 5 MB byte limit"
        raise ValueError(msg)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        msg = "Expected Buildings List must be UTF-8 JSON"
        raise ValueError(msg) from exc

    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                msg = f"Expected Buildings List contains duplicate JSON key {key!r}"
                raise ValueError(msg)
            result[key] = value
        return result

    try:
        payload = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        msg = f"Expected Buildings List is not valid JSON: {exc}"
        raise ValueError(msg) from exc
    _validate_ebl_json_bounds(payload)
    if isinstance(payload, dict):
        buildings = payload.get("buildings")
        if isinstance(buildings, list):
            for index, building in enumerate(buildings):
                if (
                    isinstance(building, dict)
                    and "euit" in building
                    and building["euit"] is not None
                    and not isinstance(building["euit"], str)
                ):
                    msg = f"buildings[{index}].euit must be a canonical decimal string"
                    raise ValueError(msg)
    return ExpectedBuildingsList.model_validate(payload)


def _validate_ebl_json_bounds(value: Any, *, depth: int = 0) -> None:
    """Reject pathological JSON structure before Pydantic walks it."""
    if depth > MAX_EBL_JSON_DEPTH:
        msg = "Expected Buildings List exceeds the JSON nesting limit"
        raise ValueError(msg)
    if isinstance(value, dict):
        for key, child in value.items():
            if len(str(key)) > MAX_EBL_JSON_TEXT_LENGTH:
                msg = "Expected Buildings List contains an oversized key"
                raise ValueError(msg)
            _validate_ebl_json_bounds(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            _validate_ebl_json_bounds(child, depth=depth + 1)
    elif isinstance(value, str) and len(value) > MAX_EBL_JSON_TEXT_LENGTH:
        msg = "Expected Buildings List contains an oversized text value"
        raise ValueError(msg)


class PortfolioManagerInputs(BaseModel):
    """Resolved author configuration and defensive backend limits."""

    submission_structure: PortfolioManagerSubmissionStructure = "single_report"
    default_euit_kbtu_ft2_yr: Decimal | None = Field(default=None, gt=0)
    compare_to_euit: bool = False
    near_target_percent: Decimal = Field(default=Decimal("10"), ge=0, le=100)
    require_complete_reporting_period: bool = False
    minimum_reporting_period_months: int = Field(default=12, ge=1, le=36)
    maximum_reporting_period_age_months: int | None = Field(
        default=None,
        ge=0,
        le=120,
    )
    reporting_period_reference_date: date | None = None
    require_benchmark_ready: bool = False
    require_form_c_ready: bool = False
    require_weather_normalized_site_eui: bool = False
    require_washington_standard_id: bool = False
    require_energy_star_score: bool = False
    meter_less_than_12_months_policy: PortfolioManagerCheckPolicy = "allow"
    meter_gap_policy: PortfolioManagerCheckPolicy = "allow"
    meter_overlap_policy: PortfolioManagerCheckPolicy = "allow"
    no_meters_selected_policy: PortfolioManagerCheckPolicy = "allow"
    long_meter_entry_policy: PortfolioManagerCheckPolicy = "allow"
    estimated_energy_policy: PortfolioManagerCheckPolicy = "allow"
    other_alert_policy: PortfolioManagerCheckPolicy = "allow"
    max_input_bytes: int = Field(default=100_000_000, gt=0, le=500_000_000)
    max_archive_members: int = Field(default=1_000, gt=0, le=10_000)
    max_member_bytes: int = Field(default=20_000_000, gt=0, le=100_000_000)
    max_uncompressed_bytes: int = Field(
        default=250_000_000,
        gt=0,
        le=1_000_000_000,
    )
    max_findings: int = Field(default=1_000, gt=0, le=10_000)

    model_config = {"extra": "forbid"}


class PortfolioManagerFinding(BaseModel):
    """Domain finding retaining member and property attribution."""

    severity: Literal["ERROR", "WARNING", "INFO"]
    code: str = Field(pattern=r"^portfolio_manager\.[a-z0-9_.-]+$")
    message: str
    member_name: str = ""
    property_id: str = ""
    path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class PortfolioManagerPropertyResult(BaseModel):
    """Carrier-neutral facts for one submitted property or grouped parent."""

    member_name: str
    carrier: Literal["xls", "xlsx", "xml"]
    property_id: str
    property_name: str = ""
    parent_property_id: str = ""
    washington_standard_id: str = ""
    custom_ids: dict[str, str] = Field(default_factory=dict)
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    reporting_period_complete: bool | None = None
    reporting_period_fresh: bool | None = None
    property_type: str = ""
    # EPA's gross floor area excludes parking, outside bays, and docks, and
    # Washington CBPS computes EUIt on the Form B floor area on that same
    # basis. This field always carries the parking-excluded quantity; the two
    # fields below retain the parking-inclusive and parking-only columns so a
    # report that publishes only those can still be read and audited.
    gross_floor_area_ft2: Decimal | None = Field(default=None, ge=0)
    gross_floor_area_basis: GrossFloorAreaBasis = "absent"
    gross_floor_area_buildings_and_parking_ft2: Decimal | None = Field(
        default=None,
        ge=0,
    )
    parking_floor_area_ft2: Decimal | None = Field(default=None, ge=0)
    site_eui_kbtu_ft2_yr: Decimal | None = Field(default=None, ge=0)
    weather_normalized_site_eui_kbtu_ft2_yr: Decimal | None = Field(
        default=None,
        ge=0,
    )
    source_eui_kbtu_ft2_yr: Decimal | None = Field(default=None, ge=0)
    national_median_site_eui_kbtu_ft2_yr: Decimal | None = Field(
        default=None,
        ge=0,
    )
    site_energy_use_kbtu: Decimal | None = Field(default=None, ge=0)
    weather_normalized_site_energy_use_kbtu: Decimal | None = Field(
        default=None,
        ge=0,
    )
    weather_normalized_site_electricity_kwh: Decimal | None = Field(
        default=None,
        ge=0,
    )
    weather_normalized_site_electricity_intensity_kwh_ft2: Decimal | None = Field(
        default=None, ge=0
    )
    weather_normalized_site_natural_gas_therms: Decimal | None = Field(
        default=None,
        ge=0,
    )
    weather_normalized_site_natural_gas_intensity_therms_ft2: Decimal | None = Field(
        default=None, ge=0
    )
    onsite_renewable_electricity_generated_kwh: Decimal | None = Field(
        default=None,
        ge=0,
    )
    onsite_renewable_electricity_exported_kwh: Decimal | None = Field(
        default=None,
        ge=0,
    )
    electricity_grid_and_onsite_renewable_kbtu: Decimal | None = Field(
        default=None,
        ge=0,
    )
    electricity_grid_purchase_kbtu: Decimal | None = Field(default=None, ge=0)
    onsite_renewable_electricity_used_onsite_kbtu: Decimal | None = Field(
        default=None,
        ge=0,
    )
    natural_gas_use_kbtu: Decimal | None = Field(default=None, ge=0)
    percent_electricity_from_onsite_renewables: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    energy_star_score: Decimal | None = Field(default=None, ge=0, le=100)
    heating_degree_days: Decimal | None = Field(default=None, ge=0)
    cooling_degree_days: Decimal | None = Field(default=None, ge=0)
    weather_station_id: str = ""
    weather_station_name: str = ""
    metric_states: dict[str, MetricValueState] = Field(default_factory=dict)
    alert_states: dict[str, MetricFieldState] = Field(default_factory=dict)
    resolved_euit_kbtu_ft2_yr: Decimal | None = Field(default=None, gt=0)
    resolved_euit_source: Literal["ebl", "default", "none"] = "none"
    euit_margin_kbtu_ft2_yr: Decimal | None = None
    euit_ratio: Decimal | None = Field(default=None, ge=0)
    euit_percent_difference: Decimal | None = None
    meets_euit: bool | None = None
    near_euit: bool | None = None
    benchmark_ready: bool = False
    form_c_ready: bool = False
    ebl_match: bool | None = None

    model_config = {"extra": "forbid"}


class PortfolioManagerOutputs(BaseModel):
    """Domain outputs and CEL-visible scalar facts returned by the backend."""

    submission_structure: PortfolioManagerSubmissionStructure
    file_count: int = Field(ge=0)
    valid_file_count: int = Field(ge=0)
    invalid_file_count: int = Field(ge=0)
    property_count: int = Field(ge=0)
    reporting_cycle_count: int = Field(ge=0)
    reporting_cycles_match: bool
    complete_reporting_period_property_count: int = Field(default=0, ge=0)
    fresh_reporting_period_property_count: int = Field(default=0, ge=0)
    expected_building_count: int = Field(default=0, ge=0)
    matched_expected_building_count: int = Field(default=0, ge=0)
    missing_expected_building_count: int = Field(default=0, ge=0)
    unexpected_submitted_building_count: int = Field(default=0, ge=0)
    duplicate_submitted_property_count: int = Field(default=0, ge=0)
    parent_child_overlap_count: int = Field(default=0, ge=0)
    target_covered_property_count: int = Field(default=0, ge=0)
    target_uncovered_property_count: int = Field(default=0, ge=0)
    target_comparable_property_count: int = Field(default=0, ge=0)
    target_met_property_count: int = Field(default=0, ge=0)
    target_above_property_count: int = Field(default=0, ge=0)
    target_near_property_count: int = Field(default=0, ge=0)
    benchmark_ready_property_count: int = Field(default=0, ge=0)
    form_c_ready_property_count: int = Field(default=0, ge=0)
    aggregate_metrics_available: bool = True
    total_gross_floor_area_ft2: Decimal | None = Field(default=None, ge=0)
    weighted_weather_normalized_site_eui_kbtu_ft2_yr: Decimal | None = Field(
        default=None,
        ge=0,
    )
    energy_star_score_property_count: int = Field(default=0, ge=0)
    weighted_energy_star_score: Decimal | None = Field(default=None, ge=0, le=100)
    estimated_excess_energy_kbtu: Decimal | None = Field(default=None, ge=0)
    target_coverage_percent: Decimal | None = Field(default=None, ge=0, le=100)
    target_compliance_percent: Decimal | None = Field(default=None, ge=0, le=100)
    floor_area_target_compliance_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    property_results: list[PortfolioManagerPropertyResult] = Field(
        default_factory=list,
    )
    missing_expected_ids: list[str] = Field(default_factory=list)
    unexpected_submitted_ids: list[str] = Field(default_factory=list)
    duplicate_submitted_property_ids: list[str] = Field(default_factory=list)
    findings: list[PortfolioManagerFinding] = Field(default_factory=list)
    execution_seconds: float = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class PortfolioManagerInputEnvelope(ValidationInputEnvelope):
    """Input envelope for the isolated Portfolio Manager backend."""

    inputs: PortfolioManagerInputs


class PortfolioManagerOutputEnvelope(ValidationOutputEnvelope):
    """Output envelope from the isolated Portfolio Manager backend."""

    outputs: PortfolioManagerOutputs | None = None


def mime_type_for_portfolio_manager_filename(filename: str) -> SupportedMimeType:
    """Return the typed carrier MIME inferred from a safe logical filename."""
    suffix = PurePath(filename).suffix.lower()
    mapping = {
        ".xls": SupportedMimeType.MICROSOFT_EXCEL_XLS,
        ".xlsx": SupportedMimeType.MICROSOFT_EXCEL_XLSX,
        ".xml": SupportedMimeType.APPLICATION_XML,
        ".zip": SupportedMimeType.APPLICATION_ZIP,
    }
    try:
        return mapping[suffix]
    except KeyError as exc:
        msg = f"Unsupported Portfolio Manager report extension: {suffix or '(none)'}"
        raise ValueError(msg) from exc


def build_portfolio_manager_input_envelope(
    *,
    run_id: str,
    validator: Any,
    org_id: str,
    org_name: str,
    workflow_id: str,
    step_id: str,
    step_name: str | None,
    submission_name: str,
    submission_uri: str,
    submission_size_bytes: int,
    submission_sha256: str,
    submission_storage_version: str,
    inputs: PortfolioManagerInputs,
    context: ExecutionContext,
    expected_buildings_list: ResourceFileItem | None = None,
) -> PortfolioManagerInputEnvelope:
    """Build the immutable input envelope consumed by every execution route."""
    return PortfolioManagerInputEnvelope(
        run_id=run_id,
        validator=ValidatorInfo(
            id=str(validator.id),
            type=ValidatorType(validator.validation_type),
            version=str(getattr(validator, "version", "1")),
        ),
        org={"id": org_id, "name": org_name},
        workflow={
            "id": workflow_id,
            "step_id": step_id,
            "step_name": step_name,
        },
        input_files=[
            InputFileItem(
                name=PurePath(submission_name).name,
                mime_type=mime_type_for_portfolio_manager_filename(submission_name),
                role="portfolio-manager-report",
                port_key="portfolio_manager_report",
                uri=submission_uri,
                size_bytes=submission_size_bytes,
                sha256=submission_sha256,
                storage_version=submission_storage_version,
            ),
        ],
        resource_files=(
            [expected_buildings_list] if expected_buildings_list is not None else []
        ),
        inputs=inputs,
        context=ExecutionContext(
            **{
                **context.model_dump(),
                "attempt_contract_version": ATTEMPT_CONTRACT_VERSION,
            }
        ),
    )
