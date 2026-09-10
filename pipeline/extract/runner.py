from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import SegmentConfig
from pipeline.extract.adapters import get_adapter
from pipeline.extract.adapters.base import LiveExtractNotImplementedError


class LegalGateError(RuntimeError):
    status = "skipped_legal_gate"


@dataclass
class ExtractResult:
    run_dir: Path
    status: str
    used_fixtures: bool
    file_count: int
    message: str


def raw_dir_has_payloads(run_dir: Path) -> bool:
    if not run_dir.exists():
        return False
    for folder in ("responses", "pages"):
        path = run_dir / folder
        if path.exists() and any(path.iterdir()):
            return True
    return False


def write_fixture_extract(config: SegmentConfig, run_dir: Path) -> ExtractResult:
    adapter = get_adapter(config.source.adapter)
    payloads = adapter.load_fixture_payloads()
    if not payloads:
        raise FileNotFoundError(
            f"No fixtures under {adapter.fixture_dir()} for segment {config.segment_id}"
        )
    responses = run_dir / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    for name, payload in payloads:
        relative = f"responses/{name}"
        (run_dir / relative).write_text(json.dumps(payload, indent=2) + "\n")
        files.append(relative)
    _write_manifest(
        run_dir,
        config=config,
        adapter=adapter.name,
        files=files,
        used_fixtures=True,
    )
    return ExtractResult(
        run_dir=run_dir,
        status="succeeded",
        used_fixtures=True,
        file_count=len(files),
        message=f"Wrote {len(files)} fixture payloads",
    )


def run_extract(
    config: SegmentConfig,
    run_dir: Path,
    *,
    allow_fixtures: bool,
) -> ExtractResult:
    if not config.extract_allowed():
        if allow_fixtures:
            return write_fixture_extract(config, run_dir)
        raise LegalGateError(
            f"Extract skipped for {config.segment_id}: "
            f"tos_status={config.source.tos_status!r}, "
            f"extract.enabled={config.extract.enabled}. "
            "Pass --allow-fixtures or drop files into data/raw."
        )
    adapter = get_adapter(config.source.adapter)
    raise LiveExtractNotImplementedError(
        f"Live extract for adapter {adapter.name!r} is not implemented yet. "
        "Keep extract.enabled false until ToS review, then add the adapter."
    )


def _write_manifest(
    run_dir: Path,
    *,
    config: SegmentConfig,
    adapter: str,
    files: list[str],
    used_fixtures: bool,
) -> None:
    manifest = {
        "segment_id": config.segment_id,
        "adapter": adapter,
        "started_at": datetime.now(UTC).isoformat(),
        "tos_status": config.source.tos_status,
        "used_fixtures": used_fixtures,
        "files": files,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
