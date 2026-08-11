"""Tests for the SHACL Advanced validator envelopes.

This suite covers the contract that lets Django hand SHACL validation off to an
isolated container backend. The container parses untrusted RDF and runs
author-supplied SPARQL, so the envelope boundary is security-critical: anything
the container needs must travel *in* the envelope (no database, no settings, no
secrets reachable from the container), and anything it produces must round-trip
back to Django through ``SHACLOutputs``.

We therefore assert three things:

1. The typed envelopes accept well-formed payloads and round-trip through JSON
   (Django serializes the input; the container serializes the output).
2. ``extra="forbid"`` is honoured so a drifting producer/consumer fails loudly
   rather than silently dropping fields across the trust boundary.
3. The ``SHACLOutputs`` output-value fields stay aligned with what Django's
   ``extract_output_values`` expects (the ``o.*`` catalog keys).
"""

import pytest
from pydantic import ValidationError

from validibot_shared.canonicalization import compute_callback_nonce_commitment
from validibot_shared.shacl.envelopes import (
    SHACL_RESULT_REPORT_ONLY,
    SHACLInputEnvelope,
    SHACLInputs,
    SHACLOutputEnvelope,
    SHACLOutputs,
    SHACLSparqlAssertionSpec,
    build_shacl_input_envelope,
    mime_type_for_rdf_format,
)
from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    SupportedMimeType,
    ValidationStatus,
    ValidatorType,
)

# The o.* output-value keys Django's SHACL catalog declares. If SHACLOutputs ever
# drops one of these, the Django extractor would silently lose a CEL signal —
# this list is the canary.
EXPECTED_SIGNAL_KEYS = {
    "parse_ok",
    "parse_serialization",
    "triple_count",
    "namespaces_present",
    "has_s223_namespace",
    "has_g36_namespace",
    "has_brick_namespace",
    "shacl_violation_count",
    "shacl_warning_count",
    "shacl_info_count",
    "shacl_total_count",
}
TEST_CALLBACK_NONCE = "A" * 43
TEST_CALLBACK_NONCE_COMMITMENT = compute_callback_nonce_commitment(
    TEST_CALLBACK_NONCE,
)


def _base_kwargs():
    """Minimal valid envelope metadata shared by the input-envelope tests."""
    return {
        "run_id": "run-123",
        "validator": {"id": "val-1", "type": ValidatorType.SHACL, "version": "1"},
        "org": {"id": "org-1", "name": "ValidiBot"},
        "workflow": {"id": "wf-1", "step_id": "step-1", "step_name": "SHACL"},
        "context": ExecutionContext(
            callback_url="https://example.com/cb",
            callback_id="execution-attempt-attempt-123",
            callback_nonce=TEST_CALLBACK_NONCE,
            callback_nonce_commitment=TEST_CALLBACK_NONCE_COMMITMENT,
            execution_bundle_uri="gs://bucket/run-123/",
            execution_attempt_id="attempt-123",
            step_run_id="step-run-123",
            attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
            expected_output_uri="gs://bucket/run-123/output.json",
        ),
    }


# ── Input envelope ──────────────────────────────────────────────────────────
# The input envelope is what Django writes to storage before triggering the
# container. It must carry the merged shapes, resolved settings, and the
# author's SPARQL-ASK assertions, because the container has no DB to read them.


def test_shacl_input_envelope_requires_typed_inputs():
    """The envelope must coerce a raw dict into a typed ``SHACLInputs``.

    Django builds the inputs as a dict in some code paths; the typed override on
    ``SHACLInputEnvelope.inputs`` is what guarantees the container receives a
    validated structure rather than arbitrary JSON.
    """
    envelope = SHACLInputEnvelope(
        **_base_kwargs(),
        input_files=[],
        inputs={
            "shapes_text": "@prefix sh: <http://www.w3.org/ns/shacl#> .",
            "rdf_format": "turtle",
            "inference_mode": "rdfs",
            "sparql_ask_assertions": [
                {"target_graph": "data", "query": "ASK { ?s ?p ?o }"},
            ],
        },
    )

    assert envelope.inputs.shapes_text.startswith("@prefix sh:")
    assert envelope.inputs.sparql_ask_assertions[0].target_graph == "data"
    # advanced features default off — the deployment gate must be opt-in.
    assert envelope.inputs.advanced_shacl is False
    assert envelope.inputs.enable_advanced_features is False


def test_shacl_inputs_rejects_nonpositive_limits():
    """Resource limits must be positive so a corrupt envelope can't disable caps.

    A zero/negative triple cap would mean "no limit" if it slipped through — the
    container relies on these bounds as a DoS backstop, so the schema refuses
    them at the boundary.
    """
    with pytest.raises(ValidationError):
        SHACLInputs(shapes_text="x", max_data_triples=0)
    with pytest.raises(ValidationError):
        SHACLInputs(shapes_text="x", pyshacl_timeout_seconds=-1)


def test_shacl_input_envelope_forbids_unknown_fields():
    """Unknown top-level keys are rejected (``extra='forbid'``).

    Silent field-dropping across the Django/container trust boundary would let a
    contract mismatch pass unnoticed; we want a hard failure instead.
    """
    with pytest.raises(ValidationError):
        SHACLInputEnvelope(
            **_base_kwargs(),
            input_files=[],
            inputs={"shapes_text": "x"},
            unexpected="nope",
        )


