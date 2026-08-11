"""Bounded properties for the shared validator trust-boundary contract.

This suite treats a generated rejection as normal when the public contract
documents it: Pydantic ``ValidationError`` for malformed envelopes and file
items, ``FilePortLookupError`` for missing or ambiguous singleton ports, and
``SvrlParseError`` for empty, malformed, or dangerous XML. A property failure
therefore means an unexpected exception or a broken invariant, not merely that
untrusted input was refused.

The properties deliberately use small structures: recursive JSON is limited to
24 leaves, SVRL has at most 12 findings, and raw parser probes have at most
2 KiB. These are test budgets chosen to keep pull requests fast. Production
byte, execution-time, and memory ceilings remain the responsibility of the
runtime boundary.

Protected invariants:

* canonical JSON is deterministic and preserves JSON-compatible values;
* callback secrets canonicalize only through their public commitments;
* valid envelopes round-trip while one-field corruption fails closed;
* logical file names cannot become paths and singleton ports never depend on
  list order; and
* SVRL severity, totals, caps, and defensive XML rejection remain consistent.
"""

from __future__ import annotations

import json
import string
from typing import Any
from xml.sax.saxutils import quoteattr

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from validibot_shared.canonicalization import (
    canonicalize_dict,
    compute_callback_nonce_commitment,
)
from validibot_shared.schematron.svrl import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SvrlParseError,
    parse_svrl,
)
from validibot_shared.validations.envelopes import (
    ATTEMPT_CONTRACT_VERSION,
    ExecutionContext,
    InputFileItem,
    SupportedMimeType,
    ValidationInputEnvelope,
    ValidatorType,
)
from validibot_shared.validations.file_ports import (
    FilePortLookupError,
    select_input_file,
)

CALLBACK_ALPHABET = string.ascii_letters + string.digits + "_-"
VALID_CALLBACK_NONCES = st.text(
    alphabet=CALLBACK_ALPHABET,
    min_size=43,
    max_size=96,
)
INVALID_CALLBACK_NONCES = st.one_of(
    st.text(alphabet=CALLBACK_ALPHABET, max_size=42),
    st.text(alphabet=CALLBACK_ALPHABET, min_size=43, max_size=96).map(
        lambda nonce: nonce + "!",
    ),
    st.just("A" * 513),
)

JSON_KEYS = st.text(
    alphabet=st.characters(exclude_categories=("Cs",)),
    min_size=1,
    max_size=16,
).filter(lambda key: key != "callback_nonce")
JSON_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**53) + 1, max_value=(2**53) - 1),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
    st.text(
        alphabet=st.characters(exclude_categories=("Cs",)),
        max_size=32,
    ),
)
JSON_VALUES = st.recursive(
    JSON_SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=6),
        st.dictionaries(JSON_KEYS, children, max_size=6),
    ),
    max_leaves=24,
)
JSON_OBJECTS = JSON_VALUES.map(lambda value: {"payload": value})

SAFE_NAME_CHARACTERS = st.characters(
    exclude_characters="/\\\x00",
    exclude_categories=("Cs",),
)
SAFE_LEAF_NAMES = st.text(
    alphabet=SAFE_NAME_CHARACTERS,
    min_size=1,
    max_size=24,
).filter(lambda name: name not in {".", ".."})
UNSAFE_LEAF_NAMES = st.one_of(
    st.sampled_from(["", ".", ".."]),
    st.tuples(
        st.text(alphabet=SAFE_NAME_CHARACTERS, max_size=8),
        st.sampled_from(["/", "\\", "\x00"]),
        st.text(alphabet=SAFE_NAME_CHARACTERS, max_size=8),
    ).map(lambda parts: "".join(parts)),
)

SEVERITY_CASES = st.sampled_from(
    [
        (SEVERITY_ERROR, "flag", "fatal"),
        (SEVERITY_ERROR, "flag", " ErRoR "),
        (SEVERITY_ERROR, "role", "FATAL"),
        (SEVERITY_WARNING, "flag", "warning"),
        (SEVERITY_WARNING, "role", " WaRn "),
        (SEVERITY_INFO, "flag", "INFO"),
        (SEVERITY_INFO, "role", " information "),
    ],
)
SVRL_FINDINGS = st.lists(
    st.tuples(
        SEVERITY_CASES,
        st.sampled_from(["failed-assert", "successful-report"]),
    ),
    max_size=12,
)


def _reverse_object_order(value: Any) -> Any:
    """Return an equivalent JSON value with every object inserted in reverse."""
    if isinstance(value, dict):
        return {
            key: _reverse_object_order(value[key]) for key in reversed(tuple(value))
        }
    if isinstance(value, list):
        return [_reverse_object_order(item) for item in value]
    return value


