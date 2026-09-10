"""CPSA Medical Directory listing catalog.

Live download runs when the medical segment has tos_status allowed and extract.enabled.
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_URL = "https://cpsa.ca/MedicalDirectory"


@dataclass(frozen=True)
class CpsaListing:
    listing_type: str
    filename: str
    licence_status: str | None
    kind: str  # people | corporations

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.filename.replace(' ', '%20')}"


CPSA_LISTINGS: tuple[CpsaListing, ...] = (
    CpsaListing("alphabetical", "Alphabetical Listing.pdf", "active", "people"),
    CpsaListing("specialists", "Specialty Listing.pdf", "active", "people"),
    CpsaListing("non_specialists", "Non Specialty Listing.pdf", "active", "people"),
    CpsaListing("retired", "Retired Listing.pdf", "retired", "people"),
    CpsaListing("obituaries", "Obituaries Listing.pdf", "deceased", "people"),
    CpsaListing(
        "professional_corporations",
        "ProfCorp Listing.pdf",
        None,
        "corporations",
    ),
)

LISTING_BY_TYPE = {item.listing_type: item for item in CPSA_LISTINGS}

# Alphabetical / specialists: people only (city is not a practice).
# Non-specialists: org if an address is present.
# Retired / obituaries: people only.
# ProfCorp: organizations only.
PROMOTE_ORGS = frozenset({"non_specialists"})
PROMOTE_CONTACTS = frozenset(
    {"alphabetical", "specialists", "non_specialists", "retired", "obituaries"}
)
PROMOTE_PRACTITIONERS = PROMOTE_CONTACTS
