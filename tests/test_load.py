from pipeline.config import load_segment
from pipeline.enrichment.stub import enrich_contact
from pipeline.extract.cpsa_listings import CPSA_LISTINGS
from pipeline.extract.runner import LegalGateError, run_extract, write_fixture_extract
from pipeline.paths import SCHEMA_PATH
from pipeline.transform import run_transform
import pytest


def test_schema_defines_v1_tables():
    sql = SCHEMA_PATH.read_text()
    for table in (
        "practitioners",
        "organizations",
        "contacts",
        "segments",
        "segment_members",
        "etl_runs",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "UNIQUE (source, listing_type, practitioner_key)" in sql
    assert "email text" in sql
    assert "enrichment_status" in sql


def test_cpsa_live_extract_is_allowed():
    config = load_segment("alberta-medical-benefits")
    assert config.source.tos_status == "allowed"
    assert config.extract.enabled is True
    assert config.extract_allowed() is True


def test_legal_gate_blocks_network_extract(tmp_path):
    config = load_segment("alberta-dental-benefits")
    assert config.extract_allowed() is False
    with pytest.raises(LegalGateError, match="Extract skipped"):
        run_extract(config, tmp_path / "run", allow_fixtures=False)


def test_dental_fixtures_are_absent(tmp_path):
    config = load_segment("alberta-dental-benefits")
    with pytest.raises(FileNotFoundError, match="No fixtures"):
        write_fixture_extract(config, tmp_path / "run")


def test_fixture_transform_medical(tmp_path):
    config = load_segment("alberta-medical-benefits")
    run_dir = tmp_path / "run"
    result = write_fixture_extract(config, run_dir)
    assert any(path.name.endswith(".txt") for path in (run_dir / "pages").iterdir())
    assert result.used_fixtures is True
    batch = run_transform(run_dir, config)

    listing_types = {row.listing_type for row in batch.practitioners}
    assert listing_types == {
        "alphabetical",
        "specialists",
        "non_specialists",
        "retired",
        "obituaries",
    }
    assert len(CPSA_LISTINGS) == 6

    calgary_from_alpha = [
        org
        for org in batch.organizations
        if org.city == "Calgary" and "Aadland" in (org.name or "")
    ]
    assert calgary_from_alpha == []

    oki = [
        org
        for org in batch.organizations
        if org.address_line1 and "Oki" in org.address_line1
    ]
    assert len(oki) == 1
    assert oki[0].city == "Calgary"

    mooney_members = [
        member
        for member in batch.members
        if member.contact_key in {contact.contact_key for contact in batch.contacts if "Mooney" in contact.full_name}
    ]
    assert mooney_members
    assert any(member.fit_score > 0 for member in mooney_members)

    mooney_pc = next(
        org for org in batch.organizations if org.name == "J. Mooney Professional Corporation"
    )
    assert any(member.org_key == mooney_pc.org_key for member in mooney_members)
    mooney_contact = next(contact for contact in batch.contacts if "Mooney" in contact.full_name)
    assert mooney_contact.title == "Owner"

    ahmed_pc = next(
        org for org in batch.organizations if org.name == "A. Ahmed Professional Corporation"
    )
    assert not any(member.org_key == ahmed_pc.org_key for member in batch.members)

    people_names = {contact.full_name for contact in batch.contacts}
    assert "Aadland, Hilary" in people_names
    assert "Abbo Adam Mohamed, Yousra" in people_names
    assert "Rebus, Christopher David" in people_names

    retired = [row for row in batch.practitioners if row.listing_type == "retired"]
    assert {row.licence_status for row in retired} == {"retired"}
    deceased = [row for row in batch.practitioners if row.listing_type == "obituaries"]
    assert {row.licence_status for row in deceased} == {"deceased"}

    corp_names = {org.name for org in batch.organizations if "Professional Corporation" in org.name}
    assert "A. Ahmed Professional Corporation" in corp_names
    assert "A. Neufeld & R. Daloise Professional Corporation" in corp_names
    assert not any("Professional Corporation" in contact.full_name for contact in batch.contacts)

    member_orgs = {member.org_key for member in batch.members}
    non_spec_orgs = [
        org for org in batch.organizations if org.city in {"Athabasca", "Red Deer"}
    ]
    assert len(non_spec_orgs) == 2
    assert {org.org_key for org in non_spec_orgs} <= member_orgs
    assert oki[0].org_key in member_orgs
    assert batch.parse_errors == []

    hilary = next(contact for contact in batch.contacts if contact.full_name == "Aadland, Hilary")
    assert hilary.specialty == "Psychiatry"
    mooney = next(
        row for row in batch.practitioners
        if row.listing_type == "specialists" and "Mooney" in row.full_name
    )
    assert mooney.specialty == "Adolescent Medicine"


def test_enrichment_stub_is_blocked():
    result = enrich_contact("any")
    assert result["status"] == "blocked"
