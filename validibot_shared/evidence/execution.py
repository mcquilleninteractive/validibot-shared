"""URI-free execution-envelope projections stored with execution attempts.

These models describe the runtime boundary used by validator launchers. They
are not part of the permanent ``EvidenceManifest`` receipt.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ManifestExecutionInput(BaseModel):
    """URI-free identity of one file committed to an execution envelope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Literal["input_files", "resource_files"]
    name: str
    role: str = ""
    resource_type: str = ""
    port_key: str = ""
    resource_id: str = ""
    media_type: str = ""
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    storage_version: str = Field(min_length=1, max_length=512)


class ManifestInputRelationship(BaseModel):
    """Relationship between source bytes and an execution-envelope file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: str
    source_id: str = ""
    source_name: str = ""
    source_size_bytes: int | None = Field(default=None, ge=0)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_channel: Literal["input_files", "resource_files"]
    target_name: str
    target_port_key: str = ""
    target_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship: str
    transformation: str = ""


__all__ = ["ManifestExecutionInput", "ManifestInputRelationship"]
