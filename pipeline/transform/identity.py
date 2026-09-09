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
        normalize_text(address_line),
        normalize_text(city),
        normalize_province(province),
        normalize_postal(postal_code),
    ]
    return "org:" + "|".join(parts)


def contact_key(
    *,
    college: str | None,
    license_number: str | None,
    full_name: str | None,
    org_key: str,
) -> str:
    if college and license_number and license_number.strip():
        return f"lic:{normalize_text(college)}|{normalize_text(license_number)}"
    return f"name:{normalize_text(full_name)}|{normalize_text(college)}|{org_key}"
