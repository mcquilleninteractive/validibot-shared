"""
Pydantic envelopes for the Schematron Advanced validator backend.

The Schematron validator is an Advanced validator — it runs in an isolated
container/Cloud Run Job rather than inside the Django worker. Schematron
rules compile to XSLT (a full programming language), so author-uploaded
rules are executable code and only ever run inside the sandboxed container:
no database, no secrets, no network egress, locked-down engine
(ADR-2026-07-01, decisions D4/D8).

These schemas define the contract between Django and the Schematron
container:

- **Input envelope**: the XML submission (as an ``InputFileItem`` URI) plus
  the author's Schematron rules **inline as text** — exactly how SHACL
  ships its merged shapes text. Django resolves the rules from the step's
  ``Ruleset`` before dispatch; the container compiles them (SchXslt2 →
  XSLT, baked into the image as fixed tooling) and runs the result over the
  submission. The D8 resource limits ride along, already clamped
  Django-side; the container re-clamps defensively.
- **Output envelope**: the parsed SVRL summary — per-severity counts, the
  ``finding_rule_ids_by_severity`` map, structured findings preserving
  native rule ids/locations — plus ``engine_status`` (D9: findings are only
  meaningful when the engine actually ran) and provenance (the sha256 of
  the executed rules, the detected query binding, and the engine that ran).
"""

from __future__ import annotations

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

# ── D9 engine status: "couldn't run the rules" ≠ "the rules failed" ────────
# ``passed``/findings on the outputs are only meaningful when the engine
# status is OK. On error/timeout, Django surfaces a single reserved
# infrastructure finding and never synthesises rule findings.
ENGINE_STATUS_OK = "ok"
ENGINE_STATUS_ERROR = "error"
ENGINE_STATUS_TIMEOUT = "timeout"

# Machine hints for ``SchematronOutputs.engine_error_code`` — Django maps
# these to its reserved ``schematron.*`` finding codes.
#
# ``rules_invalid``: the author's uploaded Schematron failed to compile.
# That's a workflow-authoring problem, not a fact about the submitted
# document — the submitter's run still reads "the check couldn't run".
ENGINE_ERROR_RULES_INVALID = "rules_invalid"
ENGINE_ERROR_BACKEND_UNAVAILABLE = "backend_unavailable"

# Schematron query bindings (declared by the .sch root's ``queryBinding``
# attribute; the container detects and echoes it for provenance).
QUERY_BINDING_XSLT1 = "xslt1"
QUERY_BINDING_XSLT2 = "xslt2"


class SchematronInputs(BaseModel):
    """Schematron run configuration resolved by Django for the container.

    Everything the container needs without database access: the author's
    rules inline (the SHACL ``shapes_text`` pattern — a ``.sch`` is a text
    document, typically tens to hundreds of KB) and the D8 resource limits
    (already clamped Django-side; re-clamped in the container).
    """

    schematron_text: str = Field(
        description=(
            "The Schematron source (.sch) to compile and run, resolved from "
            "the step's Ruleset by Django. The container compiles it with "
            "the SchXslt2 transpiler baked into the image."
        ),
    )
    schematron_sha256: str = Field(
        default="",
        description=(
            "sha256 of schematron_text, computed by Django at dispatch — "
            "the provenance identity of the rules this run executed."
        ),
    )

    # ── D8 resource limits (clamped Django-side; re-clamped in container) ──
    max_input_bytes: int = Field(default=10_000_000, gt=0)
    max_input_depth: int = Field(default=200, gt=0)
    xslt_timeout_seconds: int = Field(default=60, gt=0)
    max_memory_mb: int = Field(default=512, gt=0)
    max_findings: int = Field(default=500, gt=0)

    model_config = {"extra": "forbid"}


class SchematronFinding(BaseModel):
    """One active SVRL finding with the detail Django needs for D10.

    Both ``svrl:failed-assert`` and ``svrl:successful-report`` entries are
    active findings (a ``<report>`` can carry a publisher-authored error).
    ``rule_id`` is the rule's native identifier (``BR-CO-15``,
    ``PEPPOL-EN16931-R010``) and becomes ``ValidationFinding.code`` in
    Django; ``location_xpath`` preserves the SVRL ``@location`` so the
    finding can point at the offending element. ``flag``/``role`` carry the
    raw SVRL attributes for provenance (severity was resolved from them via
    the @flag → @role → fail-closed-ERROR chain, D3).
    """

    rule_id: str = Field(default="", description="Native rule id (@id).")
    message: str = Field(description="Human-readable finding text.")
    severity: str = Field(description="ERROR | WARNING | INFO (resolved).")
    location_xpath: str = Field(
        default="",
        description="SVRL @location XPath into the submitted document.",
    )
    flag: str = Field(default="", description="Raw SVRL @flag attribute.")
    role: str = Field(default="", description="Raw SVRL @role attribute.")

    model_config = {"extra": "forbid"}


