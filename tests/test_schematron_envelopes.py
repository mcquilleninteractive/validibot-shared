"""Tests for the Schematron container contract (ADR-2026-07-01, D4b/D9).

The Schematron validator ships the author's rules **inline as text** (the
SHACL ``shapes_text`` pattern — the container compiles them itself), and its
outputs carry an ``engine_status`` failure taxonomy where ``passed`` is
*tri-state* — True/False when the engine ran, ``None`` (unknown) when it
could not. These tests pin those contract properties so a refactor cannot
silently weaken them: the Django side and the validator backend both program
against exactly this shape.
"""

import pytest
from pydantic import ValidationError

from validibot_shared.canonicalization import compute_callback_nonce_commitment
from validibot_shared.schematron.envelopes import (
    ENGINE_ERROR_RULES_INVALID,
    ENGINE_STATUS_OK,
    ENGINE_STATUS_TIMEOUT,
    SchematronFinding,
    SchematronInputEnvelope,
    SchematronInputs,
    SchematronOutputEnvelope,
    SchematronOutputs,
    build_schematron_input_envelope,
)
from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    SupportedMimeType,
    ValidationStatus,
    ValidatorType,
)

# Test constants to avoid magic values
DEFAULT_MAX_FINDINGS = 500
DEFAULT_XSLT_TIMEOUT = 60
TEST_ERROR_COUNT = 3
RULES_SHA = "b" * 64
TEST_CALLBACK_NONCE = "A" * 43
TEST_CALLBACK_NONCE_COMMITMENT = compute_callback_nonce_commitment(
    TEST_CALLBACK_NONCE,
)

SCH_SOURCE = (
    '<schema xmlns="http://purl.oclc.org/dsdl/schematron">'
    "<pattern><rule context='/'><assert test='true()'>ok</assert></rule>"
    "</pattern></schema>"
)


class _ValidatorStub:
    """Duck-typed validator (id/validation_type/version) for the builder."""

    id = "val-1"
    validation_type = "SCHEMATRON"
    version = "1"


def _inputs(**overrides) -> SchematronInputs:
    base = {
        "schematron_text": SCH_SOURCE,
        "schematron_sha256": RULES_SHA,
    }
    base.update(overrides)
    return SchematronInputs(**base)


def test_inputs_carry_inline_rules_and_limit_defaults():
    """Inputs ship the rules inline with provenance sha and D8 defaults.

    Inline text is the whole delivery model (no staging, no artefact URIs):
    the container gets everything it needs from the envelope alone, exactly
    like SHACL's shapes_text.
    """
    inputs = _inputs()

    assert inputs.schematron_text == SCH_SOURCE
    assert inputs.schematron_sha256 == RULES_SHA
    assert inputs.max_findings == DEFAULT_MAX_FINDINGS
    assert inputs.xslt_timeout_seconds == DEFAULT_XSLT_TIMEOUT


def test_inputs_require_the_rules_text():
    """Omitting schematron_text is a validation error, not a default.

    An input envelope without rules would force the container to run
    nothing and report... something. Refuse at the contract layer.
    """
    with pytest.raises(ValidationError):
        SchematronInputs()


def test_outputs_default_to_unknown_passed_not_false():
    """``passed`` defaults to None — unknown, not failed (D9).

    A default of False would make an unpopulated envelope read as "the
    document failed the rules"; None forces every consumer to distinguish
    "engine didn't run" from "rules failed".
    """
    outputs = SchematronOutputs()
    assert outputs.passed is None
    assert outputs.engine_status == ENGINE_STATUS_OK


