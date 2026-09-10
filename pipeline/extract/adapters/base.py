from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pipeline.config import SegmentConfig
from pipeline.models import InternedRecord
from pipeline.paths import FIXTURES_DIR


class LiveExtractNotImplementedError(RuntimeError):
    """Live HTTP extract is not implemented until ToS review lands."""


class SourceAdapter(ABC):
    name: str
    college: str

    def fixture_dir(self) -> Path:
        return FIXTURES_DIR / self.name

    def iter_fixture_files(self) -> Iterator[Path]:
        directory = self.fixture_dir()
        if not directory.exists():
            return
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() in {".txt", ".pdf"}:
                yield path

    @abstractmethod
    def iter_records(
        self, config: SegmentConfig, run_dir: Path
    ) -> Iterator[dict[str, Any]]:
        """Hit the live registry. Must not run until ToS allows it."""

    def parse(self, raw_payload: dict[str, Any]) -> InternedRecord:
        raise NotImplementedError(f"{self.name} does not parse interned JSON payloads")
