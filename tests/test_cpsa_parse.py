from pipeline.config import load_segment
from pipeline.extract.cpsa_listings import CPSA_LISTINGS
from pipeline.extract.pdf import pdf_to_text, write_simple_pdf
from pipeline.extract.runner import write_fixture_extract
from pipeline.transform import run_transform
from pipeline.transform.cpsa import PARSERS, parse_listing_text
from pipeline.transform.identity import practitioner_key
from pipeline.paths import FIXTURES_DIR


def test_each_listing_type_is_tagged():
    listings_dir = FIXTURES_DIR / "cpsa" / "listings"
    seen = set()
    for listing in CPSA_LISTINGS:
        text = (listings_dir / f"{listing.listing_type}.txt").read_text()
        parsed = parse_listing_text(listing.listing_type, text)
        seen.add(parsed.listing_type)
        if listing.kind == "people":
            assert parsed.practitioners
            assert {row.listing_type for row in parsed.practitioners} == {listing.listing_type}
        else:
            assert parsed.organizations
            assert parsed.practitioners == []
            assert parsed.records == []
    assert seen == {item.listing_type for item in CPSA_LISTINGS}


def test_practitioner_keys_are_stable_across_parses():
    text = (FIXTURES_DIR / "cpsa" / "listings" / "alphabetical.txt").read_text()
    first = parse_listing_text("alphabetical", text)
    second = parse_listing_text("alphabetical", text)
    keys_a = [row.practitioner_key for row in first.practitioners]
    keys_b = [row.practitioner_key for row in second.practitioners]
    assert keys_a == keys_b
    assert len(keys_a) == len(set(keys_a))
    hilary = next(row for row in first.practitioners if "Aadland" in row.full_name)
    assert hilary.practitioner_key == practitioner_key(
        listing_type="alphabetical",
        license_number=None,
        full_name=hilary.full_name,
        city="Calgary",
    )


def test_listing_parse_error_does_not_block_others(tmp_path, monkeypatch):
    config = load_segment("alberta-medical-benefits")
    run_dir = tmp_path / "run"
    write_fixture_extract(config, run_dir)

    def boom(text, listing):
        raise ValueError("specialists exploded")

    monkeypatch.setitem(PARSERS, "specialists", boom)
    batch = run_transform(run_dir, config)
    assert any("specialists exploded" in error for error in batch.parse_errors)
    types = {row.listing_type for row in batch.practitioners}
    assert "alphabetical" in types
    assert "retired" in types
    assert "obituaries" in types
    assert "specialists" not in types
    assert any("Professional Corporation" in org.name for org in batch.organizations)


def test_profcorp_creates_orgs_not_contacts():
    text = (FIXTURES_DIR / "cpsa" / "listings" / "professional_corporations.txt").read_text()
    parsed = parse_listing_text("professional_corporations", text)
    assert parsed.records == []
    assert parsed.practitioners == []
    names = {org.name for org in parsed.organizations}
    assert "Riverbend Family Clinic Professional Corporation" in names
    assert "A. Neufeld & R. Daloise Professional Corporation" in names
    assert "J. Mooney Professional Corporation" in names


def test_alphabetical_does_not_collapse_city_into_an_org(tmp_path):
    config = load_segment("alberta-medical-benefits")
    run_dir = tmp_path / "run"
    write_fixture_extract(config, run_dir)
    batch = run_transform(run_dir, config)
    calgary_contacts = [contact for contact in batch.contacts if contact.full_name == "Aadland, Hilary"]
    assert calgary_contacts
    assert calgary_contacts[0].display_org_key is None
    assert not any(org.city == "Calgary" and "Aadland" in org.name for org in batch.organizations)


def test_alphabetical_keeps_specialty_codes():
    text = (FIXTURES_DIR / "cpsa" / "listings" / "alphabetical.txt").read_text()
    parsed = parse_listing_text("alphabetical", text)
    hilary = next(row for row in parsed.records if row.full_name.startswith("Aadland"))
    assert hilary.specialty == "Psychiatry"
    wei = next(row for row in parsed.records if "Chen, Wei" == row.full_name)
    assert wei.specialty == "Internal Medicine"