def _sync_context() -> ExecutionContext:
    """Build the strict no-callback context used by generated envelopes."""
    values: dict[str, Any] = {
        "execution_attempt_id": "attempt-property",
        "step_run_id": "step-run-property",
        "attempt_contract_version": ATTEMPT_CONTRACT_VERSION,
        "expected_output_uri": "file:///output/output.json",
        "execution_bundle_uri": "file:///attempt/",
        "skip_callback": True,
    }
    return ExecutionContext(**values)


def _envelope_payload(inputs: dict[str, Any]) -> dict[str, Any]:
    """Return one minimally complete base-envelope dictionary."""
    return {
        "schema_version": "validibot.input.v1",
        "run_id": "run-property",
        "validator": {
            "id": "validator-property",
            "type": ValidatorType.CUSTOM_VALIDATOR,
            "version": "1",
        },
        "org": {"id": "org-property", "name": "Property Org"},
        "workflow": {
            "id": "workflow-property",
            "step_id": "step-property",
            "step_name": "Property step",
        },
        "inputs": inputs,
        "context": _sync_context().model_dump(mode="json"),
    }


def _input_file(
    *,
    name: str,
    port_key: str,
    role: str | None,
) -> InputFileItem:
    """Build one integrity-complete input item for selection properties."""
    return InputFileItem(
        name=name,
        mime_type=SupportedMimeType.APPLICATION_XML,
        port_key=port_key,
        role=role,
        uri=f"gs://property-tests/{name}",
        size_bytes=1,
        sha256="a" * 64,
        storage_version="1",
    )


def _svrl_xml(
    findings: list[tuple[tuple[str, str, str], str]],
) -> str:
    """Render bounded generated findings into well-formed SVRL."""
    elements: list[str] = []
    for index, (severity_case, element_name) in enumerate(findings):
        _severity, attribute_name, attribute_value = severity_case
        elements.append(
            f"<svrl:{element_name} id={quoteattr(f'VB-{index}')} "
            f'{attribute_name}={quoteattr(attribute_value)} location="/root">'
            f"<svrl:text>Finding {index}</svrl:text>"
            f"</svrl:{element_name}>"
        )
    return (
        '<svrl:schematron-output xmlns:svrl="http://purl.oclc.org/dsdl/svrl">'
        + "".join(elements)
        + "</svrl:schematron-output>"
    )


# Canonicalization properties protect evidence and signature identity.


@given(JSON_OBJECTS)
def test_canonical_json_is_independent_of_mapping_insertion_order(
    payload: dict[str, Any],
) -> None:
    """Equivalent objects must never acquire different evidence identities."""
    assert canonicalize_dict(payload) == canonicalize_dict(
        _reverse_object_order(payload),
    )


@given(JSON_OBJECTS)
def test_canonical_json_is_idempotent_after_json_round_trip(
    payload: dict[str, Any],
) -> None:
    """A verifier decoding hostile Unicode or numbers must reproduce the bytes."""
    canonical = canonicalize_dict(payload)

    assert canonicalize_dict(json.loads(canonical)) == canonical


@given(VALID_CALLBACK_NONCES)
def test_nonce_secret_and_commitment_forms_have_one_identity(nonce: str) -> None:
    """Evidence binds every valid secret without serializing the secret itself."""
    commitment = compute_callback_nonce_commitment(nonce)
    secret_form = {
        "context": {
            "callback_nonce": nonce,
            "callback_nonce_commitment": commitment,
        },
    }
    public_form = {"context": {"callback_nonce_commitment": commitment}}

    canonical = canonicalize_dict(secret_form)

    assert canonical == canonicalize_dict(public_form)
    assert nonce.encode("utf-8") not in canonical
    assert len(commitment) == 64
    assert set(commitment) <= set("0123456789abcdef")


@given(INVALID_CALLBACK_NONCES)
def test_malformed_callback_nonces_are_cleanly_rejected(nonce: str) -> None:
    """Weak or non-wire-safe callback secrets must fail at envelope parsing."""
    values = _sync_context().model_dump(mode="python")
    values["callback_nonce"] = nonce
    values["callback_nonce_commitment"] = (
        compute_callback_nonce_commitment(nonce) if nonce else "0" * 64
    )
    with pytest.raises(ValidationError):
        ExecutionContext(**values)


# Envelope and file properties protect the cross-process input boundary.


@given(JSON_OBJECTS)
def test_input_envelope_json_round_trip_preserves_contract(
    inputs: dict[str, Any],
) -> None:
    """A valid producer payload must survive the exact JSON consumer boundary."""
    envelope = ValidationInputEnvelope.model_validate(_envelope_payload(inputs))

    restored = ValidationInputEnvelope.model_validate_json(envelope.model_dump_json())

    assert restored == envelope


