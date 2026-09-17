from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from dataclasses import replace

from pipeline.config import SegmentConfig
from pipeline.extract.cpsa_listings import PROMOTE_CONTACTS, PROMOTE_ORGS, PROMOTE_PRACTITIONERS
from pipeline.models import Contact, InternedRecord, Organization, Practitioner, SegmentMember, TransformBatch
from pipeline.transform.identity import contact_key, organization_key
from pipeline.transform.normalize import (
    detect_practice_type,
    display_title,
    industry_for,
    sector_for,
    status_sort_rank,
    title_sort_rank,
    usable_practice_address,
)
from pipeline.transform.parse import parse_run
from pipeline.transform.profcorp import match_owner, parse_profcorp_owners
from pipeline.transform.score import score_membership


def run_transform(run_dir: Path, config: SegmentConfig) -> TransformBatch:
    records, listings, errors = parse_run(run_dir, config)
    practitioners: list[Practitioner] = []
    organizations: dict[str, Organization] = {}
    interned_for_members: list = []
    people_records: list[InternedRecord] = []

    for listing in listings:
        if listing.listing_type in PROMOTE_PRACTITIONERS:
            practitioners.extend(listing.practitioners)
            people_records.extend(listing.records)
        for org in listing.organizations:
            organizations[org.org_key] = org
        if listing.listing_type in PROMOTE_ORGS:
            for record in listing.records:
                if not usable_practice_address(record):
                    continue
                org_key = organization_key(
                    source_org_id=record.source_org_id,
                    practice_name=record.practice_name or record.address_line1,
                    address_line=record.address_line1,
                    city=record.city,
                    province=record.province,
                    postal_code=record.postal_code,
                )
                interned_for_members.append((org_key, record))
                if org_key not in organizations:
                    practice_type = detect_practice_type(record, 1)
                    organizations[org_key] = Organization(
                        org_key=org_key,
                        name=record.practice_name or record.address_line1 or record.full_name,
                        industry=industry_for(config.profession, practice_type, config),
                        sector=sector_for(config.profession),
                        address_line1=record.address_line1,
                        city=record.city,
                        province=record.province,
                        postal_code=record.postal_code,
                        country=record.country,
                        licensee_count=1,
                        practice_type=practice_type,
                        source_system=record.source_system,
                        source_org_id=record.source_org_id,
                    )

    licensee_groups: dict[str, set[str]] = defaultdict(set)
    keyed_members: list[tuple[str, str, object]] = []
    for org_key, record in interned_for_members:
        person_key = contact_key(
            college=record.license_college,
            license_number=record.license_number,
            full_name=record.full_name,
            city=record.city,
        )
        licensee_groups[org_key].add(person_key)
        keyed_members.append((org_key, person_key, record))

    _attach_profcorp_owners(
        organizations,
        people_records,
        keyed_members,
        licensee_groups,
    )

    for org_key, org in organizations.items():
        if org_key in licensee_groups:
            org.licensee_count = len(licensee_groups[org_key])
            sample = next(
                (record for key, _, record in keyed_members if key == org_key),
                None,
            )
            if sample is not None:
                org.practice_type = detect_practice_type(sample, org.licensee_count)

    contacts: dict[str, Contact] = {}
    for listing in listings:
        if listing.listing_type not in PROMOTE_CONTACTS:
            continue
        for record in listing.records:
            display_org = None
            if listing.listing_type in PROMOTE_ORGS and usable_practice_address(record):
                display_org = organization_key(
                    source_org_id=record.source_org_id,
                    practice_name=record.practice_name or record.address_line1,
                    address_line=record.address_line1,
                    city=record.city,
                    province=record.province,
                    postal_code=record.postal_code,
                )
            person_key = contact_key(
                college=record.license_college,
                license_number=record.license_number,
                full_name=record.full_name,
                city=record.city,
            )
            if person_key not in contacts:
                contacts[person_key] = Contact(
                    contact_key=person_key,
                    first_name=record.first_name,
                    last_name=record.last_name,
                    full_name=record.full_name,
                    title=display_title(record),
                    credentials=record.credentials,
                    specialty=record.specialty,
                    license_number=record.license_number,
                    license_college=record.license_college,
                    license_status=record.license_status,
                    phone=record.phone,
                    fax=record.fax,
                    display_org_key=display_org,
                )
            else:
                _fill_contact_from_listing(
                    contacts[person_key], record, listing.listing_type
                )

    seen_members: set[tuple[str, str]] = set()
    members: list[SegmentMember] = []
    members_by_org: dict[str, list[tuple[SegmentMember, object]]] = defaultdict(list)
    for org_key, person_key, record in keyed_members:
        pair = (org_key, person_key)
        if pair in seen_members:
            continue
        seen_members.add(pair)
        org = organizations[org_key]
        breakdown = score_membership(
            record,
            config=config,
            practice_type=org.practice_type,
            licensee_count=org.licensee_count,
        )
        member = SegmentMember(
            org_key=org_key,
            contact_key=person_key,
            is_primary_contact=False,
            fit_score=float(breakdown["total"]),
            score_version=int(breakdown["version"]),
            score_breakdown=breakdown,
        )
        members.append(member)
        members_by_org[org_key].append((member, record))

    for org_key, group in members_by_org.items():
        group.sort(
            key=lambda item: (
                -title_sort_rank(item[1].title),
                -status_sort_rank(item[1].license_status),
                item[1].full_name or "",
            )
        )
        group[0][0].is_primary_contact = True
        primary_contact = group[0][0].contact_key
        if primary_contact in contacts:
            contacts[primary_contact].display_org_key = org_key
            if (group[0][1].title or "").strip().lower() == "owner":
                contacts[primary_contact].title = "Owner"

    if not listings and not records and errors:
        pass
    elif not listings and not records:
        raise FileNotFoundError(f"No JSON payloads in {run_dir}/responses or {run_dir}/pages")

    return TransformBatch(
        organizations=list(organizations.values()),
        contacts=list(contacts.values()),
        members=members,
        practitioners=practitioners,
        parse_errors=errors,
    )


def _attach_profcorp_owners(
    organizations: dict[str, Organization],
    people_records: list[InternedRecord],
    keyed_members: list,
    licensee_groups: dict[str, set[str]],
) -> None:
    for org in list(organizations.values()):
        if "professional corporation" not in (org.name or "").lower():
            continue
        hints = parse_profcorp_owners(org.name)
        if not hints:
            continue
        for hint in hints:
            hit = match_owner(hint, people_records)
            if hit is None:
                continue
            owner = replace(hit, title="Owner")
            person_key = contact_key(
                college=owner.license_college,
                license_number=owner.license_number,
                full_name=owner.full_name,
                city=owner.city,
            )
            licensee_groups[org.org_key].add(person_key)
            keyed_members.append((org.org_key, person_key, owner))


def _fill_contact_from_listing(
    contact: Contact, record: InternedRecord, listing_type: str
) -> None:
    """Prefer specialists / non-specialists phone and fax over alphabetical."""
    prefer = listing_type in PROMOTE_ORGS
    if record.phone and (prefer or not contact.phone):
        contact.phone = record.phone
    if record.fax and (prefer or not contact.fax):
        contact.fax = record.fax
