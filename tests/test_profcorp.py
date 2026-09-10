from pipeline.models import InternedRecord
from pipeline.transform.profcorp import match_owner, parse_profcorp_owners


def test_parse_initial_and_last():
    owners = parse_profcorp_owners("A. Ahmed Professional Corporation")
    assert [(o.last_name, o.first_initial) for o in owners] == [("Ahmed", "A")]


def test_parse_two_people():
    owners = parse_profcorp_owners("A. Neufeld & R. Daloise Professional Corporation")
    assert [(o.last_name, o.first_initial) for o in owners] == [
        ("Neufeld", "A"),
        ("Daloise", "R"),
    ]


def test_parse_shared_last_name():
    owners = parse_profcorp_owners("A & R Ali Professional Corporation")
    assert [(o.last_name, o.first_initial) for o in owners] == [
        ("Ali", "A"),
        ("Ali", "R"),
    ]


def test_parse_strips_medical_suffix():
    owners = parse_profcorp_owners("A Balogun Medical Professional Corporation")
    assert [(o.last_name, o.first_initial) for o in owners] == [("Balogun", "A")]


def test_clinic_style_name_is_not_a_person():
    assert parse_profcorp_owners("Riverbend Family Clinic Professional Corporation") == []


def _rec(**kwargs) -> InternedRecord:
    values = dict(
        source_system="cpsa",
        license_college="CPSA",
        license_number=None,
        full_name="Mooney, Jen",
        first_name="Jen",
        last_name="Mooney",
        credentials="MD",
        specialty="Adolescent Medicine",
        title=None,
        license_status="active",
        practice_name="",
        source_org_id=None,
        address_line1="28 Oki Drive Northwest",
        city="Calgary",
        province="AB",
        postal_code="T3B 6A8",
        country="CA",
        practice_type_hint="clinic",
    )
    values.update(kwargs)
    return InternedRecord(**values)


def test_match_owner_requires_unique_last_and_initial():
    hint = parse_profcorp_owners("J. Mooney Professional Corporation")[0]
    assert match_owner(hint, [_rec()]).full_name == "Mooney, Jen"
    two = [_rec(), _rec(full_name="Mooney, Jack", first_name="Jack")]
    assert match_owner(hint, two) is None


def test_match_owner_skips_retired():
    hint = parse_profcorp_owners("J. Mooney Professional Corporation")[0]
    assert match_owner(hint, [_rec(license_status="retired")]) is None