def test_build_shacl_input_envelope_constructs_expected_payload():
    """The helper gives the data-graph port a fetchable, typed file identity."""
    inputs = SHACLInputs(
        shapes_text="@prefix sh: <http://www.w3.org/ns/shacl#> .",
        rdf_format="json-ld",
    )
    envelope = build_shacl_input_envelope(
        run_id="run-1",
        validator=type(
            "Validator",
            (),
            {"id": 1, "validation_type": ValidatorType.SHACL, "version": "2"},
        )(),
        org_id="org-1",
        org_name="ValidiBot",
        workflow_id="wf-1",
        step_id="step-1",
        step_name="Validate graph",
        submission_uri="gs://bucket/submission.jsonld",
        submission_size_bytes=789,
        submission_sha256="1" * 64,
        submission_storage_version="1700000000000000",
        inputs=inputs,
        callback_url="https://example.com/callback",
        execution_bundle_uri="gs://bucket/run-1/",
        execution_attempt_id="attempt-1",
        step_run_id="step-run-1",
        expected_output_uri="gs://bucket/run-1/output.json",
        skip_callback=True,
    )

    assert envelope.input_files[0].uri == "gs://bucket/submission.jsonld"
    assert envelope.input_files[0].role == "data-graph"
    assert envelope.input_files[0].port_key == "data_graph"
    assert envelope.input_files[0].mime_type == SupportedMimeType.RDF_JSON_LD
    assert envelope.validator.version == "2"
    assert envelope.context.skip_callback is True


def test_mime_type_for_rdf_format_defaults_to_turtle():
    """An unknown format falls back to Turtle, the most common SHACL encoding.

    Defaulting (rather than raising) keeps a slightly-off format hint from
    blocking a run; the container still parses using the explicit ``rdf_format``.
    """
    assert mime_type_for_rdf_format("turtle") == SupportedMimeType.RDF_TURTLE
    assert mime_type_for_rdf_format("xml") == SupportedMimeType.RDF_XML
    assert mime_type_for_rdf_format("totally-unknown") == SupportedMimeType.RDF_TURTLE


# ── SPARQL-ASK spec ─────────────────────────────────────────────────────────
# SPARQL-ASK assertions touch the graph, so they execute in the container, not
# in Django. The spec is the serialized form of a RulesetAssertion row.


def test_sparql_assertion_spec_defaults():
    """A spec needs only a query; everything else has a safe default.

    Defaulting ``severity`` to ERROR and ``target_graph`` to the data graph
    matches the engine's historical behaviour so existing assertions keep their
    meaning after the move to the container.
    """
    spec = SHACLSparqlAssertionSpec(query="ASK { ?s a ?type }")
    assert spec.severity == "ERROR"
    assert spec.target_graph == "data"
    assert spec.assertion_id is None


# ── Output envelope ─────────────────────────────────────────────────────────
# The output envelope is what the container writes back. Its output-value fields feed
# Django's CEL/Basic assertion evaluation; its assertion tallies are folded into
# the final AssertionStats.


def test_shacl_outputs_signal_keys_cover_catalog():
    """Every catalog output-value key must exist as a field on ``SHACLOutputs``.

    Django's ``extract_output_values`` reads these keys off the envelope; a
    missing field here would surface as a null CEL signal at runtime with no
    error. This test pins the alignment at the contract layer.
    """
    field_names = set(SHACLOutputs.model_fields)
    missing = EXPECTED_SIGNAL_KEYS - field_names
    assert not missing, f"SHACLOutputs missing output-value fields: {missing}"


def test_shacl_output_envelope_round_trips():
    """A full output envelope round-trips through JSON unchanged.

    Django deserializes ``output.json`` written by the container; this proves the
    typed subclass reconstructs the ``SHACLOutputs`` (including the serialized
    report and assertion counts) faithfully.
    """
    envelope = SHACLOutputEnvelope(
        run_id="run-123",
        step_run_id="step-run-123",
        execution_attempt_id="attempt-123",
        attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
        input_envelope_sha256="a" * 64,
        output_uri="gs://bucket/run-123/output.json",
        validator={"id": "val-1", "type": ValidatorType.SHACL, "version": "1"},
        status=ValidationStatus.FAILED_VALIDATION,
        timing={},
        messages=[],
        outputs=SHACLOutputs(
            conforms=False,
            parse_ok=True,
            parse_serialization="turtle",
            triple_count=42,
            has_s223_namespace=True,
            shacl_violation_count=2,
            shacl_total_count=2,
            results_graph_turtle="@prefix sh: <http://www.w3.org/ns/shacl#> .",
            shacl_result_handling=SHACL_RESULT_REPORT_ONLY,
            assertion_total=3,
            assertion_failures=1,
            execution_seconds=0.5,
        ),
    )

    restored = SHACLOutputEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored.outputs.conforms is False
    assert restored.outputs.triple_count == 42
    assert restored.outputs.assertion_failures == 1
    assert restored.status == ValidationStatus.FAILED_VALIDATION


def test_shacl_output_envelope_allows_none_outputs():
    """``outputs`` may be None for a runtime failure before SHACL produced a report.

    The container sets a FAILED_RUNTIME status with ``outputs=None`` when, e.g.,
    the submission fails to parse — Django must still be able to deserialize that
    envelope to surface the failure.
    """
    envelope = SHACLOutputEnvelope(
        run_id="run-123",
        step_run_id="step-run-123",
        execution_attempt_id="attempt-123",
        attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
        input_envelope_sha256="a" * 64,
        output_uri="gs://bucket/run-123/output.json",
        validator={"id": "val-1", "type": ValidatorType.SHACL, "version": "1"},
        status=ValidationStatus.FAILED_RUNTIME,
        timing={},
        outputs=None,
    )
    assert envelope.outputs is None
