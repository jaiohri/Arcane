"""Column-aware text extraction for CPSA Medical Directory PDFs.

The listings are landscape pages with two or three people/org columns.
Default pdfplumber extract_text() reads left-to-right across columns, which
glues two physicians onto one line. Field x-ranges come from the printed
headers (NAME / CITY / PHONE, etc.).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

LINE_GAP = 8.0

# Exclusive x1. Words are assigned to the last column whose x0 <= word.x0.
LISTING_LAYOUTS: dict[str, dict[str, Any]] = {
    "alphabetical": {
        "header_y": 115,
        "wrap": "name",
        "columns": (
            {
                "x0": 0,
                "fields": {
                    "name": (0, 140),
                    "city": (140, 230),
                    "phone": (230, 320),
                    "specialty": (320, 400),
                },
            },
            {
                "x0": 400,
                "fields": {
                    "name": (400, 545),
                    "city": (545, 635),
                    "phone": (635, 725),
                    "specialty": (725, 900),
                },
            },
        ),
    },
    "specialists": {
        "header_y": 115,
        "wrap": "address",
        "columns": (
            {
                "x0": 0,
                "fields": {
                    "name": (0, 200),
                    "address": (200, 500),
                    "city": (500, 580),
                    "postal": (580, 655),
                    "phone": (655, 735),
                    "fax": (735, 900),
                },
            },
        ),
    },
    "non_specialists": {
        "header_y": 115,
        "wrap": "address",
        "columns": (
            {
                "x0": 0,
                "fields": {
                    "name": (0, 200),
                    "address": (200, 500),
                    "city": (500, 580),
                    "postal": (580, 655),
                    "phone": (655, 735),
                    "fax": (735, 900),
                },
            },
        ),
    },
    "retired": {
        "header_y": 128,
        "wrap": "name",
        "columns": (
            {"x0": 0, "fields": {"name": (0, 140), "city": (140, 280)}},
            {"x0": 280, "fields": {"name": (280, 410), "city": (410, 560)}},
            {"x0": 560, "fields": {"name": (560, 680), "city": (680, 900)}},
        ),
    },
    "obituaries": {
        "header_y": 128,
        "wrap": "name",
        "columns": (
            {"x0": 0, "fields": {"name": (0, 140), "city": (140, 280)}},
            {"x0": 280, "fields": {"name": (280, 410), "city": (410, 900)}},
        ),
    },
    "professional_corporations": {
        "header_y": 130,
        "wrap": None,
        "columns": (
            {"x0": 0, "fields": {"name": (0, 430)}},
            {"x0": 430, "fields": {"name": (430, 900)}},
        ),
    },
}

_HEADER_TOKENS = frozenset(
    {
        "NAME",
        "CITY",
        "PHONE",
        "SPECIALTY",
        "ADDRESS",
        "POSTAL",
        "FAX",
    }
)


def is_cpsa_directory_pdf(path: Path) -> bool:
    """Live CPSA listings are landscape (~842x595). Fixture PDFs are letter portrait."""
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            return False
        page = pdf.pages[0]
        return page.width >= 800 and page.width > page.height


def looks_like_section_header(text: str) -> bool:
    if not text or "," in text or any(char.isdigit() for char in text):
        return False
    words = text.split()
    if not words or len(words) > 6:
        return False
    lowered = text.lower()
    if lowered.startswith("total number") or "page " in lowered:
        return True
    return True


def extract_listing_rows(path: Path, listing_type: str) -> list[dict[str, str]]:
    import pdfplumber

    layout = LISTING_LAYOUTS[listing_type]
    carry_sections = listing_type == "specialists"
    current_specialty: str | None = None
    rows: list[dict[str, str]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_rows, current_specialty = _rows_from_page(
                page, layout, current_specialty, carry_sections
            )
            rows.extend(page_rows)
    return rows


def rows_to_text(rows: list[dict[str, str]]) -> str:
    field_order = ("name", "address", "city", "postal", "phone", "fax", "specialty")
    lines: list[str] = []
    for row in rows:
        parts = [row[key] for key in field_order if row.get(key)]
        if parts:
            lines.append(" ".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def pdf_to_listing_text(path: Path, listing_type: str) -> str:
    return rows_to_text(extract_listing_rows(path, listing_type))


def _field_for(x: float, fields: dict[str, tuple[float, float]]) -> str | None:
    for name, (start, end) in fields.items():
        if start <= x < end:
            return name
    return None


def _cluster_lines(words: list[dict]) -> list[list[dict]]:
    if not words:
        return []
    ordered = sorted(words, key=lambda word: (word["top"], word["x0"]))
    lines: list[list[dict]] = []
    current = [ordered[0]]
    top = ordered[0]["top"]
    for word in ordered[1:]:
        if word["top"] - top > LINE_GAP:
            lines.append(current)
            current = [word]
            top = word["top"]
        else:
            current.append(word)
    lines.append(current)
    return lines


def _strip_specialty_from_address(address: str | None, specialty: str | None) -> str | None:
    if not address or not specialty:
        return address
    stripped = address.strip()
    if stripped.endswith(specialty):
        stripped = stripped[: -len(specialty)].strip()
    return stripped or None


def _rows_from_page(
    page,
    layout: dict[str, Any],
    current_specialty: str | None,
    carry_sections: bool,
) -> tuple[list[dict[str, str]], str | None]:
    words = [
        word
        for word in (page.extract_words() or [])
        if word["top"] >= layout["header_y"]
        and word["text"].strip().upper() not in _HEADER_TOKENS
    ]
    wrap_field = layout["wrap"]
    collected: list[dict[str, str]] = []
    for column in layout["columns"]:
        col_words = [word for word in words if word["x0"] >= column["x0"]]
        next_x0 = None
        for other in layout["columns"]:
            if other["x0"] > column["x0"]:
                next_x0 = other["x0"] if next_x0 is None else min(next_x0, other["x0"])
        if next_x0 is not None:
            col_words = [word for word in col_words if word["x0"] < next_x0]

        merged: list[dict[str, str]] = []
        for line_words in _cluster_lines(col_words):
            fields: dict[str, list[str]] = defaultdict(list)
            for word in sorted(line_words, key=lambda item: item["x0"]):
                field = _field_for(word["x0"], column["fields"])
                if field:
                    fields[field].append(word["text"])
            line = {key: " ".join(values) for key, values in fields.items() if values}
            if not line:
                continue
            name = line.get("name")
            if name and (
                name.lower().startswith("total number")
                or name.lower() in {"professional corporation", "name"}
            ):
                continue
            if not name:
                leftover = " ".join(line.values())
                min_x = min(word["x0"] for word in line_words)
                only_address = set(line) <= {"address"}
                is_header = (
                    carry_sections
                    and only_address
                    and looks_like_section_header(leftover)
                    and 300 <= min_x <= 490
                )
                if is_header:
                    current_specialty = leftover
                    continue
                if wrap_field is None:
                    continue
                if merged:
                    for key, value in line.items():
                        merged[-1][key] = f"{merged[-1].get(key, '')} {value}".strip()
                continue
            extras = [key for key in line if key != wrap_field]
            is_wrap = (
                wrap_field
                and line.get(wrap_field)
                and not any(line.get(key) for key in extras)
            )
            if is_wrap and merged:
                previous = merged[-1]
                previous[wrap_field] = (
                    f"{previous.get(wrap_field, '')} {line[wrap_field]}"
                ).strip()
            else:
                if carry_sections and current_specialty and not line.get("specialty"):
                    line["specialty"] = current_specialty
                    line["address"] = _strip_specialty_from_address(
                        line.get("address"), current_specialty
                    ) or ""
                    if not line["address"]:
                        line.pop("address", None)
                merged.append(line)
        collected.extend(merged)
    return collected, current_specialty
