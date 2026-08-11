"""
Pydantic envelopes for the SHACL Advanced validator backend.

The SHACL validator is an Advanced validator — it runs in an isolated
container/Cloud Run Job rather than inside the Django worker. That isolation is
the whole point: SHACL parses untrusted RDF and executes author-supplied SPARQL
(SHACL-AF constraints and SPARQL-ASK assertions), and we never want that running
next to the worker's database credentials, service-account identity, or network.

These schemas define the contract between Django and the SHACL container:

- **Input envelope**: the RDF submission (as an ``InputFileItem`` URI) plus the
  merged shape/ontology text, the resolved engine settings, the resource limits,
  and the author-defined SPARQL-ASK assertions. Django resolves all of this from
  the database (rulesets, ``RulesetAssertion`` rows, settings) before dispatch —
  the container receives only this serialized boundary.
- **Output envelope**: the SHACL findings (as ``ValidationMessage`` rows), the
  ``o.*`` output-value dict (for CEL/Basic output assertions evaluated back in Django),
  the serialized ``sh:ValidationReport`` for evidence download, and the
  container-side SPARQL-ASK assertion counts (folded into the final assertion
  totals by ``AdvancedValidator.post_execute_validate``).

See ADR-2026-05-18 for the SHACL engine design and the cross-repo plan for the
isolation rationale.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    InputFileItem,
    SupportedMimeType,
    ValidationInputEnvelope,
    ValidationOutputEnvelope,
    ValidatorInfo,
    ValidatorType,
)

# Result-handling modes. Mirrors
# ``validibot.validations.validators.shacl.constants`` on the Django side; the
# container applies the resolved mode to decide which findings block.
SHACL_RESULT_FAIL_IMMEDIATELY = "fail_immediately"
SHACL_RESULT_FAIL_AFTER_ASSERTIONS = "fail_after_assertions"
SHACL_RESULT_REPORT_ONLY = "report_only"

# SPARQL-ASK target graphs.
SPARQL_ASK_TARGET_DATA = "data"
SPARQL_ASK_TARGET_RESULTS = "results"
SPARQL_ASK_TARGET_UNION = "union"


class SHACLSparqlAssertionSpec(BaseModel):
    """One author-defined SPARQL-ASK assertion to run inside the container.

    Django rehydrates each ``RulesetAssertion`` row (``assertion_type=SHACL``)
    into one of these specs and ships it in the input envelope. The container
    re-scrubs ``query`` through the AST scrubber before executing it — the form
    already scrubbed at save time, but the runtime re-check is belt-and-braces
    against fixtures/imports that bypass the form.
    """

    target_graph: str = Field(
        default=SPARQL_ASK_TARGET_DATA,
        description="Which graph to run the ASK against: data | results | union.",
    )
    query: str = Field(description="Raw SPARQL ASK query text.")
    severity: str = Field(
        default="ERROR",
        description=(
            "Validibot severity emitted on a false answer (ERROR/WARNING/INFO)."
        ),
    )
    description: str = Field(default="", description="Human-readable label.")
    error_message_template: str = Field(
        default="",
        description="Message shown when the ASK returns false.",
    )
    success_message: str = Field(
        default="",
        description="Optional message recorded when the ASK returns true.",
    )
    assertion_id: int | None = Field(
        default=None,
        description="RulesetAssertion.pk, for finding attribution back in Django.",
    )

    model_config = {"extra": "forbid"}


class SHACLInputs(BaseModel):
    """SHACL engine configuration resolved by Django and run in the container.

    Everything the container needs to validate without any database access. The
    shape/ontology text is already merged (library default + step extras), the
    RDF format is already resolved from the submission filename, and the resource
    limits are already clamped to their hard caps Django-side — the container
    treats these as authoritative but still hard-caps defensively.
    """

    shapes_text: str = Field(description="Merged SHACL shapes graph (Turtle).")
    ontology_text: str = Field(
        default="",
        description="Optional merged ontology graph (Turtle) for inference.",
    )
    rdf_format: str = Field(
        default="turtle",
        description=(
            "Resolved rdflib format slug for the submission "
            "(turtle | json-ld | xml | nt | nquads)."
        ),
    )
    inference_mode: str = Field(
        default="rdfs",
        description="pyshacl inference mode: none | rdfs | owlrl | both.",
    )
    advanced_shacl: bool = Field(
        default=False,
        description="Whether the author requested SHACL-AF / embedded SPARQL.",
    )
    enable_advanced_features: bool = Field(
        default=False,
        description=(
            "Deployment gate forwarded from SHACL_ENABLE_ADVANCED_FEATURES. "
            "Even when advanced_shacl is requested, embedded SPARQL execution is "
            "only accepted when this is also true."
        ),
    )
    submission_format: str = Field(
        default="auto",
        description=(
            "Original author-selected submission format (auto/turtle/...). "
            "Retained for diagnostics; the container parses using rdf_format."
        ),
    )
    shacl_result_handling: str = Field(
        default=SHACL_RESULT_FAIL_AFTER_ASSERTIONS,
        description="fail_immediately | fail_after_assertions | report_only.",
    )
    bundled_standards: list[str] = Field(
        default_factory=list,
        description="Opted-in bundled standard identifiers (e.g. brick-1.4).",
    )
    sparql_ask_assertions: list[SHACLSparqlAssertionSpec] = Field(
        default_factory=list,
        description="Author-defined SPARQL-ASK assertions to evaluate post-SHACL.",
    )

    # ── Resource limits (already clamped Django-side; re-clamped in container) ──
    max_data_triples: int = Field(default=100_000, gt=0)
    max_shape_triples: int = Field(default=50_000, gt=0)
    max_ontology_triples: int = Field(default=100_000, gt=0)
    max_validation_depth: int = Field(default=25, gt=0)
    # Mirror the producer-side defaults so a direct/shared-envelope consumer
    # (or a test) that doesn't set these explicitly behaves like a real launch.
    # Django (validations/.../shacl/launch.py) and the container backend
    # (validibot-validator-backends shacl/engine.py) both default pySHACL to
    # 300s (hard cap 1800s) and SPARQL-ASK to 10s; this contract must not lag.
    pyshacl_timeout_seconds: int = Field(default=300, gt=0)
    sparql_query_timeout_seconds: int = Field(default=10, gt=0)

    model_config = {"extra": "forbid"}


class SHACLFinding(BaseModel):
    """One SHACL finding with the full detail Django
    gneeds to rebuild a ``ValidationIssue``.

    The generic ``ValidationMessage`` on the output envelope is lossy — it has no
    ``meta`` (SHACL focus node / source shape / constraint component) and no
    ``assertion_id`` (SPARQL-ASK attribution). SHACL carries those through this
    richer per-finding model so Django's ``post_execute_validate`` can reconstruct
    findings with the same fidelity as the old in-process path.

    ``severity`` is a plain string (ERROR / WARNING / INFO / SUCCESS) rather than
    the shared ``Severity`` enum because SHACL emits SUCCESS rows for passing
    SPARQL-ASK assertions with a configured success message, and ``Severity`` only
    covers INFO/WARNING/ERROR. Django maps it back to its own severity enum.
    """

    path: str = Field(default="")
    message: str = Field(description="Human-readable finding text.")
    severity: str = Field(description="ERROR | WARNING | INFO | SUCCESS.")
    code: str = Field(default="")
    meta: dict[str, Any] = Field(default_factory=dict)
    assertion_id: int | None = Field(default=None)

    model_config = {"extra": "forbid"}


class SHACLOutputs(BaseModel):
    """SHACL validation results and the ``o.*`` output-value dict.

    The output-value fields (``parse_ok`` … ``shacl_total_count``) mirror the catalog
    entries declared in the Django SHACL ``ValidatorConfig`` — Django's
    ``extract_output_values`` pulls exactly those keys for CEL/Basic assertion
    evaluation. The remaining fields carry evidence (the serialized report) and
    the container-side SPARQL-ASK assertion counts.
    """

    conforms: bool = Field(description="Whether the data graph conforms to the shapes.")

    findings: list[SHACLFinding] = Field(
        default_factory=list,
        description=(
            "Blocking + advisory findings (SHACL results, SPARQL-ASK outcomes, "
            "bundle/parse/engine messages) with full meta for Django to rebuild "
            "ValidationIssue rows. Already filtered per shacl_result_handling."
        ),
    )

    # ── o.* output values (must stay aligned with the SHACL ValidatorConfig catalog) ──
    parse_ok: bool = Field(description="Whether the submitted RDF parsed.")
    parse_serialization: str = Field(description="rdflib format used to parse.")
    triple_count: int = Field(default=0, ge=0)
    namespaces_present: list[str] = Field(default_factory=list)
    has_s223_namespace: bool = Field(default=False)
    has_g36_namespace: bool = Field(default=False)
    has_brick_namespace: bool = Field(default=False)
    shacl_violation_count: int = Field(default=0, ge=0)
    shacl_warning_count: int = Field(default=0, ge=0)
    shacl_info_count: int = Field(default=0, ge=0)
    shacl_total_count: int = Field(default=0, ge=0)

    # ── Evidence + run metadata ──
    results_graph_turtle: str = Field(
        default="",
        description="Serialized sh:ValidationReport (Turtle) for evidence download.",
    )
    shacl_shapes_sha256: str = Field(default="")
    shacl_ontology_sha256: str = Field(default="")
    advanced_shacl_requested: bool = Field(default=False)
    shacl_result_handling: str = Field(default="")

    # ── Container-side SPARQL-ASK assertion tallies (folded into AssertionStats) ──
    assertion_total: int = Field(default=0, ge=0)
    assertion_failures: int = Field(default=0, ge=0)

    execution_seconds: float = Field(default=0.0, ge=0)
    pyshacl_version: str | None = Field(default=None)

    model_config = {"extra": "forbid"}


class SHACLInputEnvelope(ValidationInputEnvelope):
    """Input envelope for SHACL validator containers."""

    inputs: SHACLInputs


class SHACLOutputEnvelope(ValidationOutputEnvelope):
    """Output envelope from SHACL validator containers.

    ``outputs`` can be ``None`` for runtime-failure cases where the engine never
    produced a report (e.g. the submission failed to parse before SHACL ran).
    """

    outputs: SHACLOutputs | None = None


# Default descriptive role and MIME for the submitted RDF graph. The backend
# selects this item through its required ``data_graph`` port key.
_RDF_FORMAT_TO_MIME: dict[str, SupportedMimeType] = {
    "turtle": SupportedMimeType.RDF_TURTLE,
    "n3": SupportedMimeType.RDF_TURTLE,
    "json-ld": SupportedMimeType.RDF_JSON_LD,
    "xml": SupportedMimeType.RDF_XML,
    "nt": SupportedMimeType.RDF_N_TRIPLES,
    "nquads": SupportedMimeType.RDF_N_QUADS,
}


def mime_type_for_rdf_format(rdf_format: str) -> SupportedMimeType:
    """Map a resolved rdflib format slug to a SupportedMimeType (Turtle default)."""
    return _RDF_FORMAT_TO_MIME.get(rdf_format, SupportedMimeType.RDF_TURTLE)


def build_shacl_input_envelope(
    *,
    run_id: str,
    validator,
    org_id: str,
    org_name: str,
    workflow_id: str,
    step_id: str,
    step_name: str | None,
    submission_uri: str,
    submission_size_bytes: int,
    submission_sha256: str,
    submission_storage_version: str,
    inputs: SHACLInputs,
    callback_url: str,
    execution_bundle_uri: str,
    execution_attempt_id: str,
    step_run_id: str,
    expected_output_uri: str,
    callback_id: str | None = None,
    callback_nonce: str | None = None,
    callback_nonce_commitment: str | None = None,
    skip_callback: bool = False,
) -> SHACLInputEnvelope:
    """Build a ``SHACLInputEnvelope`` from Django validation data.

    Args:
        run_id: ValidationRun ID.
        validator: Validator-like object (id/validation_type/version attrs).
        org_id / org_name: Organization identity.
        workflow_id / step_id / step_name: Workflow context.
        submission_uri: Storage URI for the RDF submission (gs:// or file://).
        submission_size_bytes: Expected exact submission size and byte ceiling.
        submission_sha256: Expected SHA-256 of the RDF submission.
        submission_storage_version: Immutable provider version for the object.
        inputs: Fully-resolved ``SHACLInputs`` (shapes/ontology/settings/asks).
        callback_url: URL the container POSTs to on completion.
        execution_bundle_uri: Base URI for this run's bundle.
        callback_id: Idempotency key echoed back in the callback.
        callback_nonce: Per-attempt secret returned in the callback payload.
        callback_nonce_commitment: Public commitment to ``callback_nonce``.
        skip_callback: True for synchronous (Docker) execution.
    """
    input_files = [
        InputFileItem(
            name="submission.rdf",
            mime_type=mime_type_for_rdf_format(inputs.rdf_format),
            role="data-graph",
            port_key="data_graph",
            uri=submission_uri,
            size_bytes=submission_size_bytes,
            sha256=submission_sha256,
            storage_version=submission_storage_version,
        ),
    ]

    context = ExecutionContext(
        execution_attempt_id=execution_attempt_id,
        step_run_id=step_run_id,
        attempt_contract_version=ATTEMPT_CONTRACT_VERSION,
        expected_output_uri=expected_output_uri,
        callback_id=callback_id,
        callback_nonce=callback_nonce,
        callback_nonce_commitment=callback_nonce_commitment,
        callback_url=callback_url,
        execution_bundle_uri=execution_bundle_uri,
        skip_callback=skip_callback,
    )

    return SHACLInputEnvelope(
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
        input_files=input_files,
        inputs=inputs,
        context=context,
    )
