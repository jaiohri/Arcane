from __future__ import annotations

import re

from pipeline.config import SegmentConfig
from pipeline.models import InternedRecord

HOSPITAL_TOKENS = (
    "hospital",
    "health authority",
    "health-authority",
    "regional health",
    "university of",
    "faculty of",
    "health sciences centre",
    "health sciences center",
)

LOW_TITLE_TOKENS = ("associate", "resident", "student", "intern")

DECISION_TITLES = {
    "owner": 100,
    "practice owner": 100,
    "founder": 90,
    "managing partner": 80,
}

WORD = re.compile(r"[a-z0-9]+")


def word_set(value: str | None) -> set[str]:
    return set(WORD.findall((value or "").lower()))


def detect_practice_type(record: InternedRecord, licensee_count: int) -> str:
    hint = (record.practice_type_hint or "").lower()
    name = (record.practice_name or "").lower()
    if hint == "hospital" or any(token in name for token in HOSPITAL_TOKENS):
        return "hospital"
    if licensee_count <= 0:
        return "unknown"
    if licensee_count == 1:
        return "solo"
    return "group"


def sector_for(profession: str) -> str:
    if profession == "dentist":
        return "dental"
    return "medical"


def industry_for(profession: str, practice_type: str, config: SegmentConfig) -> str:
    if practice_type == "hospital" and "Hospital and Health Care" in config.industries:
        return "Hospital and Health Care"
    if profession == "dentist":
        return "Dentists"
    return "Medical Practices"


def display_title(record: InternedRecord) -> str | None:
    if record.title and record.title.strip():
        return record.title.strip()
    return record.credentials


def title_rank(title: str | None) -> str:
    lowered = (title or "").strip().lower()
    if lowered in DECISION_TITLES:
        return "decision_maker"
    words = word_set(title)
    if words & set(LOW_TITLE_TOKENS):
        return "low"
    if not lowered:
        return "credential_only"
    return "credential_only"


def title_sort_rank(title: str | None) -> int:
    lowered = (title or "").strip().lower()
    if lowered in DECISION_TITLES:
        return DECISION_TITLES[lowered]
    if title_rank(title) == "low":
        return 0
    return 10


def status_sort_rank(status: str | None) -> int:
    lowered = (status or "").strip().lower()
    if lowered in {"active", "practising", "practicing", "licensed"}:
        return 2
    if lowered in {"former", "inactive", "cancelled", "retired"}:
        return 0
    return 1
