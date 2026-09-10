from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.types.json import Jsonb

from pipeline.config import SegmentConfig
from pipeline.models import Contact, Organization, Practitioner, SegmentMember, TransformBatch
from pipeline.paths import SCHEMA_PATH


def connect(database_url: str) -> Connection:
    return psycopg.connect(database_url)


def apply_schema(conn: Connection) -> None:
    conn.execute(SCHEMA_PATH.read_text())
    conn.commit()


def record_run_start(
    conn: Connection,
    *,
    run_id: UUID,
    segment_id: str,
    phase: str,
    git_sha: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO etl_runs (id, segment_id, phase, status, git_sha)
        VALUES (%s, %s, %s, 'started', %s)
        ON CONFLICT (id) DO UPDATE SET
            phase = EXCLUDED.phase,
            status = 'started',
            error = NULL,
            finished_at = NULL
        """,
        (run_id, segment_id, phase, git_sha),
    )
    conn.commit()


def record_run_finish(
    conn: Connection,
    *,
    run_id: UUID,
    status: str,
    row_counts: dict | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE etl_runs
        SET status = %s,
            finished_at = now(),
            row_counts = %s,
            error = %s
        WHERE id = %s
        """,
        (status, Jsonb(row_counts) if row_counts is not None else None, error, run_id),
    )
    conn.commit()


def upsert_segment(conn: Connection, config: SegmentConfig) -> None:
    conn.execute(
        """
        INSERT INTO segments (id, display_name, province, profession, config_hash)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            province = EXCLUDED.province,
            profession = EXCLUDED.profession,
            config_hash = EXCLUDED.config_hash,
            updated_at = now()
        """,
        (
            config.segment_id,
            config.display_name,
            config.province,
            config.profession,
            config.config_hash,
        ),
    )


def upsert_organization(conn: Connection, org: Organization) -> UUID:
    row = conn.execute(
        """
        INSERT INTO organizations (
            org_key, name, industry, sector, address_line1, city, province,
            postal_code, country, licensee_count, practice_type, source_system,
            source_org_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (org_key) DO UPDATE SET
            name = EXCLUDED.name,
            industry = EXCLUDED.industry,
            sector = EXCLUDED.sector,
            address_line1 = EXCLUDED.address_line1,
            city = EXCLUDED.city,
            province = EXCLUDED.province,
            postal_code = EXCLUDED.postal_code,
            country = EXCLUDED.country,
            licensee_count = EXCLUDED.licensee_count,
            practice_type = EXCLUDED.practice_type,
            source_system = EXCLUDED.source_system,
            source_org_id = EXCLUDED.source_org_id,
            updated_at = now()
        RETURNING id
        """,
        (
            org.org_key,
            org.name,
            org.industry,
            org.sector,
            org.address_line1,
            org.city,
            org.province,
            org.postal_code,
            org.country,
            org.licensee_count,
            org.practice_type,
            org.source_system,
            org.source_org_id,
        ),
    ).fetchone()
    return row[0]


def upsert_contact(conn: Connection, contact: Contact, organization_id: UUID | None) -> UUID:
    row = conn.execute(
        """
        INSERT INTO contacts (
            contact_key, organization_id, first_name, last_name, full_name, title,
            credentials, specialty, license_number, license_college, enrichment_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'blocked')
        ON CONFLICT (contact_key) DO UPDATE SET
            organization_id = EXCLUDED.organization_id,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            full_name = EXCLUDED.full_name,
            title = EXCLUDED.title,
            credentials = EXCLUDED.credentials,
            specialty = EXCLUDED.specialty,
            license_number = EXCLUDED.license_number,
            license_college = EXCLUDED.license_college,
            updated_at = now()
        RETURNING id
        """,
        (
            contact.contact_key,
            organization_id,
            contact.first_name,
            contact.last_name,
            contact.full_name,
            contact.title,
            contact.credentials,
            contact.specialty,
            contact.license_number,
            contact.license_college,
        ),
    ).fetchone()
    return row[0]


