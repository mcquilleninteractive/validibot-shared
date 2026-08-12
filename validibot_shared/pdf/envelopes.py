"""Strict static-text PDF package input, inventory, and output contracts.

The PDF backend has one fixed policy. It may inspect document XMP and package
members carried as XML, JSON, or STEP Part 21 through a deliberately small set
of standard attachment routes. It never renders the PDF, executes active
content, or interprets an extracted carrier as domain-conformant.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from validibot_shared.validations.envelopes import (
    ValidationInputEnvelope,
    ValidationOutputEnvelope,
)

PDF_INVENTORY_SCHEMA_VERSION = "validibot.pdf_inventory.v2"
PDF_STATIC_TEXT_POLICY = "static_text_package_v1"

PdfDiscoveryKind = Literal[
    "embedded_files_name_tree",
    "associated_file",
    "file_attachment_annotation",
]


class PdfExtension(BaseModel):
    """One declared PDF extension dictionary, including unknown developers."""

    developer: str = Field(max_length=255)
    object_reference: str = Field(default="", max_length=64)
    base_version: str = Field(default="", max_length=64)
    extension_level: int | None = Field(default=None, ge=0)
    extension_revision: int | None = Field(default=None, ge=0)
    url: str = Field(default="", max_length=2048)

    model_config = {"extra": "forbid"}


class PdfRequirement(BaseModel):
    """One catalog requirement dictionary without interpreting its domain."""

    position: int = Field(ge=0)
    object_reference: str = Field(default="", max_length=64)
    type: str = Field(default="", max_length=255)
    subtype: str = Field(default="", max_length=255)
    keys: list[str] = Field(default_factory=list, max_length=128)

    model_config = {"extra": "forbid"}


class PdfDeclaration(BaseModel):
    """One identifier asserted through the PDF Declarations XMP convention."""

    identifier: str = Field(max_length=2048)
    source_qname: str = Field(default="", max_length=1024)

    model_config = {"extra": "forbid"}


class PdfCollection(BaseModel):
    """Minimal Collection facts retained only to explain policy rejection."""

    object_reference: str = Field(default="", max_length=64)
    view: str = Field(default="", max_length=64)

    model_config = {"extra": "forbid"}


class PdfRichMediaAnnotation(BaseModel):
    """Minimal RichMedia facts retained only to explain policy rejection."""

    object_reference: str = Field(default="", max_length=64)
    locations: list[str] = Field(default_factory=list, max_length=1_000)

    model_config = {"extra": "forbid"}


class PdfThreeDAnnotation(BaseModel):
    """Minimal 3D facts retained only to explain policy rejection."""

    object_reference: str = Field(default="", max_length=64)
    locations: list[str] = Field(default_factory=list, max_length=1_000)
    stream_object_reference: str = Field(default="", max_length=64)
    stream_subtype: str = Field(default="", max_length=64)

    model_config = {"extra": "forbid"}


class PdfLogicalStructureFacts(BaseModel):
    """Counts of publisher-supplied logical and optional-content structures."""

    tagged: bool = False
    structure_element_count: int = Field(default=0, ge=0)
    marked_content_reference_count: int = Field(default=0, ge=0)
    marked_content_id_count: int = Field(default=0, ge=0)
    object_reference_count: int = Field(default=0, ge=0)
    optional_content_group_count: int = Field(default=0, ge=0)
    associated_file_link_count: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class PdfPayloadSelector(BaseModel):
    """Exact, deterministic selector for one optional typed output."""

    required: bool = False
    discovery_kinds: list[PdfDiscoveryKind] = Field(default_factory=list, max_length=3)
    original_filename: str = Field(default="", max_length=512)
    declared_media_type: str = Field(default="", max_length=255)
    detected_media_type: str = Field(default="", max_length=255)
    af_relationship: str = Field(default="", max_length=128)
    xml_root_qname: str = Field(default="", max_length=1024)
    step_file_schema: list[str] = Field(default_factory=list, max_length=128)

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
                self.xml_root_qname,
                self.step_file_schema,
            )
        ):
            msg = "A PDF payload selector must define at least one exact match key."
            raise ValueError(msg)
        return self


class PdfProcessingLimits(BaseModel):
    """Backend-enforced limits, already clamped by the application."""

    max_input_bytes: int = Field(default=104_857_600, gt=0, le=262_144_000)
    max_pages: int = Field(default=2_000, gt=0, le=10_000)
    max_objects: int = Field(default=250_000, gt=0, le=1_000_000)
    max_object_depth: int = Field(default=128, gt=0, le=256)
    max_member_references: int = Field(default=100, gt=0, le=1_000)
    max_member_bytes: int = Field(default=52_428_800, gt=0, le=262_144_000)
    max_total_member_bytes: int = Field(
        default=262_144_000,
        gt=0,
        le=1_073_741_824,
    )
    max_decode_ratio: int = Field(default=200, gt=0, le=1_000)
    max_xmp_bytes: int = Field(default=5_242_880, gt=0, le=20_971_520)
    max_action_entries: int = Field(default=10_000, gt=0, le=100_000)
    max_findings: int = Field(default=1_000, gt=0, le=10_000)
    max_inventory_bytes: int = Field(
        default=26_214_400,
        ge=10_000,
        le=104_857_600,
    )
    max_output_bundle_bytes: int = Field(
        default=314_572_800,
        gt=0,
        le=1_073_741_824,
    )
    max_execution_seconds: int = Field(default=60, gt=0, le=300)

    model_config = {"extra": "forbid"}


class PdfInputs(BaseModel):
    """Fixed static-text PDF inspection and typed-extraction configuration."""

    policy: Literal["static_text_package_v1"] = PDF_STATIC_TEXT_POLICY
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
    discovery_kinds: list[PdfDiscoveryKind] = Field(default_factory=list)
    discovery_locations: list[str] = Field(default_factory=list)
    object_references: list[str] = Field(default_factory=list)
    original_names: list[str] = Field(default_factory=list)
    description: str = ""
    declared_media_type: str = ""
    detected_media_type: str = ""
    af_relationships: list[str] = Field(default_factory=list)
    xml_root_qname: str = ""
    step_file_schema: list[str] = Field(default_factory=list, max_length=128)
    encoded_size_bytes: int | None = Field(default=None, ge=0)
    decoded_size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extraction_eligible: bool = True
    refusal_reason: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    selected_output_key: str = ""

    model_config = {"extra": "forbid"}


class PdfPolicyResult(BaseModel):
    """Result of the sole fixed PDF security policy."""

    policy: Literal["static_text_package_v1"] = PDF_STATIC_TEXT_POLICY
    passed: bool

    model_config = {"extra": "forbid"}


class PdfInventory(BaseModel):
    """Canonical public inventory for one inspected PDF package."""

    schema_version: Literal["validibot.pdf_inventory.v2"] = PDF_INVENTORY_SCHEMA_VERSION
    source: PdfInventorySource
    parser: PdfParserInfo
    pdf: PdfDocumentFacts
    extensions: list[PdfExtension] = Field(default_factory=list)
    requirements: list[PdfRequirement] = Field(default_factory=list)
    declarations: list[PdfDeclaration] = Field(default_factory=list)
    collections: list[PdfCollection] = Field(default_factory=list)
    rich_media: list[PdfRichMediaAnnotation] = Field(default_factory=list)
    three_d: list[PdfThreeDAnnotation] = Field(default_factory=list)
    logical_structure: PdfLogicalStructureFacts = Field(
        default_factory=PdfLogicalStructureFacts,
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    interactive_features: dict[str, Any] = Field(default_factory=dict)
    members: list[PdfMember] = Field(default_factory=list)
    policy_results: list[PdfPolicyResult] = Field(default_factory=list, max_length=1)
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
