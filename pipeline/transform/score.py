from __future__ import annotations

from typing import Any

from pipeline.config import SegmentConfig
from pipeline.models import InternedRecord
from pipeline.transform.normalize import title_rank, word_set

MARKET_POINTS = 15
PRACTICE_TYPE_POINTS = 25
SIZE_POINTS = 30
TITLE_POINTS = 20
CREDENTIAL_POINTS = 10

TITLE_PARTIAL = 8

SIZE_BANDS = (
    (1, 1, 12),
    (2, 3, 22),
    (4, 8, 30),
    (9, 15, 22),
    (16, None, 8),
)


def size_proxy_points(licensee_count: int) -> int:
    for low, high, points in SIZE_BANDS:
        if high is None and licensee_count >= low:
            return points
        if high is not None and low <= licensee_count <= high:
            return points
    return 12


def credential_match(record: InternedRecord, tokens: tuple[str, ...]) -> bool:
    hay = word_set(record.credentials) | word_set(record.title) | word_set(record.full_name)
    wanted = {token.lower() for token in tokens}
    return bool(hay & wanted)


def score_membership(
    record: InternedRecord,
    *,
    config: SegmentConfig,
    practice_type: str,
    licensee_count: int,
) -> dict[str, Any]:
    province = (record.province or "").strip().upper()
    market = MARKET_POINTS if province == config.province.upper() else 0

    if practice_type == "hospital":
        practice_pts = 0
        size_pts = 0
    else:
        practice_pts = PRACTICE_TYPE_POINTS
        size_pts = size_proxy_points(max(licensee_count, 1))

    rank = title_rank(record.title)
    if rank == "decision_maker":
        title_pts = TITLE_POINTS
    elif rank == "low":
        title_pts = 0
    else:
        title_pts = TITLE_PARTIAL

    cred_pts = CREDENTIAL_POINTS if credential_match(record, config.target.credential_tokens) else 0
    total = market + practice_pts + size_pts + title_pts + cred_pts
    return {
        "version": config.score.version,
        "total": total,
        "signals": {
            "market": market,
            "practice_type": practice_pts,
            "size_proxy": size_pts,
            "title": title_pts,
            "credential": cred_pts,
        },
        "inputs": {
            "practice_type": practice_type,
            "licensee_count": licensee_count,
            "title": record.title,
            "title_rank": rank,
        },
    }
