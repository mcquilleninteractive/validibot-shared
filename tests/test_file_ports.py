"""Tests for deterministic named-file selection from shared envelopes.

The file lists cross a process boundary and must therefore be treated as
untrusted. These tests protect the sole stable ``port_key`` lookup and its
fail-closed cardinality rules.
"""

import pytest

from validibot_shared.validations.envelopes import (
    InputFileItem,
    ResourceFileItem,
    SupportedMimeType,
)
from validibot_shared.validations.file_ports import (
    FilePortLookupError,
    select_input_file,
    select_resource_file,
)


def _input_file(
    *,
    name: str,
    port_key: str,
    role: str | None,
) -> InputFileItem:
    """Build one integrity-complete input item for matcher tests."""
    return InputFileItem(
        name=name,
        mime_type=SupportedMimeType.APPLICATION_XML,
        role=role,
        port_key=port_key,
        uri=f"gs://test/{name}",
        size_bytes=1,
        sha256="a" * 64,
        storage_version="1",
    )


def _resource_file(
    *,
    name: str,
    port_key: str,
    resource_type: str,
) -> ResourceFileItem:
    """Build one integrity-complete resource item for matcher tests."""
    return ResourceFileItem(
        id=name,
        name=name,
        type=resource_type,
        port_key=port_key,
        uri=f"gs://test/{name}",
        size_bytes=1,
        sha256="b" * 64,
        storage_version="1",
    )


def test_input_port_key_selects_the_named_item_independent_of_order() -> None:
    """A side file before the declared input must never become the input."""
    side_file = _input_file(name="side.xml", port_key="side_file", role="side")
    document = _input_file(
        name="document.xml",
        port_key="xml_document",
        role=None,
    )

    selected = select_input_file(
        [side_file, document],
        port_key="xml_document",
    )

    assert selected is document


def test_role_cannot_override_a_different_port_key() -> None:
    """A misleading descriptive role cannot reclassify a named file port."""
    conflicting = _input_file(
        name="wrong.xml",
        port_key="different_port",
        role="xml-document",
    )

    with pytest.raises(FilePortLookupError, match="was not found"):
        select_input_file(
            [conflicting],
            port_key="xml_document",
        )


def test_duplicate_port_keys_are_ambiguous() -> None:
    """Two files claiming one singleton port must fail rather than pick one."""
    first = _input_file(name="first.xml", port_key="xml_document", role=None)
    second = _input_file(name="second.xml", port_key="xml_document", role=None)

    with pytest.raises(FilePortLookupError, match="ambiguous; found 2"):
        select_input_file(
            [first, second],
            port_key="xml_document",
        )


def test_optional_resource_returns_none_when_no_item_claims_the_port() -> None:
    """Optional resource ports may be absent without weakening ambiguity checks."""
    unrelated = _resource_file(
        name="other.json",
        port_key="other_resource",
        resource_type="other",
    )

    selected = select_resource_file(
        [unrelated],
        port_key="expected_buildings_list",
        required=False,
    )

    assert selected is None


def test_resource_type_cannot_replace_the_declared_port_key() -> None:
    """A matching domain type is not accepted when the resource port differs."""
    expected_buildings = _resource_file(
        name="expected.json",
        port_key="other_resource",
        resource_type="portfolio_manager_ebl_v1",
    )

    with pytest.raises(FilePortLookupError, match="was not found"):
        select_resource_file(
            [expected_buildings],
            port_key="expected_buildings_list",
        )
