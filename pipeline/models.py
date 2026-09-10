from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InternedRecord:
    """Source-native practitioner-at-place row after parse."""

    source_system: str
    license_college: str
    license_number: str | None
    full_name: str
    first_name: str | None
    last_name: str | None
    credentials: str | None
    specialty: str | None
    title: str | None
    license_status: str | None
    practice_name: str
    source_org_id: str | None
    address_line1: str | None
    city: str | None
    province: str | None
    postal_code: str | None
    country: str
    practice_type_hint: str | None
    listing_type: str | None = None
    source_reference: str | None = None
    collection_method: str | None = "bulk_pdf"
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Practitioner:
    practitioner_key: str
    source: str
    listing_type: str
    full_name: str
    profession: str
    licence_status: str | None
    specialty: str | None
    practice_name: str | None
    practice_address: str | None
    source_reference: str | None
    collection_method: str
    collected_at: datetime | None = None


@dataclass
class Organization:
    org_key: str
    name: str
    industry: str
    sector: str
    address_line1: str | None
    city: str | None
    province: str | None
    postal_code: str | None
    country: str
    licensee_count: int
    practice_type: str
    source_system: str
    source_org_id: str | None


@dataclass
class Contact:
    contact_key: str
    first_name: str | None
    last_name: str | None
    full_name: str
    title: str | None
    credentials: str | None
    specialty: str | None
    license_number: str | None
    license_college: str
    license_status: str | None
    display_org_key: str | None = None


@dataclass
class SegmentMember:
    org_key: str
    contact_key: str
    is_primary_contact: bool
    fit_score: float
    score_version: int
    score_breakdown: dict[str, Any]


@dataclass
class TransformBatch:
    organizations: list[Organization]
    contacts: list[Contact]
    members: list[SegmentMember]
    practitioners: list[Practitioner] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