class SchematronOutputs(BaseModel):
    """Schematron results: engine status, SVRL summary, and provenance.

    The output-value fields (``passed`` … ``engine``) mirror the catalog entries in
    the Django Schematron ``ValidatorConfig`` — Django's
    ``extract_output_values`` pulls exactly those keys for CEL assertion
    evaluation.

    D9 contract: when ``engine_status != "ok"`` the run never evaluated the
    rules — ``passed`` is ``None`` (*unknown*, not failed), the counts are
    meaningless, and ``finding_rule_ids_by_severity``/``findings`` stay
    empty. Django surfaces one reserved infrastructure finding instead.
    """

    # ── D9 engine status ──
    engine_status: str = Field(
        default=ENGINE_STATUS_OK,
        description="ok | error | timeout — findings only meaningful on ok.",
    )
    engine_message: str = Field(
        default="",
        description="Human-readable engine failure detail (when not ok).",
    )
    engine_error_code: str = Field(
        default="",
        description=(
            "Machine hint for the failure kind (e.g. rules_invalid, "
            "backend_unavailable); maps to Django's reserved codes."
        ),
    )

    # ── o.* output values (must stay aligned with the ValidatorConfig catalog) ──
    passed: bool | None = Field(
        default=None,
        description=(
            "True iff zero ERROR-level findings; None (unknown) when the "
            "engine could not run."
        ),
    )
    error_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    info_count: int = Field(default=0, ge=0)
    # svrl:fired-rule counts rules/contexts EVALUATED, not assertions that
    # fired — never surface this as an "assertion count" (D3 SVRL note).
    fired_rule_count: int = Field(default=0, ge=0)
    finding_rule_ids_by_severity: dict[str, str] = Field(
        default_factory=dict,
        description=(
            'Map of native rule id to resolved severity, e.g. {"BR-CO-15": '
            '"ERROR"}. Key membership + severity gates in CEL (D2).'
        ),
    )

    # ── Findings (volume-capped, never silently — D10) ──
    findings: list[SchematronFinding] = Field(
        default_factory=list,
        description=(
            "Active findings (failed-asserts AND successful-reports), "
            "capped at max_findings ordered ERROR → WARNING → INFO."
        ),
    )
    findings_truncated: bool = Field(
        default=False,
        description="True when the findings list was capped.",
    )
    findings_suppressed_count: int = Field(
        default=0,
        ge=0,
        description="How many findings the cap suppressed (counts stay full).",
    )

    # ── Provenance of the executed rules + engine (D5) ──
    schematron_sha256: str = Field(
        default="",
        description="sha256 of the Schematron source that was executed.",
    )
    query_binding: str = Field(
        default="",
        description=(
            "Query binding detected from the .sch root (xslt1/xslt2/…), "
            "echoed for provenance."
        ),
    )
    engine: str = Field(
        default="",
        description="Engine name + version that ran, e.g. 'SaxonC-HE 12.9'.",
    )

    execution_seconds: float = Field(default=0.0, ge=0)

    model_config = {"extra": "forbid"}


class SchematronInputEnvelope(ValidationInputEnvelope):
    """Input envelope for Schematron validator containers."""

    inputs: SchematronInputs


class SchematronOutputEnvelope(ValidationOutputEnvelope):
    """Output envelope from Schematron validator containers.

    ``outputs`` can be ``None`` for runtime-failure cases where the backend
    crashed before producing even an engine-status summary.
    """

    outputs: SchematronOutputs | None = None


def build_schematron_input_envelope(
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
    inputs: SchematronInputs,
    callback_url: str,
    execution_bundle_uri: str,
    execution_attempt_id: str,
    step_run_id: str,
    expected_output_uri: str,
    callback_id: str | None = None,
    callback_nonce: str | None = None,
    callback_nonce_commitment: str | None = None,
    skip_callback: bool = False,
) -> SchematronInputEnvelope:
    """Build a ``SchematronInputEnvelope`` from Django validation data.

    Args:
        run_id: ValidationRun ID.
        validator: Validator-like object (id/validation_type/version attrs).
        org_id / org_name: Organization identity.
        workflow_id / step_id / step_name: Workflow context.
        submission_uri: Storage URI for the XML submission (gs:// or file://).
        submission_size_bytes: Expected exact submission size and byte ceiling.
        submission_sha256: Expected SHA-256 of the XML submission.
        submission_storage_version: Immutable provider version for the object.
        inputs: Fully-resolved ``SchematronInputs`` (inline rules + limits).
        callback_url: URL the container POSTs to on completion.
        execution_bundle_uri: Base URI for this run's bundle.
        callback_id: Idempotency key echoed back in the callback.
        callback_nonce: Per-attempt secret returned in the callback payload.
        callback_nonce_commitment: Public commitment to ``callback_nonce``.
        skip_callback: True for synchronous (Docker) execution.
    """
    input_files = [
        InputFileItem(
            name="submission.xml",
            mime_type=SupportedMimeType.APPLICATION_XML,
            role="xml-document",
            port_key="xml_document",
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

    return SchematronInputEnvelope(
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
