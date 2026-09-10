"""Conservative ProfCorp → physician matching.

A medical professional corporation in Alberta is often named for its physician.
We only attach a person when the last name plus first initial are unique among
active licensees. Clinic-style names are left unmatched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.models import InternedRecord
from pipeline.transform.identity import normalize_text

_SUFFIX = re.compile(
    r"""
    \s+
    (?:medical\s+)?
    professional\s+corporation
    \s*$
    """,
    re.I | re.X,
)
_TRAILING_MEDICAL = re.compile(r"\s+medical\s*$", re.I)
_CLINIC_WORDS = frozenset(
    {
        "clinic",
        "clinics",
        "centre",
        "center",
        "hospital",
        "associates",
        "partnership",
        "family",
        "health",
    }
)
_TWO_INITIALS_ONE_LAST = re.compile(
    r"^([A-Za-z])\.?\s*(?:&|and)\s*([A-Za-z])\.?\s+(.+)$",
    re.I,
)
_INITIALS_LAST = re.compile(
    r"^((?:[A-Za-z]\.\s*)+|[A-Za-z]\s+)"
    r"([A-Za-z]{2}[A-Za-z'’.\-]*(?:\s+[A-Za-z][A-Za-z'’.\-]*)*)$"
)


@dataclass(frozen=True)
class CorpOwnerHint:
    last_name: str
    first_initial: str


def _letters_only(value: str) -> str:
    return re.sub(r"[^a-z]", "", (value or "").lower())


def parse_profcorp_owners(name: str) -> list[CorpOwnerHint]:
    core = _SUFFIX.sub("", (name or "").strip())
    core = _TRAILING_MEDICAL.sub("", core).strip(" ,.")
    if not core:
        return []
    words = {part.lower().strip(".,") for part in core.replace("&", " ").split()}
    if words & _CLINIC_WORDS:
        return []

    two = _TWO_INITIALS_ONE_LAST.match(core)
    if two:
        last = two.group(3).strip(" ,.")
        last = _TRAILING_MEDICAL.sub("", last).strip()
        if _letters_only(last):
            return [
                CorpOwnerHint(last, two.group(1).upper()),
                CorpOwnerHint(last, two.group(2).upper()),
            ]

    parts = re.split(r"\s*(?:&| and )\s*", core, flags=re.I)
    owners: list[CorpOwnerHint] = []
    for part in parts:
        part = part.strip(" ,.")
        match = _INITIALS_LAST.match(part)
        if not match:
            return []
        initials = re.findall(r"[A-Za-z]", match.group(1))
        last = match.group(2).strip(" ,.")
        last = _TRAILING_MEDICAL.sub("", last).strip()
        if not initials or not _letters_only(last):
            return []
        owners.append(CorpOwnerHint(last, initials[0].upper()))
    return owners


def match_owner(
    hint: CorpOwnerHint, records: list[InternedRecord]
) -> InternedRecord | None:
    wanted_last = _letters_only(hint.last_name)
    if len(wanted_last) < 2:
        return None
    hits: dict[str, InternedRecord] = {}
    for record in records:
        status = (record.license_status or "").lower()
        if status in {"retired", "deceased"}:
            continue
        last = _letters_only(record.last_name or "")
        if last != wanted_last:
            continue
        first = (record.first_name or "").strip()
        if not first or first[0].upper() != hint.first_initial:
            continue
        hits[normalize_text(record.full_name)] = record
    if len(hits) != 1:
        return None
    return next(iter(hits.values()))