def test_specialists_keep_section_header_as_specialty():
    text = (FIXTURES_DIR / "cpsa" / "listings" / "specialists.txt").read_text()
    parsed = parse_listing_text("specialists", text)
    mooney = next(row for row in parsed.records if "Mooney" in row.full_name)
    adam = next(row for row in parsed.records if "Adam, Benjamin" in row.full_name)
    assert mooney.specialty == "Adolescent Medicine"
    assert adam.specialty == "Anatomical Pathology"
    assert mooney.address_line1 is None or "Adolescent Medicine" not in mooney.address_line1


def test_specialists_keep_every_pdf_column():
    text = (FIXTURES_DIR / "cpsa" / "listings" / "specialists.txt").read_text()
    parsed = parse_listing_text("specialists", text)
    mooney = next(row for row in parsed.practitioners if "Mooney" in row.full_name)
    assert mooney.practice_address == "28 Oki Drive Northwest"
    assert mooney.city == "Calgary"
    assert mooney.postal_code == "T3B 6A8"
    assert mooney.phone == "403-955-2978"
    assert mooney.fax == "403-955-7649"
    adam = next(row for row in parsed.practitioners if "Adam, Benjamin" in row.full_name)
    assert adam.phone == "780-407-8822"
    assert adam.fax is None


def test_alphabetical_keeps_phone():
    text = (FIXTURES_DIR / "cpsa" / "listings" / "alphabetical.txt").read_text()
    parsed = parse_listing_text("alphabetical", text)
    hilary = next(row for row in parsed.practitioners if "Aadland" in row.full_name)
    assert hilary.city == "Calgary"
    assert hilary.phone == "403-956-1156"
    assert hilary.fax is None


def test_two_column_alphabetical_line_splits_into_two_people():
    text = (
        "Aadland, Hilary Calgary 403-956-1156 PSY "
        "Abbotts, Dawn-Ellen Edmonton 780-735-7346 PED\n"
    )
    parsed = parse_listing_text("alphabetical", text)
    names = [row.full_name for row in parsed.practitioners]
    assert names == ["Aadland, Hilary", "Abbotts, Dawn-Ellen"]
    assert not any(any(char.isdigit() for char in name) for name in names)


def test_header_text_is_not_a_person_name():
    text = (
        "Actively Licensed Physicians Resident in Alberta\n"
        "Aadland, Hilary Calgary 403-956-1156 PSY\n"
        "Pattabhi, Rodney Varakumar (Actively Licensed Physicians) Patterson, Jeffery Calgary FM\n"
    )
    parsed = parse_listing_text("alphabetical", text)
    names = [row.full_name for row in parsed.practitioners]
    assert "Aadland, Hilary" in names
    assert all("Actively Licensed" not in name for name in names)


def test_expand_specialty_codes_leaves_section_titles_intact():
    from pipeline.extract.cpsa_symbols import expand_specialty_codes

    assert expand_specialty_codes("PSY") == "Psychiatry"
    assert expand_specialty_codes("IM CARD") == "Internal Medicine; Cardiology"
    assert expand_specialty_codes("Adolescent Medicine") == "Adolescent Medicine"
    assert expand_specialty_codes("Otolaryngology - Head and Neck Surgery") == (
        "Otolaryngology - Head and Neck Surgery"
    )


def test_raw_txt_is_retained_next_to_pdf(tmp_path):
    pdf_path = tmp_path / "alphabetical.pdf"
    write_simple_pdf(pdf_path, "Aadland, Hilary Calgary 403-956-1156 PSY")
    text = pdf_to_text(pdf_path)
    txt_path = tmp_path / "alphabetical.txt"
    txt_path.write_text(text)
    assert txt_path.exists()
    assert "Aadland" in txt_path.read_text()


def test_transform_writes_txt_when_only_pdf_is_landed(tmp_path):
    config = load_segment("alberta-medical-benefits")
    pages = tmp_path / "pages"
    pages.mkdir()
    write_simple_pdf(
        pages / "alphabetical.pdf",
        "Aadland, Hilary Calgary 403-956-1156 PSY",
    )
    batch = run_transform(tmp_path, config)
    assert (pages / "alphabetical.txt").exists()
    assert any(row.listing_type == "alphabetical" for row in batch.practitioners)
