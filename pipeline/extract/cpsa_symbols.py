"""Hardcoded CPSA medical-directory symbols and specialty abbreviations.

Sourced from CPSA's symbols key. Do not re-fetch this on each extract run.
"""

from __future__ import annotations

# Prefix marks that appear to the left of a physician name.
NAME_PREFIX_SYMBOLS = {
    "L": "life_member",
    "H": "honorary_life_member",
    "*": "ccfp_less_than_two_years",
    "**": "ccfp_emergency_less_than_two_years",
    "^": "non_specialist_defined_area",
    "-": "non_specialist",
}

SPECIALTY_ABBREVIATIONS = {
    "ANES": "Anesthesiology",
    "CARD": "Cardiology",
    "DERM": "Dermatology",
    "EM": "Emergency Medicine",
    "FM": "Family Medicine",
    "FPSY": "Forensic Psychiatry",
    "GS": "General Surgery",
    "IM": "Internal Medicine",
    "NEUR": "Neurology",
    "NPM": "Neonatal-Perinatal Medicine",
    "OCCM": "Occupational Medicine",
    "ORTH": "Orthopedic Surgery",
    "PATH": "Pathology",
    "PED": "Pediatrics",
    "PSY": "Psychiatry",
}


def expand_specialty_codes(codes: str | None) -> str | None:
    if not codes:
        return None
    collapsed = " ".join(codes.split())
    parts = [part.strip() for part in collapsed.replace(",", " ").split() if part.strip()]
    if not parts:
        return None
    # Section headers are phrases ("Adolescent Medicine"). Only expand short codes.
    if not all(part.isupper() or "&" in part for part in parts):
        return collapsed
    expanded = [SPECIALTY_ABBREVIATIONS.get(part.upper(), part) for part in parts]
    return "; ".join(expanded)
