"""Tests for deterministic named-file selection from shared envelopes.

The file lists cross a process boundary and must therefore be treated as
untrusted. These tests protect the stable ``port_key`` lookup, compatibility
with envelopes that genuinely predate it, and fail-closed cardinality rules.
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
    port_key: str | None,
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
    port_key: str | None,
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
        legacy_role="xml-document",
    )

    assert selected is document


def test_keyless_input_can_use_its_legacy_role() -> None:
    """A schema-valid older envelope remains usable when its key is absent."""
    document = _input_file(
        name="document.xml",
        port_key=None,
        role="xml-document",
    )

    selected = select_input_file(
        [document],
        port_key="xml_document",
        legacy_role="xml-document",
    )

    assert selected is document


def test_conflicting_port_key_cannot_be_overridden_by_legacy_role() -> None:
    """An explicit different key wins over a misleading older role label."""
    conflicting = _input_file(
        name="wrong.xml",
        port_key="different_port",
        role="xml-document",
    )

    with pytest.raises(FilePortLookupError, match="was not found"):
        select_input_file(
            [conflicting],
            port_key="xml_document",
            legacy_role="xml-document",
        )


def test_duplicate_canonical_and_keyless_legacy_claims_are_ambiguous() -> None:
    """Two files claiming one singleton port must fail rather than pick one."""
    canonical = _input_file(
        name="canonical.xml",
        port_key="xml_document",
        role=None,
    )
    legacy = _input_file(
        name="legacy.xml",
        port_key=None,
        role="xml-document",
    )

    with pytest.raises(FilePortLookupError, match="ambiguous; found 2"):
        select_input_file(
            [canonical, legacy],
            port_key="xml_document",
            legacy_role="xml-document",
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
        legacy_type="portfolio_manager_ebl_v1",
        required=False,
    )

    assert selected is None


def test_keyless_resource_can_use_its_legacy_type() -> None:
    """Resource envelopes without a key retain their documented fallback."""
    expected_buildings = _resource_file(
        name="expected.json",
        port_key=None,
        resource_type="portfolio_manager_ebl_v1",
    )

    selected = select_resource_file(
        [expected_buildings],
        port_key="expected_buildings_list",
        legacy_type="portfolio_manager_ebl_v1",
    )

    assert selected is expected_buildings
