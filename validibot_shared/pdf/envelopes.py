"""Strict PDF package input, inventory, and output contracts.

The PDF backend inventories standardized package mechanisms and may emit a few
fixed singleton payloads for later workflow steps. It never renders the PDF or
interprets an extracted XML/JSON/STEP payload as domain-conformant.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from validibot_shared.validations.envelopes import (
    ValidationInputEnvelope,
    ValidationOutputEnvelope,
)

PDF_INVENTORY_SCHEMA_VERSION = "validibot.pdf_inventory.v1"


class PdfPayloadSelector(BaseModel):
    """Exact, deterministic selector for one optional typed output."""

    required: bool = False
    discovery_kinds: list[str] = Field(default_factory=list, max_length=16)
    original_filename: str = Field(default="", max_length=512)
    declared_media_type: str = Field(default="", max_length=255)
    detected_media_type: str = Field(default="", max_length=255)
    af_relationship: str = Field(default="", max_length=128)
    rich_media_asset_name: str = Field(default="", max_length=512)
    xml_root_qname: str = Field(default="", max_length=1024)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def require_one_match_key(self) -> PdfPayloadSelector:
        """Reject selectors that would mean an unsafe implicit first match."""
        if not any(
            (
                self.discovery_kinds,
                self.original_filename,
                self.declared_media_type,
                self.detected_media_type,
                self.af_relationship,
                self.rich_media_asset_name,
                self.xml_root_qname,
            )
        ):
            msg = "A PDF payload selector must define at least one exact match key."
            raise ValueError(msg)
        return self


class PdfProcessingLimits(BaseModel):
    """Backend-enforced limits, already clamped by the application."""

    max_input_bytes: int = Field(default=100_000_000, gt=0, le=250_000_000)
    max_pages: int = Field(default=2_000, gt=0, le=10_000)
    max_objects: int = Field(default=250_000, gt=0, le=1_000_000)
    max_object_depth: int = Field(default=128, gt=0, le=256)
    max_member_references: int = Field(default=100, gt=0, le=1_000)
    max_member_bytes: int = Field(default=50_000_000, gt=0, le=250_000_000)
    max_total_member_bytes: int = Field(
        default=250_000_000,
        gt=0,
        le=1_000_000_000,
    )
    max_xmp_bytes: int = Field(default=5_000_000, gt=0, le=20_000_000)
    max_findings: int = Field(default=1_000, gt=0, le=10_000)
    max_inventory_bytes: int = Field(
        default=25_000_000,
        ge=10_000,
        le=100_000_000,
    )

    model_config = {"extra": "forbid"}


class PdfInputs(BaseModel):
    """Industry-neutral PDF inventory and typed-extraction configuration."""

    profile: Literal["inventory_v1", "safe_static_package_v1"] = "inventory_v1"
    emit_extracted_files_bundle: bool = False
    selected_xml: PdfPayloadSelector | None = None
    selected_json: PdfPayloadSelector | None = None
    selected_step_p21: PdfPayloadSelector | None = None
    limits: PdfProcessingLimits = Field(default_factory=PdfProcessingLimits)

    model_config = {"extra": "forbid"}


class PdfInventorySource(BaseModel):
    """Identity of the immutable source PDF."""

    name: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = {"extra": "forbid"}


class PdfParserInfo(BaseModel):
    """Parser identity and warning evidence."""

    engine: str
    versions: dict[str, str] = Field(default_factory=dict)
    recovery_attempted: bool = False
    warnings: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class PdfDocumentFacts(BaseModel):
    """Bounded structural facts about the PDF wrapper."""

    header_version: str = ""
    catalog_version: str | None = None
    page_count: int = Field(default=0, ge=0)
    object_count: int = Field(default=0, ge=0)
    encrypted: bool = False
    opened_with_empty_password: bool = False
    encryption_revision: int | None = Field(default=None, ge=0)
    encryption_bits: int | None = Field(default=None, ge=0)
    encryption_methods: dict[str, str] = Field(default_factory=dict)
    permissions: dict[str, bool] = Field(default_factory=dict)
    linearized: bool = False

    model_config = {"extra": "forbid"}


class PdfMember(BaseModel):
    """One deduplicated package-member byte sequence and its references."""

    member_id: str
    discovery_kinds: list[str] = Field(default_factory=list)
    discovery_locations: list[str] = Field(default_factory=list)
    object_references: list[str] = Field(default_factory=list)
    original_names: list[str] = Field(default_factory=list)
    description: str = ""
    declared_media_type: str = ""
    detected_media_type: str = ""
    af_relationships: list[str] = Field(default_factory=list)
    rich_media_asset_names: list[str] = Field(default_factory=list)
    xml_root_qname: str = ""
    encoded_size_bytes: int | None = Field(default=None, ge=0)
    decoded_size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_eligible: bool = True
    refusal_reason: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    selected_output_key: str = ""

    model_config = {"extra": "forbid"}


class PdfInventory(BaseModel):
    """Canonical public inventory for one inspected PDF package."""

    schema_version: Literal["validibot.pdf_inventory.v1"] = PDF_INVENTORY_SCHEMA_VERSION
    source: PdfInventorySource
    parser: PdfParserInfo
    pdf: PdfDocumentFacts
    extensions: list[dict[str, Any]] = Field(default_factory=list)
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    declarations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    interactive_features: dict[str, Any] = Field(default_factory=dict)
    signatures: list[dict[str, Any]] = Field(default_factory=list)
    members: list[PdfMember] = Field(default_factory=list)
    profile_results: list[dict[str, Any]] = Field(default_factory=list)
    limits: dict[str, int] = Field(default_factory=dict)
    finding_summary: dict[str, int] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class PdfOutputs(BaseModel):
    """Typed summary and canonical inventory returned by the backend."""

    passed: bool
    member_count: int = Field(ge=0)
    selected_output_keys: list[str] = Field(default_factory=list)
    finding_summary: dict[str, int] = Field(default_factory=dict)
    inventory: PdfInventory
    engine: str
    execution_seconds: float = Field(default=0.0, ge=0)

    model_config = {"extra": "forbid"}


class PdfInputEnvelope(ValidationInputEnvelope):
    """Input envelope for the isolated PDF package backend."""

    inputs: PdfInputs


class PdfOutputEnvelope(ValidationOutputEnvelope):
    """Output envelope for the isolated PDF package backend."""

    outputs: PdfOutputs | None = None
