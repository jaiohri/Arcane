from pipeline.config import load_segment
from pipeline.models import InternedRecord
from pipeline.transform.score import score_membership, size_proxy_points


def _record(**overrides) -> InternedRecord:
    values = dict(
        source_system="cpsa",
        license_college="CPSA",
        license_number="1",
        full_name="Jane Doe",
        first_name="Jane",
        last_name="Doe",
        credentials="MD",
        specialty="Family Medicine",
        title=None,
        license_status="active",
        practice_name="Riverbend Family Clinic",
        source_org_id=None,
        address_line1="100 Example Street",
        city="Edmonton",
        province="AB",
        postal_code="T5J 0A1",
        country="CA",
        practice_type_hint="clinic",
    )
    values.update(overrides)
    return InternedRecord(**values)


def test_size_bands():
    assert size_proxy_points(1) == 12
    assert size_proxy_points(3) == 22
    assert size_proxy_points(5) == 30
    assert size_proxy_points(12) == 22
    assert size_proxy_points(20) == 8


def test_registry_only_example_score():
    config = load_segment("alberta-medical-benefits")
    breakdown = score_membership(
        _record(title=None),
        config=config,
        practice_type="group",
        licensee_count=5,
    )
    assert breakdown["total"] == 88
    assert breakdown["signals"] == {
        "market": 15,
        "practice_type": 25,
        "size_proxy": 30,
        "title": 8,
        "credential": 10,
    }
    assert breakdown["inputs"]["title_rank"] == "credential_only"


def test_hospital_penalty_ignores_size_band():
    config = load_segment("alberta-medical-benefits")
    breakdown = score_membership(
        _record(practice_name="University of Alberta Hospital", title=None),
        config=config,
        practice_type="hospital",
        licensee_count=5,
    )
    assert breakdown["signals"]["practice_type"] == 0
    assert breakdown["signals"]["size_proxy"] == 0
    assert breakdown["total"] == 33


def test_owner_title_gets_full_points():
    config = load_segment("alberta-medical-benefits")
    breakdown = score_membership(
        _record(title="Owner"),
        config=config,
        practice_type="group",
        licensee_count=5,
    )
    assert breakdown["signals"]["title"] == 20
    assert breakdown["total"] == 100


def test_associate_title_scores_zero():
    config = load_segment("alberta-medical-benefits")
    breakdown = score_membership(
        _record(title="Associate"),
        config=config,
        practice_type="group",
        licensee_count=5,
    )
    assert breakdown["signals"]["title"] == 0
