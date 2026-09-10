"""On-demand enrichment. Blocked until an Apollo reseller agreement exists."""

BLOCKED_STATUS = "blocked"


def enrich_contact(_contact_id: str) -> dict[str, str]:
    return {
        "status": BLOCKED_STATUS,
        "reason": "Apollo enrichment is not authorized. No network call was made.",
    }