@given(
    JSON_OBJECTS,
    st.sampled_from(
        [
            "remove_run_id",
            "remove_validator",
            "remove_org",
            "remove_workflow",
            "remove_context",
            "wrong_schema_version",
            "extra_top_level_field",
        ],
    ),
)
def test_one_field_envelope_corruption_fails_closed(
    inputs: dict[str, Any],
    mutation: str,
) -> None:
    """One damaged boundary field must not be ignored or defaulted into validity."""
    payload = _envelope_payload(inputs)
    if mutation.startswith("remove_"):
        payload.pop(mutation.removeprefix("remove_"))
    elif mutation == "wrong_schema_version":
        payload["schema_version"] = "validibot.input.future"
    else:
        payload["unexpected"] = True

    with pytest.raises(ValidationError):
        ValidationInputEnvelope.model_validate(payload)


@given(UNSAFE_LEAF_NAMES)
def test_generated_path_like_file_names_are_rejected(name: str) -> None:
    """A logical name must never redirect materialization outside its workspace."""
    with pytest.raises(ValidationError):
        _input_file(name=name, port_key="xml_document", role="xml-document")


@given(st.lists(SAFE_LEAF_NAMES, max_size=6, unique=True))
def test_singleton_file_selection_is_independent_of_list_order(
    unrelated_names: list[str],
) -> None:
    """Prepending, appending, or reversing side files must not change selection."""
    document = _input_file(
        name="document.xml",
        port_key="xml_document",
        role="xml-document",
    )
    unrelated = [
        _input_file(name=name, port_key=f"side_{index}", role="side")
        for index, name in enumerate(unrelated_names)
    ]

    orderings = [
        [document, *unrelated],
        [*unrelated, document],
        list(reversed([document, *unrelated])),
    ]
    for items in orderings:
        assert (
            select_input_file(
                items,
                port_key="xml_document",
            )
            is document
        )


@given(st.integers(min_value=2, max_value=6))
def test_every_duplicate_singleton_claim_is_rejected(claim_count: int) -> None:
    """Any cardinality above one must fail instead of becoming first-item-wins."""
    claims = [
        _input_file(
            name=f"claim-{index}.xml",
            port_key="xml_document",
            role="xml-document",
        )
        for index in range(claim_count)
    ]

    with pytest.raises(FilePortLookupError, match=rf"found {claim_count} items"):
        select_input_file(
            claims,
            port_key="xml_document",
        )


# SVRL properties protect defensive XML parsing and bounded signal output.


@given(SVRL_FINDINGS, st.integers(min_value=1, max_value=8))
def test_svrl_caps_findings_without_losing_totals_or_severity(
    findings: list[tuple[tuple[str, str, str], str]],
    cap: int,
) -> None:
    """Truncation must retain the strongest findings and truthful full totals."""
    summary = parse_svrl(_svrl_xml(findings), max_findings=cap)
    expected_severities = [case[0][0] for case in findings]
    severity_rank = {
        SEVERITY_ERROR: 0,
        SEVERITY_WARNING: 1,
        SEVERITY_INFO: 2,
    }
    kept = sorted(expected_severities, key=severity_rank.__getitem__)[:cap]

    assert summary.error_count == expected_severities.count(SEVERITY_ERROR)
    assert summary.warning_count == expected_severities.count(SEVERITY_WARNING)
    assert summary.info_count == expected_severities.count(SEVERITY_INFO)
    assert [finding.severity for finding in summary.findings] == (
        kept if len(findings) > cap else expected_severities
    )
    assert summary.findings_truncated is (len(findings) > cap)
    assert summary.findings_suppressed_count == max(0, len(findings) - cap)


@given(st.binary(max_size=2_048))
def test_bounded_raw_svrl_bytes_have_only_documented_outcomes(payload: bytes) -> None:
    """Arbitrary bytes may parse or reject, but must not escape as another error."""
    try:
        parse_svrl(payload, max_findings=16)
    except SvrlParseError:
        pass


@given(st.text(alphabet=string.ascii_letters + string.digits, max_size=32))
def test_svrl_external_entities_are_always_rejected(system_suffix: str) -> None:
    """Generated entity targets must never turn SVRL parsing into file access."""
    payload = (
        "<!DOCTYPE svrl:schematron-output ["
        f'<!ENTITY xxe SYSTEM "file:///tmp/{system_suffix}">'
        "]>"
        '<svrl:schematron-output xmlns:svrl="http://purl.oclc.org/dsdl/svrl">'
        '<svrl:failed-assert id="VB-XXE" flag="fatal">'
        "<svrl:text>&xxe;</svrl:text>"
        "</svrl:failed-assert>"
        "</svrl:schematron-output>"
    )

    with pytest.raises(SvrlParseError, match="forbidden constructs"):
        parse_svrl(payload)
