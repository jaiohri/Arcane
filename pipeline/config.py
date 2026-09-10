from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import yaml

from pipeline.paths import SEGMENTS_DIR


@dataclass(frozen=True)
class SourceConfig:
    adapter: str
    tos_status: str
    tos_notes: str = ""


@dataclass(frozen=True)
class TargetConfig:
    headcount_min: int
    headcount_max: int
    decision_maker_titles: tuple[str, ...]
    credential_tokens: tuple[str, ...]


@dataclass(frozen=True)
class ExtractConfig:
    enabled: bool
    rate_limit_rps: float


@dataclass(frozen=True)
class ScoreConfig:
    version: int


@dataclass(frozen=True)
class SegmentConfig:
    segment_id: str
    display_name: str
    province: str
    country: str
    profession: str
    industries: tuple[str, ...]
    source: SourceConfig
    target: TargetConfig
    extract: ExtractConfig
    score: ScoreConfig
    path: Path
    config_hash: str

    def extract_allowed(self) -> bool:
        return self.source.tos_status == "allowed" and self.extract.enabled


def load_segment(segment_id: str) -> SegmentConfig:
    path = SEGMENTS_DIR / f"{segment_id}.yaml"
    if not path.exists():
        known = sorted(p.stem for p in SEGMENTS_DIR.glob("*.yaml"))
        raise FileNotFoundError(
            f"Unknown segment {segment_id!r}. Available: {', '.join(known) or '(none)'}"
        )
    return load_segment_path(path)


def load_segment_path(path: Path) -> SegmentConfig:
    raw = yaml.safe_load(path.read_text())
    source = raw["source"]
    target = raw["target"]
    extract = raw["extract"]
    score = raw["score"]
    return SegmentConfig(
        segment_id=raw["segment_id"],
        display_name=raw["display_name"],
        province=raw["province"],
        country=raw["country"],
        profession=raw["profession"],
        industries=tuple(raw.get("industries") or ()),
        source=SourceConfig(
            adapter=source["adapter"],
            tos_status=source["tos_status"],
            tos_notes=source.get("tos_notes") or "",
        ),
        target=TargetConfig(
            headcount_min=int(target["headcount_min"]),
            headcount_max=int(target["headcount_max"]),
            decision_maker_titles=tuple(target.get("decision_maker_titles") or ()),
            credential_tokens=tuple(target.get("credential_tokens") or ()),
        ),
        extract=ExtractConfig(
            enabled=bool(extract["enabled"]),
            rate_limit_rps=float(extract["rate_limit_rps"]),
        ),
        score=ScoreConfig(version=int(score["version"])),
        path=path,
        config_hash=sha256(path.read_bytes()).hexdigest(),
    )
