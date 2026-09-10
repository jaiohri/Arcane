from __future__ import annotations

import json
from pathlib import Path

from pipeline.config import SegmentConfig
from pipeline.extract.adapters import get_adapter
from pipeline.models import InternedRecord


def parse_run(run_dir: Path, config: SegmentConfig) -> list[InternedRecord]:
    adapter = get_adapter(config.source.adapter)
    records: list[InternedRecord] = []
    for folder in ("responses", "pages"):
        path = run_dir / folder
        if not path.exists():
            continue
        for file in sorted(path.iterdir()):
            if file.suffix.lower() != ".json":
                continue
            payload = json.loads(file.read_text())
            records.append(adapter.parse(payload))
    return records
