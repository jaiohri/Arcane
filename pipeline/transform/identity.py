from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _SPACE.sub(" ", value.strip().lower())


def normalize_province(value: str | None) -> str:
    return normalize_text(value).upper()


def normalize_postal(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


_STREET_ABBREV = (
    (re.compile(r"\bnorthwest\b"), "nw"),
    (re.compile(r"\bnortheast\b"), "ne"),
    (re.compile(r"\bsouthwest\b"), "sw"),
    (re.compile(r"\bsoutheast\b"), "se"),
    (re.compile(r"\bstreet\b"), "st"),
    (re.compile(r"\bavenue\b"), "ave"),
    (re.compile(r"\bdrive\b"), "dr"),
    (re.compile(r"\broad\b"), "rd"),
    (re.compile(r"\bboulevard\b"), "blvd"),
)


def normalize_address(value: str | None) -> str:
    text = normalize_text(value)
    for pattern, repl in _STREET_ABBREV:
        text = pattern.sub(repl, text)
    return text


def organization_key(
    *,
    source_org_id: str | None,
    practice_name: str | None,
    address_line: str | None,
    city: str | None,
    province: str | None,
    postal_code: str | None,
) -> str:
    if source_org_id and source_org_id.strip():
        return f"src:{source_org_id.strip()}"
    parts = [
        normalize_text(practice_name),
        normalize_address(address_line),
        normalize_text(city),
        normalize_province(province),
        normalize_postal(postal_code),
    ]
    return "org:" + "|".join(parts)


def practitioner_key(
    *,
    listing_type: str,
    license_number: str | None,
    full_name: str | None,
    city: str | None,
) -> str:
    if license_number and license_number.strip():
        return f"lic:{normalize_text(license_number)}"
    return (
        f"name:{normalize_text(listing_type)}|{normalize_text(full_name)}|"
        f"{normalize_text(city)}"
    )


def contact_key(
    *,
    college: str | None,
    license_number: str | None,
    full_name: str | None,
    org_key: str | None = None,
    city: str | None = None,
) -> str:
    if college and license_number and license_number.strip():
        return f"lic:{normalize_text(college)}|{normalize_text(license_number)}"
    if org_key:
        return f"name:{normalize_text(full_name)}|{normalize_text(college)}|{org_key}"
    return f"name:{normalize_text(full_name)}|{normalize_text(college)}|{normalize_text(city)}"
