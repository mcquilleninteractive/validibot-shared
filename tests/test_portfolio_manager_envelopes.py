"""Tests for the Portfolio Manager backend interchange contract.

Portfolio Manager processes untrusted spreadsheet, XML, and ZIP carriers in an
isolated backend. These tests pin strict author configuration, EBL semantics,
typed per-property facts, and immutable file-envelope construction so producer
and consumer cannot silently drift.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from validibot_shared.portfolio_manager import (
    ExpectedBuildingsList,
    PortfolioManagerInputEnvelope,
    PortfolioManagerInputs,
    PortfolioManagerOutputs,
    PortfolioManagerPropertyResult,
    build_portfolio_manager_input_envelope,
    mime_type_for_portfolio_manager_filename,
    validate_expected_buildings_list_json,
)
from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    SupportedMimeType,
    ValidatorType,
)


def _context() -> ExecutionContext:
    """Return the smallest valid synchronous context for envelope tests."""
    return ExecutionContext(
        execution_attempt_id="attempt-1",
        step_run_id="step-run-1",
        attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
        expected_output_uri="file:///tmp/output.json",
        execution_bundle_uri="file:///tmp/bundle/",
        skip_callback=True,
    )


def test_expected_buildings_list_rejects_duplicate_opaque_ids() -> None:
    """Duplicate IDs would make a per-building EUIt override ambiguous."""
    with pytest.raises(ValidationError, match="duplicate"):
        ExpectedBuildingsList(
            id_field={
                "kind": "standard_id",
                "name": "State of Washington Clean Buildings Standard",
            },
            buildings=[
                {"id_value": "001", "euit": "40"},
                {"id_value": "001", "euit": "45"},
            ],
        )


def test_named_ebl_identity_requires_the_portfolio_manager_label() -> None:
    """A Standard ID without its program name cannot be matched deterministically."""
    with pytest.raises(ValidationError, match="name is required"):
        ExpectedBuildingsList(
            id_field={"kind": "standard_id"},
            buildings=[{"id_value": "WA-1"}],
        )


def test_explicit_policy_fields_are_preserved_without_profile_mutation() -> None:
    """The shared boundary must execute exactly the policy authored in the workflow."""
    inputs = PortfolioManagerInputs(
        require_complete_reporting_period=False,
        require_benchmark_ready=True,
        require_form_c_ready=False,
        require_weather_normalized_site_eui=True,
        require_washington_standard_id=True,
        meter_gap_policy="warning",
        estimated_energy_policy="error",
    )

    assert inputs.require_complete_reporting_period is False
    assert inputs.require_benchmark_ready is True
    assert inputs.require_form_c_ready is False
    assert inputs.require_weather_normalized_site_eui is True
    assert inputs.require_washington_standard_id is True
    assert inputs.meter_gap_policy == "warning"
    assert inputs.estimated_energy_policy == "error"


def test_inputs_reject_unversioned_profile_shortcuts() -> None:
    """V1 has no hidden preset channel that can override explicit author choices."""
    with pytest.raises(ValidationError, match="profile"):
        PortfolioManagerInputs(profile="washington_cbps_tier1_euit")


def test_ebl_json_rejects_duplicate_keys_before_schema_validation() -> None:
    """Duplicate JSON keys must not silently overwrite target evidence."""
    content = (
        '{"schema_version":"1.0","schema_version":"1.0",'
        '"id_field":{"kind":"property_id"},'
        '"euit_unit":"kBtu/ft2/year",'
        '"buildings":[{"id_value":"001"}]}'
    )

    with pytest.raises(ValueError, match="duplicate JSON key"):
        validate_expected_buildings_list_json(content)


def test_ebl_json_requires_canonical_decimal_strings() -> None:
    """EUIt values use decimal strings so evidence never passes through floats."""
    content = (
        '{"schema_version":"1.0","id_field":{"kind":"property_id"},'
        '"euit_unit":"kBtu/ft2/year",'
        '"buildings":[{"id_value":"001","euit":40.1}]}'
    )

    with pytest.raises(ValueError, match="canonical decimal string"):
        validate_expected_buildings_list_json(content)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("report.xls", SupportedMimeType.MICROSOFT_EXCEL_XLS),
        ("report.xlsx", SupportedMimeType.MICROSOFT_EXCEL_XLSX),
        ("report.xml", SupportedMimeType.APPLICATION_XML),
        ("reports.zip", SupportedMimeType.APPLICATION_ZIP),
    ],
)
def test_portfolio_manager_mime_mapping_covers_supported_carriers(
    filename: str,
    expected: SupportedMimeType,
) -> None:
    """Every advertised carrier must cross the envelope as an accepted MIME."""
    assert mime_type_for_portfolio_manager_filename(filename) == expected


def test_input_envelope_builder_binds_the_report_port() -> None:
    """The backend locates submission bytes by a stable role and port key."""
    validator = type(
        "Validator",
        (),
        {
            "id": "validator-1",
            "validation_type": ValidatorType.PORTFOLIO_MANAGER,
            "version": "1.0.0",
        },
    )()
    envelope = build_portfolio_manager_input_envelope(
        run_id="run-1",
        validator=validator,
        org_id="org-1",
        org_name="Organization",
        workflow_id="workflow-1",
        step_id="step-1",
        step_name="Portfolio Manager",
        submission_name="portfolio.xlsx",
        submission_uri="file:///tmp/portfolio.xlsx",
        submission_size_bytes=123,
        submission_sha256="a" * 64,
        submission_storage_version="sha256:" + "a" * 64,
        inputs=PortfolioManagerInputs(),
        context=_context(),
    )

    assert isinstance(envelope, PortfolioManagerInputEnvelope)
    assert envelope.input_files[0].role == "portfolio-manager-report"
    assert envelope.input_files[0].port_key == "portfolio_manager_report"
    assert envelope.validator.type == ValidatorType.PORTFOLIO_MANAGER


def test_outputs_round_trip_decimal_metrics_without_float_loss() -> None:
    """Energy targets and ratios remain decimals across the JSON boundary."""
    outputs = PortfolioManagerOutputs(
        submission_structure="single_report",
        file_count=1,
        valid_file_count=1,
        invalid_file_count=0,
        property_count=1,
        reporting_cycle_count=1,
        reporting_cycles_match=True,
        property_results=[
            PortfolioManagerPropertyResult(
                member_name="report.xlsx",
                carrier="xlsx",
                property_id="123",
                weather_normalized_site_eui_kbtu_ft2_yr="39.5",
                resolved_euit_kbtu_ft2_yr="40",
                resolved_euit_source="default",
                euit_ratio="0.9875",
                euit_margin_kbtu_ft2_yr="0.5",
                euit_percent_difference="1.25",
                meets_euit=True,
                near_euit=False,
            )
        ],
    )
    restored = PortfolioManagerOutputs.model_validate_json(outputs.model_dump_json())

    assert restored.property_results[0].euit_ratio == Decimal("0.9875")
    assert restored.property_results[0].property_id == "123"
