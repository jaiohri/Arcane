from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import SegmentConfig
from pipeline.extract.adapters import get_adapter
from pipeline.extract.adapters.base import LiveExtractNotImplementedError
from pipeline.extract.result import ExtractResult


class LegalGateError(RuntimeError):
    status = "skipped_legal_gate"


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
    source_dir = adapter.fixture_dir()
    if not source_dir.exists():
        raise FileNotFoundError(
            f"No fixtures under {source_dir} for segment {config.segment_id}"
        )
    files: list[str] = []
    pages = run_dir / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".txt", ".pdf"}:
            continue
        target = pages / path.name
        target.write_bytes(path.read_bytes())
        files.append(f"pages/{path.name}")
    if not files:
        raise FileNotFoundError(
            f"No fixtures under {source_dir} for segment {config.segment_id}"
        )
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
    adapter = get_adapter(config.source.adapter)
    if not config.extract_allowed():
        if allow_fixtures:
            return write_fixture_extract(config, run_dir)
        raise LegalGateError(
            f"Extract skipped for {config.segment_id}: "
            f"tos_status={config.source.tos_status!r}, "
            f"extract.enabled={config.extract.enabled}. "
            "Pass --allow-fixtures or drop files into data/raw."
        )
    extract_live = getattr(adapter, "extract_to_run_dir", None)
    if extract_live is None:
        raise LiveExtractNotImplementedError(
            f"Live extract for adapter {adapter.name!r} is not implemented yet."
        )
    return extract_live(config, run_dir)


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
