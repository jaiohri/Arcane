from __future__ import annotations

import json
import ssl
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import certifi

from pipeline.config import SegmentConfig
from pipeline.extract.cpsa_listings import CPSA_LISTINGS
from pipeline.extract.cpsa_pdf import is_cpsa_directory_pdf, pdf_to_listing_text
from pipeline.extract.pdf import pdf_to_text
from pipeline.extract.result import ExtractResult
from pipeline.models import InternedRecord
from pipeline.paths import FIXTURES_DIR
from pipeline.extract.adapters.base import LiveExtractNotImplementedError, SourceAdapter

USER_AGENT = "arcane-pipeline/0.1 (CPSA directory ingest; tos-gated)"


class CpsaAdapter(SourceAdapter):
    name = "cpsa"
    college = "CPSA"

    def fixture_dir(self) -> Path:
        return FIXTURES_DIR / "cpsa" / "listings"

    def iter_records(
        self, config: SegmentConfig, run_dir: Path
    ) -> Iterator[dict[str, Any]]:
        result = self.extract_to_run_dir(config, run_dir)
        yield {
            "adapter": self.name,
            "file_count": result.file_count,
            "status": result.status,
        }

    def extract_to_run_dir(self, config: SegmentConfig, run_dir: Path) -> ExtractResult:
        pages = run_dir / "pages"
        pages.mkdir(parents=True, exist_ok=True)
        files: list[str] = []
        listing_status: list[dict[str, Any]] = []
        delay = 1.0 / max(config.extract.rate_limit_rps, 0.01)

        for index, listing in enumerate(CPSA_LISTINGS):
            try:
                print(f"downloading {listing.listing_type} from {listing.url}")
                pdf_bytes = _download(listing.url)
                pdf_path = pages / f"{listing.listing_type}.pdf"
                pdf_path.write_bytes(pdf_bytes)
                if is_cpsa_directory_pdf(pdf_path):
                    text = pdf_to_listing_text(pdf_path, listing.listing_type)
                else:
                    text = pdf_to_text(pdf_path)
                txt_path = pages / f"{listing.listing_type}.txt"
                txt_path.write_text(text)
                files.extend(
                    [
                        f"pages/{listing.listing_type}.pdf",
                        f"pages/{listing.listing_type}.txt",
                    ]
                )
                listing_status.append(
                    {"listing": listing.listing_type, "status": "succeeded"}
                )
                print(f"landed {listing.listing_type} ({len(pdf_bytes)} bytes)")
            except Exception as exc:  # isolate one listing from the rest
                listing_status.append(
                    {
                        "listing": listing.listing_type,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                print(f"failed {listing.listing_type}: {exc}")
            if index < len(CPSA_LISTINGS) - 1:
                time.sleep(delay)

        succeeded = sum(1 for item in listing_status if item["status"] == "succeeded")
        if succeeded == 0:
            raise LiveExtractNotImplementedError(
                "All CPSA listing downloads failed: "
                + "; ".join(
                    f"{item['listing']}: {item.get('error', '')}"
                    for item in listing_status
                )
            )

        manifest_extra = {"listings": listing_status}
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "segment_id": config.segment_id,
                    "adapter": self.name,
                    "tos_status": config.source.tos_status,
                    "used_fixtures": False,
                    "files": files,
                    **manifest_extra,
                },
                indent=2,
            )
            + "\n"
        )
        return ExtractResult(
            run_dir=run_dir,
            status="succeeded",
            used_fixtures=False,
            file_count=len(files),
            message=f"Landed {succeeded}/{len(CPSA_LISTINGS)} CPSA listings",
            listing_status=listing_status,
        )

    def parse(self, raw_payload: dict[str, Any]) -> InternedRecord:
        raise NotImplementedError("CPSA parse is listing-text based, not interned JSON")


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=120, context=context) as response:
        return response.read()
