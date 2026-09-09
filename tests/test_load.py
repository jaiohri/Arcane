from pipeline.config import load_segment
from pipeline.enrichment.stub import enrich_contact
from pipeline.extract.runner import LegalGateError, run_extract, write_fixture_extract
from pipeline.paths import SCHEMA_PATH
from pipeline.transform import run_transform
import pytest


def test_schema_defines_v1_tables():
    sql = SCHEMA_PATH.read_text()
    for table in (
        "organizations",
        "contacts",
        "segments",
        "segment_members",
        "etl_runs",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "email text" in sql
    assert "enrichment_status" in sql


def test_legal_gate_blocks_network_extract(tmp_path):
    config = load_segment("alberta-medical-benefits")
    assert config.extract_allowed() is False
    with pytest.raises(LegalGateError, match="Extract skipped"):
        run_extract(config, tmp_path / "run", allow_fixtures=False)


def test_fixture_transform_medical(tmp_path):
    config = load_segment("alberta-medical-benefits")
    run_dir = tmp_path / "run"
    write_fixture_extract(config, run_dir)
    batch = run_transform(run_dir, config)

    names = sorted(org.name for org in batch.organizations)
    assert names == [
        "Lee Wong Medicine",
        "Riverbend Family Clinic",
        "University of Alberta Hospital",
    ]

    riverbend = next(org for org in batch.organizations if org.name.startswith("Riverbend"))
    assert riverbend.licensee_count == 4
    assert riverbend.practice_type == "group"

    hospital = next(org for org in batch.organizations if "Hospital" in org.name)
    assert hospital.practice_type == "hospital"
    assert hospital.industry == "Hospital and Health Care"

    primaries = [member for member in batch.members if member.is_primary_contact]
    assert len(primaries) == 3
    riverbend_primary = next(
        member for member in batch.members if member.org_key == riverbend.org_key and member.is_primary_contact
    )
    jane = next(contact for contact in batch.contacts if contact.full_name == "Jane Doe")
    assert riverbend_primary.contact_key == jane.contact_key
    assert jane.title == "Owner"


def test_enrichment_stub_is_blocked():
    result = enrich_contact("any")
    assert result["status"] == "blocked"
