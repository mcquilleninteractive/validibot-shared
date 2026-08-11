"""Resolve named file ports from validator input envelopes.

``port_key`` is the sole file-selection identity in the current envelope
contract. Ambiguous or missing singleton ports fail closed instead of falling
back to list order or validator-specific labels.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, overload

from validibot_shared.validations.envelopes import InputFileItem, ResourceFileItem


class FilePortLookupError(ValueError):
    """Raised when one named envelope port is missing or ambiguous."""


def _select_file_item[FileItemT: (InputFileItem, ResourceFileItem)](
    items: Sequence[FileItemT],
    *,
    port_key: str,
    required: bool,
) -> FileItemT | None:
    """Select at most one item by its declared contract key."""
    matches = [item for item in items if item.port_key == port_key]
    if len(matches) > 1:
        msg = f"File port '{port_key}' is ambiguous; found {len(matches)} items."
        raise FilePortLookupError(msg)
    if matches:
        return matches[0]
    if required:
        msg = f"Required file port '{port_key}' was not found."
        raise FilePortLookupError(msg)
    return None


@overload
def select_input_file(
    items: Sequence[InputFileItem],
    *,
    port_key: str,
    required: Literal[True] = True,
) -> InputFileItem: ...


@overload
def select_input_file(
    items: Sequence[InputFileItem],
    *,
    port_key: str,
    required: Literal[False],
) -> InputFileItem | None: ...


def select_input_file(
    items: Sequence[InputFileItem],
    *,
    port_key: str,
    required: bool = True,
) -> InputFileItem | None:
    """Return the input item carrying exactly ``port_key``."""
    return _select_file_item(
        items,
        port_key=port_key,
        required=required,
    )


@overload
def select_resource_file(
    items: Sequence[ResourceFileItem],
    *,
    port_key: str,
    required: Literal[True] = True,
) -> ResourceFileItem: ...


@overload
def select_resource_file(
    items: Sequence[ResourceFileItem],
    *,
    port_key: str,
    required: Literal[False],
) -> ResourceFileItem | None: ...


def select_resource_file(
    items: Sequence[ResourceFileItem],
    *,
    port_key: str,
    required: bool = True,
) -> ResourceFileItem | None:
    """Return the resource item carrying exactly ``port_key``."""
    return _select_file_item(
        items,
        port_key=port_key,
        required=required,
    )


__all__ = [
    "FilePortLookupError",
    "select_input_file",
    "select_resource_file",
]