def test_engine_failure_shapes_round_trip():
    """Timeout and rules-invalid outputs serialize and re-validate losslessly.

    The callback path deserializes output.json with this model; the D9
    fields must survive the JSON round trip exactly, including the
    machine hint that lets Django distinguish "your rules don't compile"
    from a generic engine error.
    """
    timeout = SchematronOutputs(
        engine_status=ENGINE_STATUS_TIMEOUT,
        engine_message="Transform exceeded 60s",
        passed=None,
    )
    invalid_rules = SchematronOutputs(
        engine_status="error",
        engine_error_code=ENGINE_ERROR_RULES_INVALID,
        engine_message="Schematron failed to compile: unexpected element",
        passed=None,
    )
    for outputs, status in (
        (timeout, ValidationStatus.FAILED_RUNTIME),
        (invalid_rules, ValidationStatus.FAILED_RUNTIME),
    ):
        envelope = SchematronOutputEnvelope(
            run_id="run-1",
            step_run_id="step-run-1",
            execution_attempt_id="attempt-1",
            attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
            input_envelope_sha256="a" * 64,
            output_uri="gs://bucket/run-1/output.json",
            validator={"id": "v1", "type": ValidatorType.SCHEMATRON, "version": "1"},
            status=status,
            timing={},
            outputs=outputs,
        )
        restored = SchematronOutputEnvelope.model_validate(
            envelope.model_dump(mode="json"),
        )
        assert restored.outputs.engine_status == outputs.engine_status
        assert restored.outputs.engine_error_code == outputs.engine_error_code
        assert restored.outputs.passed is None


def test_findings_map_and_provenance_round_trip():
    """Findings keep native ids/locations; provenance keeps the rules sha."""
    outputs = SchematronOutputs(
        engine_status=ENGINE_STATUS_OK,
        passed=False,
        error_count=TEST_ERROR_COUNT,
        finding_rule_ids_by_severity={"BR-CO-15": "ERROR", "BR-05": "WARNING"},
        findings=[
            SchematronFinding(
                rule_id="BR-CO-15",
                message="Totals must reconcile.",
                severity="ERROR",
                location_xpath="/Invoice/LegalMonetaryTotal",
                flag="fatal",
            ),
        ],
        schematron_sha256=RULES_SHA,
        query_binding="xslt2",
        engine="SaxonC-HE 12.9",
    )

    restored = SchematronOutputs.model_validate(outputs.model_dump(mode="json"))
    assert restored.finding_rule_ids_by_severity["BR-CO-15"] == "ERROR"
    assert restored.findings[0].rule_id == "BR-CO-15"
    assert restored.findings[0].location_xpath == "/Invoice/LegalMonetaryTotal"
    assert restored.schematron_sha256 == RULES_SHA
    assert restored.query_binding == "xslt2"


def test_outputs_forbid_unknown_fields():
    """extra="forbid" holds — a typo'd field fails loudly, not silently.

    Contract models must reject unknown keys so a mismatched backend/Django
    version pair surfaces as an explicit error instead of dropped data.
    This also guards the 0.11 → 0.12 break: old pack_* fields are refused.
    """
    with pytest.raises(ValidationError):
        SchematronOutputs(engine_status="ok", pack_id="stale-field")


def test_build_schematron_input_envelope_assembles_the_xml_submission():
    """The builder produces a valid envelope with an XML primary input.

    Pins the file-item conventions (name/mime/role) the container reads and
    that ``ValidatorType.SCHEMATRON`` exists — the builder would crash
    without the enum member.
    """
    envelope = build_schematron_input_envelope(
        run_id="run-1",
        validator=_ValidatorStub(),
        org_id="org-1",
        org_name="ValidiBot",
        workflow_id="wf-1",
        step_id="step-1",
        step_name="Peppol rules",
        submission_uri="gs://bucket/run-1/submission.xml",
        submission_size_bytes=321,
        submission_sha256="1" * 64,
        submission_storage_version="1700000000000000",
        inputs=_inputs(),
        callback_url="https://example.com/callback",
        callback_id="execution-attempt-attempt-1",
        callback_nonce=TEST_CALLBACK_NONCE,
        callback_nonce_commitment=TEST_CALLBACK_NONCE_COMMITMENT,
        execution_bundle_uri="gs://bucket/run-1/",
        execution_attempt_id="attempt-1",
        step_run_id="step-run-1",
        expected_output_uri="gs://bucket/run-1/output.json",
    )

    assert isinstance(envelope, SchematronInputEnvelope)
    assert envelope.validator.type == ValidatorType.SCHEMATRON
    file_item = envelope.input_files[0]
    assert file_item.name == "submission.xml"
    assert file_item.mime_type == SupportedMimeType.APPLICATION_XML
    assert file_item.role == "xml-document"
    assert file_item.port_key == "xml_document"
    assert envelope.inputs.schematron_text == SCH_SOURCE
