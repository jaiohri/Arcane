from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pipeline.config import SegmentConfig
from pipeline.extract.adapters.base import LiveExtractNotImplementedError, SourceAdapter


class CpsaAdapter(SourceAdapter):
    name = "cpsa"
    college = "CPSA"

    def iter_records(
        self, config: SegmentConfig, run_dir: Path
    ) -> Iterator[dict[str, Any]]:
        raise LiveExtractNotImplementedError(
            "CPSA live extract is not implemented. Use fixtures or a manual raw drop "
            "until tos_status is allowed."
        )
