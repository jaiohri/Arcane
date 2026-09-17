from pipeline.transform.identity import contact_key, organization_key, practitioner_key


def test_org_key_uses_source_id_when_present():
    key = organization_key(
        source_org_id="clinic-9",
        practice_name="Westside Family Dental",
        address_line="200 17 Avenue SW",
        city="Calgary",
        province="AB",
        postal_code="T2S 0A1",
    )
    assert key == "src:clinic-9"


def test_org_key_normalizes_address_identity():
    a = organization_key(
        source_org_id=None,
        practice_name="  Westside Family Dental ",
        address_line="200 17 Avenue SW",
        city="Calgary",
        province="ab",
        postal_code="T2S 0A1",
    )
    b = organization_key(
        source_org_id=None,
        practice_name="westside family dental",
        address_line="200  17 Avenue SW",
        city="CALGARY",
        province="AB",
        postal_code="t2s 0a1",
    )
    assert a == b
    assert a.startswith("org:")


def test_contact_key_prefers_college_and_license():
    key = contact_key(
        college="CPSA",
        license_number="CPSA-1001",
        full_name="Jane Doe",
        org_key="org:riverbend",
    )
    assert key == "lic:cpsa|cpsa-1001"


def test_contact_key_falls_back_to_name_and_org():
    key = contact_key(
        college="CPSA",
        license_number=None,
        full_name="Jane Doe",
        org_key="org:riverbend",
    )
    assert key == "name:jane doe|cpsa|org:riverbend"


def test_contact_key_falls_back_to_name_and_city_without_org():
    key = contact_key(
        college="CPSA",
        license_number=None,
        full_name="Aadland, Hilary",
        city="Calgary",
    )
    assert key == "name:aadland, hilary|cpsa|calgary"


def test_practitioner_key_prefers_license_number():
    assert (
        practitioner_key(
            listing_type="alphabetical",
            license_number="12345",
            full_name="Aadland, Hilary",
            city="Calgary",
        )
        == "lic:12345"
    )


def test_practitioner_key_uses_listing_name_and_city():
    a = practitioner_key(
        listing_type="alphabetical",
        license_number=None,
        full_name="Aadland, Hilary",
        city="Calgary",
    )
    b = practitioner_key(
        listing_type="alphabetical",
        license_number=None,
        full_name="Aadland,  Hilary",
        city="calgary",
    )
    assert a == b
    assert a.startswith("name:alphabetical|")
