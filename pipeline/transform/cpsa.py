from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.extract.cpsa_listings import LISTING_BY_TYPE, CpsaListing
from pipeline.extract.cpsa_pdf import looks_like_section_header
from pipeline.extract.cpsa_symbols import SPECIALTY_ABBREVIATIONS, expand_specialty_codes
from pipeline.models import InternedRecord, Organization, Practitioner
from pipeline.transform.identity import organization_key, practitioner_key

PHONE_RE = re.compile(r"\b\d{3}-\d{3}-\d{4}\b")
POSTAL_RE = re.compile(r"\b[A-CEGHJ-NPR-TVXY]\d[A-Z]\s?\d[A-Z]\d\b", re.I)
# Last, First — used to split two-column leftovers and wrapped rows.
PERSON_COMMA_RE = re.compile(r",\s+[A-Za-z]")
NAME_RE = re.compile(r"^[\^\*\-LH]*\s*([^,]+),\s+(.+)$")
HEADER_RE = re.compile(
    r"^(NAME\b|CITY\b|PHONE\b|SPECIALTY\b|ADDRESS\b|POSTAL\b|FAX\b|"
    r"Alphabetical|Specialists|Non-Specialists|Non Specialists|"
    r'"?Retired"?|Obituaries|Professional Corporation|'
    r"Actively Licensed|Total Number|Page \d+|as of\b|"
    r"This list represents|The College and)",
    re.I,
)
SPECIALTY_TOKEN_RE = re.compile(r"^[A-Z]{2,6}$|^[A-Z]{1,4}&[A-Z]{1,4}$")
PROFCORP_RE = re.compile(r".+?\bProfessional Corporation\b", re.I)

# Used only for the text/fixture fallback. Live PDFs supply city from columns.
CITIES = tuple(
    sorted(
        {
            "Airdrie",
            "Athabasca",
            "Bassano",
            "Calgary",
            "Calmar",
            "Camrose",
            "Canmore",
            "Edmonton",
            "Fort McMurray",
            "Hanna",
            "Lacombe",
            "Lethbridge",
            "Medicine Hat",
            "Morinville",
            "Okotoks",
            "Ponoka",
            "Raymond",
            "Red Deer",
            "Rocky Mountain House",
            "St. Albert",
            "West Vancouver",
            "Surrey",
            "Toronto",
            "Regina",
            "Brampton",
            "Mississauga",
            "Saskatoon",
            "North Vancouver",
        },
        key=len,
        reverse=True,
    )
)


@dataclass
class ListingParse:
    listing_type: str
    practitioners: list[Practitioner]
    records: list[InternedRecord]
    organizations: list[Organization]


def split_name(full: str) -> tuple[str | None, str | None, str]:
    match = NAME_RE.match(full.strip())
    if not match:
        parts = full.strip().split()
        if len(parts) >= 2:
            return parts[-1], " ".join(parts[:-1]), full.strip()
        return None, None, full.strip()
    last_name, rest = match.group(1).strip(), match.group(2).strip()
    return last_name, rest, f"{last_name}, {rest}".strip()


def find_city(text: str) -> str | None:
    lowered = f" {text} "
    for city in CITIES:
        if re.search(rf"\b{re.escape(city)}\b", lowered, re.I):
            return city
    return None


def _skip_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if HEADER_RE.match(stripped):
        return True
    if stripped.lower().startswith("name "):
        return True
    return False


def _is_junk_person_name(name: str) -> bool:
    stripped = name.strip()
    if not stripped or "," not in stripped:
        return True
    if any(char.isdigit() for char in stripped):
        return True
    if HEADER_RE.match(stripped):
        return True
    if "actively licensed" in stripped.lower():
        return True
    if len(stripped) > 90:
        return True
    return False


def _is_specialty_token(token: str) -> bool:
    stripped = token.strip("(),;")
    if not stripped:
        return False
    if stripped.upper() in SPECIALTY_ABBREVIATIONS and stripped.isupper():
        return True
    return bool(SPECIALTY_TOKEN_RE.match(stripped))


