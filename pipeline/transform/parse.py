from __future__ import annotations

from pathlib import Path

from pipeline.config import SegmentConfig
from pipeline.extract.cpsa_listings import CPSA_LISTINGS
from pipeline.extract.cpsa_pdf import (
    extract_listing_rows,
    is_cpsa_directory_pdf,
    rows_to_text,
)
from pipeline.extract.pdf import pdf_to_text
from pipeline.models import InternedRecord
from pipeline.transform.cpsa import ListingParse, parse_listing_rows, parse_listing_text


def parse_run(run_dir: Path, config: SegmentConfig) -> tuple[list[InternedRecord], list[ListingParse], list[str]]:
    if config.source.adapter == "cpsa":
        return parse_cpsa_run(run_dir)
    records: list[InternedRecord] = []
    errors: list[str] = []
    for folder in ("responses", "pages"):
        path = run_dir / folder
        if not path.exists():
            continue
        for file in sorted(path.iterdir()):
            if file.suffix.lower() not in {".txt", ".pdf"}:
                continue
            errors.append(
                f"{config.source.adapter} has no parser for {file.name}; dentist ingest is not in this build"
            )
    if not records and not errors:
        raise FileNotFoundError(f"No payloads in {run_dir}/responses or {run_dir}/pages")
    return records, [], errors


def parse_cpsa_run(run_dir: Path) -> tuple[list[InternedRecord], list[ListingParse], list[str]]:
    pages = run_dir / "pages"
    records: list[InternedRecord] = []
    listings: list[ListingParse] = []
    errors: list[str] = []
    for listing in CPSA_LISTINGS:
        txt_path = pages / f"{listing.listing_type}.txt"
        pdf_path = pages / f"{listing.listing_type}.pdf"
        try:
            parsed: ListingParse | None = None
            if pdf_path.exists() and is_cpsa_directory_pdf(pdf_path):
                rows = extract_listing_rows(pdf_path, listing.listing_type)
                txt_path.write_text(rows_to_text(rows))
                parsed = parse_listing_rows(listing.listing_type, rows)
            elif txt_path.exists():
                parsed = parse_listing_text(listing.listing_type, txt_path.read_text())
            elif pdf_path.exists():
                text = pdf_to_text(pdf_path)
                txt_path.write_text(text)
                parsed = parse_listing_text(listing.listing_type, text)
            if parsed is None:
                continue
            listings.append(parsed)
            records.extend(parsed.records)
        except Exception as exc:
            errors.append(f"{listing.listing_type}: {exc}")
    if not listings and not errors:
        raise FileNotFoundError(f"No CPSA listing files in {pages}")
    return records, listings, errors
