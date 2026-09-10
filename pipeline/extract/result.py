from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExtractResult:
    run_dir: Path
    status: str
    used_fixtures: bool
    file_count: int
    message: str
    listing_status: list[dict[str, Any]] = field(default_factory=list)
