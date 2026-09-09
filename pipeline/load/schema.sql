CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS organizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_key text NOT NULL UNIQUE,
    name text NOT NULL,
    industry text,
    sector text,
    address_line1 text,
    city text,
    province text,
    postal_code text,
    country text,
    employee_count_estimate integer,
    licensee_count integer,
    practice_type text,
    founded_year integer,
    source_system text NOT NULL,
    source_org_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_key text NOT NULL UNIQUE,
    organization_id uuid REFERENCES organizations (id),
    first_name text,
    last_name text,
    full_name text NOT NULL,
    title text,
    credentials text,
    specialty text,
    license_number text,
    license_college text NOT NULL,
    email text,
    phone text,
    enriched_at timestamptz,
    enrichment_status text NOT NULL DEFAULT 'blocked',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS segments (
    id text PRIMARY KEY,
    display_name text NOT NULL,
    province text NOT NULL,
    profession text NOT NULL,
    config_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etl_runs (
    id uuid PRIMARY KEY,
    segment_id text NOT NULL,
    phase text NOT NULL,
    status text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    row_counts jsonb,
    git_sha text,
    error text
);

CREATE TABLE IF NOT EXISTS segment_members (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    segment_id text NOT NULL REFERENCES segments (id),
    organization_id uuid NOT NULL REFERENCES organizations (id),
    contact_id uuid NOT NULL REFERENCES contacts (id),
    is_primary_contact boolean NOT NULL DEFAULT false,
    fit_score numeric NOT NULL,
    score_version integer NOT NULL,
    score_breakdown jsonb,
    run_id uuid NOT NULL REFERENCES etl_runs (id),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (segment_id, organization_id, contact_id)
);

CREATE INDEX IF NOT EXISTS organizations_city_idx ON organizations (city);
CREATE INDEX IF NOT EXISTS organizations_sector_idx ON organizations (sector);
CREATE INDEX IF NOT EXISTS segment_members_score_idx ON segment_members (segment_id, fit_score DESC);
CREATE INDEX IF NOT EXISTS segment_members_primary_idx ON segment_members (segment_id, is_primary_contact);
