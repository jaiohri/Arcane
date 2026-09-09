from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from pipeline.config import SegmentConfig
from pipeline.models import Contact, Organization, SegmentMember, TransformBatch
from pipeline.transform.identity import contact_key, organization_key
from pipeline.transform.normalize import (
    detect_practice_type,
    display_title,
    industry_for,
    sector_for,
    status_sort_rank,
    title_sort_rank,
)
from pipeline.transform.parse import parse_run
from pipeline.transform.score import score_membership


def run_transform(run_dir: Path, config: SegmentConfig) -> TransformBatch:
    records = parse_run(run_dir, config)
    if not records:
        raise FileNotFoundError(f"No JSON payloads in {run_dir}/responses or {run_dir}/pages")

    keyed: list[tuple[str, str, object]] = []
    org_records: dict[str, list] = defaultdict(list)

    for record in records:
        org_key = organization_key(
            source_org_id=record.source_org_id,
            practice_name=record.practice_name,
            address_line=record.address_line1,
            city=record.city,
            province=record.province,
            postal_code=record.postal_code,
        )
        person_key = contact_key(
            college=record.license_college,
            license_number=record.license_number,
            full_name=record.full_name,
            org_key=org_key,
        )
        keyed.append((org_key, person_key, record))
        org_records[org_key].append((person_key, record))

    licensee_counts = {
        org_key: len({person_key for person_key, _ in people})
        for org_key, people in org_records.items()
    }

    organizations: dict[str, Organization] = {}
    contacts: dict[str, Contact] = {}
    members: list[SegmentMember] = []
    members_by_org: dict[str, list[tuple[SegmentMember, object]]] = defaultdict(list)

    for org_key, person_key, record in keyed:
        licensee_count = licensee_counts[org_key]
        practice_type = detect_practice_type(record, licensee_count)
        if org_key not in organizations:
            organizations[org_key] = Organization(
                org_key=org_key,
                name=record.practice_name,
                industry=industry_for(config.profession, practice_type, config),
                sector=sector_for(config.profession),
                address_line1=record.address_line1,
                city=record.city,
                province=record.province,
                postal_code=record.postal_code,
                country=record.country,
                licensee_count=licensee_count,
                practice_type=practice_type,
                source_system=record.source_system,
                source_org_id=record.source_org_id,
            )
        breakdown = score_membership(
            record,
            config=config,
            practice_type=practice_type,
            licensee_count=licensee_count,
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
        title = display_title(record)
        if person_key not in contacts:
            contacts[person_key] = Contact(
                contact_key=person_key,
                first_name=record.first_name,
                last_name=record.last_name,
                full_name=record.full_name,
                title=title,
                credentials=record.credentials,
                specialty=record.specialty,
                license_number=record.license_number,
                license_college=record.license_college,
                license_status=record.license_status,
                display_org_key=org_key,
            )

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

    return TransformBatch(
        organizations=list(organizations.values()),
        contacts=list(contacts.values()),
        members=members,
    )
