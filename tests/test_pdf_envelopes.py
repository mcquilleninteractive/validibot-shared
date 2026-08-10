"""Verify the strict, deterministic PDF package wire contract.

These tests protect the selector safety boundary and canonical inventory shape
shared by Django and the isolated parser backend.
"""

import pytest
from pydantic import ValidationError

from validibot_shared.pdf import PdfInputs, PdfInventory, PdfPayloadSelector


def test_selector_requires_an_explicit_exact_match_key() -> None:
    """An empty selector must never degrade into implicit first-member choice."""
    with pytest.raises(ValidationError, match="at least one exact match key"):
        PdfPayloadSelector()


def test_xml_root_qname_is_a_valid_semantic_selector() -> None:
    """Authors may select a known XML vocabulary without trusting filenames."""
    inputs = PdfInputs(
        selected_xml=PdfPayloadSelector(
            xml_root_qname="{urn:example:asset}handover",
        ),
    )

    assert inputs.selected_xml is not None
    assert inputs.selected_xml.xml_root_qname == "{urn:example:asset}handover"


def test_inventory_rejects_unknown_fields() -> None:
    """A backend cannot silently invent fields outside the public V1 schema."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PdfInventory.model_validate(
            {
                "source": {"name": "a.pdf", "size_bytes": 1, "sha256": "a" * 64},
                "parser": {"engine": "qpdf/pikepdf"},
                "pdf": {},
                "surprise": True,
            }
        )