def upsert_practitioner(conn: Connection, practitioner: Practitioner) -> UUID:
    row = conn.execute(
        """
        INSERT INTO practitioners (
            practitioner_key, source, listing_type, full_name, profession,
            licence_status, specialty, practice_name, practice_address,
            source_reference, collection_method, collected_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now()))
        ON CONFLICT (source, listing_type, practitioner_key) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            profession = EXCLUDED.profession,
            licence_status = EXCLUDED.licence_status,
            specialty = EXCLUDED.specialty,
            practice_name = EXCLUDED.practice_name,
            practice_address = EXCLUDED.practice_address,
            source_reference = EXCLUDED.source_reference,
            collection_method = EXCLUDED.collection_method,
            collected_at = EXCLUDED.collected_at,
            updated_at = now()
        RETURNING id
        """,
        (
            practitioner.practitioner_key,
            practitioner.source,
            practitioner.listing_type,
            practitioner.full_name,
            practitioner.profession,
            practitioner.licence_status,
            practitioner.specialty,
            practitioner.practice_name,
            practitioner.practice_address,
            practitioner.source_reference,
            practitioner.collection_method,
            practitioner.collected_at,
        ),
    ).fetchone()
    return row[0]


def upsert_member(
    conn: Connection,
    member: SegmentMember,
    *,
    segment_id: str,
    organization_id: UUID,
    contact_id: UUID,
    run_id: UUID,
) -> None:
    conn.execute(
        """
        INSERT INTO segment_members (
            segment_id, organization_id, contact_id, is_primary_contact,
            fit_score, score_version, score_breakdown, run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (segment_id, organization_id, contact_id) DO UPDATE SET
            is_primary_contact = EXCLUDED.is_primary_contact,
            fit_score = EXCLUDED.fit_score,
            score_version = EXCLUDED.score_version,
            score_breakdown = EXCLUDED.score_breakdown,
            run_id = EXCLUDED.run_id,
            last_seen_at = now()
        """,
        (
            segment_id,
            organization_id,
            contact_id,
            member.is_primary_contact,
            member.fit_score,
            member.score_version,
            Jsonb(member.score_breakdown),
            run_id,
        ),
    )


def replace_source_rows(conn: Connection, config: SegmentConfig) -> None:
    """Drop prior rows for this source so a parser fix does not leave glued names."""
    source = config.source.adapter
    college = source.upper()
    conn.execute(
        "DELETE FROM segment_members WHERE segment_id = %s",
        (config.segment_id,),
    )
    conn.execute(
        "DELETE FROM contacts WHERE license_college = %s",
        (college,),
    )
    conn.execute(
        "DELETE FROM organizations WHERE source_system = %s",
        (source,),
    )
    conn.execute(
        "DELETE FROM practitioners WHERE source = %s",
        (source,),
    )


def load_batch(
    conn: Connection,
    config: SegmentConfig,
    batch: TransformBatch,
    run_id: UUID,
) -> dict[str, int]:
    apply_schema(conn)
    upsert_segment(conn, config)
    replace_source_rows(conn, config)
    for practitioner in batch.practitioners:
        upsert_practitioner(conn, practitioner)
    org_ids: dict[str, UUID] = {}
    for org in batch.organizations:
        org_ids[org.org_key] = upsert_organization(conn, org)

    contact_ids: dict[str, UUID] = {}
    contacts_by_key = {contact.contact_key: contact for contact in batch.contacts}
    for contact in batch.contacts:
        org_id = org_ids.get(contact.display_org_key) if contact.display_org_key else None
        contact_ids[contact.contact_key] = upsert_contact(conn, contact, org_id)

    for member in batch.members:
        upsert_member(
            conn,
            member,
            segment_id=config.segment_id,
            organization_id=org_ids[member.org_key],
            contact_id=contact_ids[member.contact_key],
            run_id=run_id,
        )

    conn.commit()
    return {
        "practitioners": len(batch.practitioners),
        "orgs": len(batch.organizations),
        "contacts": len(contacts_by_key),
        "members": len(batch.members),
    }