def _person(
    *,
    listing: CpsaListing,
    last_name: str | None,
    first_name: str | None,
    full_name: str,
    city: str | None,
    specialty: str | None,
    address: str | None = None,
    postal_code: str | None = None,
    practice_name: str | None = None,
    license_number: str | None = None,
    extra: dict | None = None,
) -> tuple[Practitioner, InternedRecord]:
    display = full_name.strip()
    key = practitioner_key(
        listing_type=listing.listing_type,
        license_number=license_number,
        full_name=display,
        city=city,
    )
    practitioner = Practitioner(
        practitioner_key=key,
        source="cpsa",
        listing_type=listing.listing_type,
        full_name=display,
        profession="physician",
        licence_status=listing.licence_status,
        specialty=specialty,
        practice_name=practice_name,
        practice_address=address,
        source_reference=license_number,
        collection_method="bulk_pdf",
    )
    record = InternedRecord(
        source_system="cpsa",
        license_college="CPSA",
        license_number=license_number,
        full_name=display,
        first_name=first_name,
        last_name=last_name,
        credentials="MD",
        specialty=specialty,
        title=None,
        license_status=listing.licence_status,
        practice_name=practice_name or "",
        source_org_id=None,
        address_line1=address,
        city=city,
        province="AB",
        postal_code=postal_code,
        country="CA",
        practice_type_hint="clinic" if address or practice_name else None,
        listing_type=listing.listing_type,
        source_reference=license_number,
        collection_method="bulk_pdf",
        raw_payload=extra or {},
    )
    return practitioner, record


_ADDRESS_BREAK = frozenset(
    {
        "northwest",
        "northeast",
        "southwest",
        "southeast",
        "street",
        "avenue",
        "drive",
        "road",
        "hospital",
        "nw",
        "ne",
        "sw",
        "se",
        "st",
        "ave",
        "dr",
        "rd",
    }
)
_SINGLE_CITIES = frozenset(city.lower() for city in CITIES if " " not in city)


def _is_name_boundary_token(token: str) -> bool:
    stripped = token.strip("()[]")
    if not stripped:
        return True
    if _is_specialty_token(stripped):
        return True
    if PHONE_RE.search(stripped) or POSTAL_RE.search(stripped):
        return True
    if stripped.lower() in _SINGLE_CITIES or stripped.lower() in _ADDRESS_BREAK:
        return True
    if any(char.isdigit() for char in stripped):
        return True
    return False


def _person_start_indexes(text: str) -> list[int]:
    starts: list[int] = []
    for match in PERSON_COMMA_RE.finditer(text):
        before = text[: match.start()]
        tokens = before.split()
        if not tokens:
            continue
        taken: list[str] = []
        for token in reversed(tokens):
            if taken and _is_name_boundary_token(token):
                break
            taken.insert(0, token)
            if len(taken) >= 4:
                break
        if not taken or _is_name_boundary_token(taken[0]):
            continue
        prefix = " ".join(taken)
        index = before.rfind(prefix)
        if index < 0:
            continue
        if starts and index <= starts[-1]:
            continue
        starts.append(index)
    return starts


def _new_person_starts(line: str) -> list[int]:
    starts = _person_start_indexes(line)
    if starts:
        return starts
    if line.endswith(",") and not looks_like_section_header(line):
        return [0]
    return []


def _people_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            chunks.append(" ".join(pending))
            pending.clear()

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if _skip_line(line):
            continue
        starts = _new_person_starts(line)
        if starts:
            flush()
            if len(starts) == 1:
                pending.append(line)
            else:
                for index, start in enumerate(starts):
                    end = starts[index + 1] if index + 1 < len(starts) else len(line)
                    piece = line[start:end].strip()
                    if piece:
                        chunks.append(piece)
        elif pending:
            pending.append(line)
    flush()
    return chunks


