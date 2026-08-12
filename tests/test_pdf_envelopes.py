"""Verify the strict, deterministic PDF package wire contract.

These tests protect the selector safety boundary and canonical inventory shape
shared by Django and the isolated parser backend.
"""

import pytest
from pydantic import ValidationError

from validibot_shared.pdf import (
    PDF_INVENTORY_SCHEMA_VERSION,
    PDF_STATIC_TEXT_PROFILE,
    PdfInputs,
    PdfInventory,
    PdfPayloadSelector,
    PdfProcessingLimits,
)

EXPECTED_BINARY_MIB = 1024 * 1024


def test_selector_requires_an_explicit_exact_match_key() -> None:
    """An empty selector must never degrade into implicit first-member choice."""
    with pytest.raises(ValidationError, match="at least one exact match key"):
        PdfPayloadSelector()


def test_static_text_is_the_only_accepted_pdf_policy() -> None:
    """No caller may downgrade PDF processing to a permissive inventory mode."""
    assert PdfInputs().profile == PDF_STATIC_TEXT_PROFILE

    for legacy_profile in ("inventory_v1", "safe_static_package_v1"):
        with pytest.raises(ValidationError, match="static_text_package_v1"):
            PdfInputs(profile=legacy_profile)


def test_selector_rejects_discovery_routes_outside_the_static_policy() -> None:
    """RichMedia and free-floating file specs cannot become extraction selectors."""
    with pytest.raises(ValidationError, match="Input should be"):
        PdfPayloadSelector(discovery_kinds=["rich_media_asset"])


def test_selector_rejects_removed_rich_media_fields() -> None:
    """The strict contract must not retain a hidden RichMedia extraction path."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PdfPayloadSelector(
            rich_media_asset_name="asset-index",
        )


def test_xml_root_qname_is_a_valid_semantic_selector() -> None:
    """Authors may select a known XML vocabulary without trusting filenames."""
    inputs = PdfInputs(
        selected_xml=PdfPayloadSelector(
            xml_root_qname="{urn:example:asset}handover",
        ),
    )

    assert inputs.selected_xml is not None
    assert inputs.selected_xml.xml_root_qname == "{urn:example:asset}handover"


def test_step_file_schema_is_a_valid_exact_selector() -> None:
    """A STEP member can be selected by its bounded Part 21 header identity."""
    selector = PdfPayloadSelector(
        step_file_schema=["AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF"],
    )

    assert selector.step_file_schema == [
        "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF"
    ]


def test_inventory_rejects_unknown_fields() -> None:
    """A backend cannot silently invent fields outside the public V2 schema."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PdfInventory.model_validate(
            {
                "source": {"name": "a.pdf", "size_bytes": 1, "sha256": "a" * 64},
                "parser": {"engine": "qpdf/pikepdf"},
                "pdf": {},
                "surprise": True,
            }
        )


def test_inventory_v2_keeps_prohibited_mechanisms_as_shallow_typed_evidence() -> None:
    """Rejected Collection, RichMedia, and 3D structures stay shallow and typed."""
    inventory = PdfInventory.model_validate(
        {
            "source": {"name": "a.pdf", "size_bytes": 1, "sha256": "a" * 64},
            "parser": {"engine": "qpdf/pikepdf"},
            "pdf": {},
            "extensions": [{"developer": "ISO_", "extension_revision": 2023}],
            "requirements": [{"position": 0, "subtype": "AP242"}],
            "declarations": [{"identifier": "urn:example:profile:v1"}],
            "collections": [{"view": "D"}],
            "rich_media": [{"locations": ["catalog/Pages/0/Annots/0"]}],
            "three_d": [{"stream_subtype": "PRC"}],
            "logical_structure": {"tagged": True, "structure_element_count": 1},
            "profile_results": [{"profile": "static_text_package_v1", "passed": False}],
        }
    )

    assert inventory.schema_version == PDF_INVENTORY_SCHEMA_VERSION
    assert inventory.extensions[0].extension_revision == 2023
    assert inventory.declarations[0].identifier == "urn:example:profile:v1"
    assert inventory.logical_structure.tagged is True
    assert inventory.profile_results[0].profile == PDF_STATIC_TEXT_PROFILE


def test_inventory_rejects_non_static_profile_results() -> None:
    """A backend output cannot claim evaluation under an unsupported policy."""
    with pytest.raises(ValidationError, match="static_text_package_v1"):
        PdfInventory.model_validate(
            {
                "source": {"name": "a.pdf", "size_bytes": 1, "sha256": "a" * 64},
                "parser": {"engine": "qpdf/pikepdf"},
                "pdf": {},
                "profile_results": [{"profile": "inventory_v1", "passed": True}],
            }
        )


def test_pdf_limits_match_the_documented_binary_budgets() -> None:
    """The wire defaults must express the ADR's MiB values without decimal drift."""
    limits = PdfProcessingLimits()

    assert limits.max_input_bytes == 100 * EXPECTED_BINARY_MIB
    assert limits.max_member_bytes == 50 * EXPECTED_BINARY_MIB
    assert limits.max_total_member_bytes == 250 * EXPECTED_BINARY_MIB
    assert limits.max_output_bundle_bytes == 300 * EXPECTED_BINARY_MIB
    assert limits.max_decode_ratio == 200
    assert limits.max_action_entries == 10_000
    assert limits.max_execution_seconds == 60


@pytest.mark.parametrize(
    ("field", "hard_maximum"),
    [
        ("max_decode_ratio", 1_000),
        ("max_action_entries", 100_000),
        ("max_execution_seconds", 300),
    ],
)
def test_pdf_limit_hard_maxima_are_enforced(field: str, hard_maximum: int) -> None:
    """An envelope cannot ask the backend to exceed an architecture hard ceiling."""
    with pytest.raises(ValidationError):
        PdfProcessingLimits.model_validate({field: hard_maximum + 1})
