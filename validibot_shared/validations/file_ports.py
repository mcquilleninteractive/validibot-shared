"""Resolve named file ports from validator input envelopes.

``port_key`` is the stable name from a Validibot validator contract. Older or
third-party envelope producers may omit it and provide only the backend-facing
``role`` or resource ``type``. The helpers in this module implement that
compatibility rule once for every application and container consumer.

Fallback is deliberately allowed only for an item whose ``port_key`` is
absent. If an item carries a different port key, its older role/type label must
not reclassify it. Ambiguous envelopes fail closed instead of depending on list
order.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal, overload

from validibot_shared.validations.envelopes import InputFileItem, ResourceFileItem


class FilePortLookupError(ValueError):
    """Raised when one named envelope port is missing or ambiguous."""


def _select_file_item[FileItemT: (InputFileItem, ResourceFileItem)](
    items: Sequence[FileItemT],
    *,
    port_key: str,
    fallback_name: str | None,
    fallback_label: str,
    fallback_value: Callable[[FileItemT], str | None],
    required: bool,
) -> FileItemT | None:
    """Select at most one item without allowing a conflicting key fallback."""
    matches = [
        item
        for item in items
        if item.port_key == port_key
        or (
            item.port_key is None
            and fallback_name is not None
            and fallback_value(item) == fallback_name
        )
    ]
    if len(matches) > 1:
        msg = f"File port '{port_key}' is ambiguous; found {len(matches)} items."
        raise FilePortLookupError(msg)
    if matches:
        return matches[0]
    if required:
        fallback = (
            f" or legacy {fallback_label} '{fallback_name}'"
            if fallback_name is not None
            else ""
        )
        msg = f"Required file port '{port_key}'{fallback} was not found."
        raise FilePortLookupError(msg)
    return None


@overload
def select_input_file(
    items: Sequence[InputFileItem],
    *,
    port_key: str,
    legacy_role: str | None = None,
    required: Literal[True] = True,
) -> InputFileItem: ...


@overload
def select_input_file(
    items: Sequence[InputFileItem],
    *,
    port_key: str,
    legacy_role: str | None = None,
    required: Literal[False],
) -> InputFileItem | None: ...


def select_input_file(
    items: Sequence[InputFileItem],
    *,
    port_key: str,
    legacy_role: str | None = None,
    required: bool = True,
) -> InputFileItem | None:
    """Return the input item for ``port_key``, with role-only compatibility."""
    return _select_file_item(
        items,
        port_key=port_key,
        fallback_name=legacy_role,
        fallback_label="role",
        fallback_value=lambda item: item.role,
        required=required,
    )


@overload
def select_resource_file(
    items: Sequence[ResourceFileItem],
    *,
    port_key: str,
    legacy_type: str | None = None,
    required: Literal[True] = True,
) -> ResourceFileItem: ...


@overload
def select_resource_file(
    items: Sequence[ResourceFileItem],
    *,
    port_key: str,
    legacy_type: str | None = None,
    required: Literal[False],
) -> ResourceFileItem | None: ...


def select_resource_file(
    items: Sequence[ResourceFileItem],
    *,
    port_key: str,
    legacy_type: str | None = None,
    required: bool = True,
) -> ResourceFileItem | None:
    """Return the resource for ``port_key``, with type-only compatibility."""
    return _select_file_item(
        items,
        port_key=port_key,
        fallback_name=legacy_type,
        fallback_label="type",
        fallback_value=lambda item: item.type,
        required=required,
    )


__all__ = [
    "FilePortLookupError",
    "select_input_file",
    "select_resource_file",
]
