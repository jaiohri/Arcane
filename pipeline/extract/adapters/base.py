from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pipeline.config import SegmentConfig
from pipeline.models import InternedRecord
from pipeline.paths import FIXTURES_DIR


class LiveExtractNotImplementedError(RuntimeError):
    """Live HTTP extract is not implemented until ToS review lands."""


def parse_interned_json(
    payload: dict[str, Any], *, source_system: str, license_college: str
) -> InternedRecord:
    full_name = (payload.get("full_name") or "").strip()
    first_name = payload.get("first_name")
    last_name = payload.get("last_name")
    if full_name and not first_name and not last_name:
        parts = full_name.split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None
    return InternedRecord(
        source_system=source_system,
        license_college=license_college,
        license_number=payload.get("license_number"),
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        credentials=payload.get("credentials"),
        specialty=payload.get("specialty"),
        title=payload.get("title"),
        license_status=payload.get("license_status"),
        practice_name=(payload.get("practice_name") or "").strip(),
        source_org_id=payload.get("source_org_id"),
        address_line1=payload.get("address_line1"),
        city=payload.get("city"),
        province=payload.get("province"),
        postal_code=payload.get("postal_code"),
        country=payload.get("country") or "CA",
        practice_type_hint=payload.get("practice_type_hint"),
        raw_payload=payload,
    )


class SourceAdapter(ABC):
    name: str
    college: str

    def fixture_dir(self) -> Path:
        return FIXTURES_DIR / self.name

    def iter_fixture_files(self) -> Iterator[Path]:
        directory = self.fixture_dir()
        if not directory.exists():
            return
        yield from sorted(directory.glob("*.json"))

    def parse(self, raw_payload: dict[str, Any]) -> InternedRecord:
        return parse_interned_json(
            raw_payload, source_system=self.name, license_college=self.college
        )

    def load_fixture_payloads(self) -> list[tuple[str, dict[str, Any]]]:
        payloads: list[tuple[str, dict[str, Any]]] = []
        for path in self.iter_fixture_files():
            payloads.append((path.name, json.loads(path.read_text())))
        return payloads

    @abstractmethod
    def iter_records(
        self, config: SegmentConfig, run_dir: Path
    ) -> Iterator[dict[str, Any]]:
        """Hit the live registry. Must not run until ToS allows it."""