def _parse_name_tail(rest: str) -> tuple[str, str | None, list[str], str | None]:
    """Split 'First Middle City Phone SPEC' into first name, city, phones, specialty."""
    phones = PHONE_RE.findall(rest)
    without_phone = PHONE_RE.sub(" ", rest)
    tokens = [token for token in without_phone.split() if token]
    spec_tokens: list[str] = []
    while tokens and _is_specialty_token(tokens[-1]):
        spec_tokens.insert(0, tokens.pop())
    remainder = " ".join(tokens)
    city = find_city(remainder)
    if city:
        city_match = re.search(rf"\b{re.escape(city)}\b", remainder, re.I)
        first_name = remainder[: city_match.start()].strip() if city_match else remainder
    elif len(tokens) >= 2:
        city = tokens[-1]
        first_name = " ".join(tokens[:-1])
    else:
        first_name = remainder
        city = None
    specialty_raw = " ".join(spec_tokens) or None
    return first_name, city, phones, specialty_raw


def _parse_address_chunk(
    chunk: str,
) -> tuple[str, str | None, str | None, str | None, list[str]]:
    last_name, after, full_name = split_name(chunk)
    after = after or ""
    phones = PHONE_RE.findall(after)
    postal_match = POSTAL_RE.search(after)
    postal = postal_match.group(0).upper() if postal_match else None
    city = find_city(after)
    work = PHONE_RE.sub(" ", after)
    if postal_match:
        work = work[: postal_match.start()] + " " + work[postal_match.end() :]
    if city:
        city_match = re.search(rf"\b{re.escape(city)}\b", work, re.I)
        left = work[: city_match.start()].strip() if city_match else work.strip()
    else:
        left = work.strip()
    digit = re.search(r"\d", left)
    if digit:
        first_name = left[: digit.start()].strip()
        address = left[digit.start() :].strip() or None
    else:
        first_name = left
        address = None
    display = f"{last_name}, {first_name}".strip() if last_name else full_name
    return display, city, address, postal, phones


def parse_alphabetical(text: str, listing: CpsaListing) -> ListingParse:
    practitioners: list[Practitioner] = []
    records: list[InternedRecord] = []
    for chunk in _people_chunks(text):
        last_name, rest, _full = split_name(chunk)
        first_name, city, phones, specialty_raw = _parse_name_tail(rest or "")
        full_name = f"{last_name}, {first_name}".strip() if last_name else chunk
        if _is_junk_person_name(full_name):
            continue
        practitioner, record = _person(
            listing=listing,
            last_name=last_name,
            first_name=first_name or None,
            full_name=full_name,
            city=city,
            specialty=expand_specialty_codes(specialty_raw) or specialty_raw,
            extra={"phones_in_source": phones},
        )
        practitioners.append(practitioner)
        records.append(record)
    return ListingParse(listing.listing_type, practitioners, records, [])


def parse_name_city(text: str, listing: CpsaListing) -> ListingParse:
    practitioners: list[Practitioner] = []
    records: list[InternedRecord] = []
    for chunk in _people_chunks(text):
        last_name, rest, _full = split_name(chunk)
        first_name, city, _phones, _spec = _parse_name_tail(rest or "")
        full_name = f"{last_name}, {first_name}".strip() if last_name else chunk
        if _is_junk_person_name(full_name):
            continue
        practitioner, record = _person(
            listing=listing,
            last_name=last_name,
            first_name=first_name or None,
            full_name=full_name,
            city=city,
            specialty=None,
        )
        practitioners.append(practitioner)
        records.append(record)
    return ListingParse(listing.listing_type, practitioners, records, [])


