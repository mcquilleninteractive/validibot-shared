"""Typed contracts for the generic PDF package validator."""

from validibot_shared.pdf.envelopes import (
    PDF_INVENTORY_SCHEMA_VERSION,
    PdfDocumentFacts,
    PdfInputEnvelope,
    PdfInputs,
    PdfInventory,
    PdfInventorySource,
    PdfMember,
    PdfOutputEnvelope,
    PdfOutputs,
    PdfParserInfo,
    PdfPayloadSelector,
    PdfProcessingLimits,
)

__all__ = [
    "PDF_INVENTORY_SCHEMA_VERSION",
    "PdfInputEnvelope",
    "PdfInputs",
    "PdfInventory",
    "PdfInventorySource",
    "PdfMember",
    "PdfDocumentFacts",
    "PdfOutputEnvelope",
    "PdfOutputs",
    "PdfParserInfo",
    "PdfPayloadSelector",
    "PdfProcessingLimits",
]