def parse_address_listing(text: str, listing: CpsaListing) -> ListingParse:
    practitioners: list[Practitioner] = []
    records: list[InternedRecord] = []
    current_specialty: str | None = None
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        chunk = " ".join(pending)
        pending = []
        full_name, city, address, postal, phones = _parse_address_chunk(chunk)
        if _is_junk_person_name(full_name):
            return
        if current_specialty and address and address.endswith(current_specialty):
            address = address[: -len(current_specialty)].strip() or None
        last_name, first_name, _ = split_name(full_name)
        practitioner, record = _person(
            listing=listing,
            last_name=last_name,
            first_name=first_name,
            full_name=full_name,
            city=city,
            specialty=current_specialty,
            address=address,
            postal_code=postal,
            extra={"phones_in_source": phones},
        )
        practitioners.append(practitioner)
        records.append(record)

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if _skip_line(line):
            continue
        if "," not in line and looks_like_section_header(line):
            if pending and pending[-1].endswith(","):
                pending.append(line)
                continue
            flush()
            current_specialty = line
            continue
        starts = _new_person_starts(line)
        if starts:
            flush()
            if len(starts) == 1:
                pending = [line]
            else:
                for index, start in enumerate(starts):
                    end = starts[index + 1] if index + 1 < len(starts) else len(line)
                    piece = line[start:end].strip()
                    if not piece:
                        continue
                    pending = [piece]
                    flush()
        elif pending:
            pending.append(line)
    flush()
    return ListingParse(listing.listing_type, practitioners, records, [])


def parse_profcorp(text: str, listing: CpsaListing) -> ListingParse:
    organizations: list[Organization] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if _skip_line(line):
            continue
        names = [match.group(0).strip() for match in PROFCORP_RE.finditer(line)]
        if not names and "professional corporation" in line.lower():
            names = [line.strip()]
        for name in names:
            org_key = organization_key(
                source_org_id=None,
                practice_name=name,
                address_line=None,
                city=None,
                province="AB",
                postal_code=None,
            )
            if org_key in seen:
                continue
            seen.add(org_key)
            organizations.append(
                Organization(
                    org_key=org_key,
                    name=name,
                    industry="Medical Practices",
                    sector="medical",
                    address_line1=None,
                    city=None,
                    province="AB",
                    postal_code=None,
                    country="CA",
                    licensee_count=0,
                    practice_type="unknown",
                    source_system="cpsa",
                    source_org_id=None,
                )
            )
    return ListingParse(listing.listing_type, [], [], organizations)


def _row_person(
    listing: CpsaListing, row: dict[str, str]
) -> tuple[Practitioner, InternedRecord] | None:
    name = " ".join((row.get("name") or "").split())
    if _is_junk_person_name(name):
        return None
    last_name, first_name, display = split_name(name)
    city = (row.get("city") or "").strip() or None
    address = (row.get("address") or "").strip() or None
    postal = (row.get("postal") or "").strip() or None
    specialty_raw = (row.get("specialty") or "").strip() or None
    phones = PHONE_RE.findall(row.get("phone") or "")
    return _person(
        listing=listing,
        last_name=last_name,
        first_name=first_name,
        full_name=display,
        city=city,
        specialty=expand_specialty_codes(specialty_raw) or specialty_raw,
        address=address,
        postal_code=postal,
        extra={"phones_in_source": phones, "fax": row.get("fax")},
    )


def parse_listing_rows(listing_type: str, rows: list[dict[str, str]]) -> ListingParse:
    listing = LISTING_BY_TYPE[listing_type]
    if listing.kind == "corporations":
        text = "\n".join(row.get("name") or "" for row in rows)
        return parse_profcorp(text, listing)
    practitioners: list[Practitioner] = []
    records: list[InternedRecord] = []
    for row in rows:
        parsed = _row_person(listing, row)
        if parsed is None:
            continue
        practitioner, record = parsed
        practitioners.append(practitioner)
        records.append(record)
    return ListingParse(listing.listing_type, practitioners, records, [])


PARSERS = {
    "alphabetical": parse_alphabetical,
    "specialists": parse_address_listing,
    "non_specialists": parse_address_listing,
    "retired": parse_name_city,
    "obituaries": parse_name_city,
    "professional_corporations": parse_profcorp,
}


def parse_listing_text(listing_type: str, text: str) -> ListingParse:
    listing = LISTING_BY_TYPE[listing_type]
    parser = PARSERS[listing_type]
    return parser(text, listing)
