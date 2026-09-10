from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = Path(__file__).resolve().parent
SEGMENTS_DIR = PACKAGE_ROOT / "configs" / "segments"
FIXTURES_DIR = PACKAGE_ROOT / "fixtures"
SCHEMA_PATH = PACKAGE_ROOT / "load" / "schema.sql"
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"


def segment_raw_dir(segment_id: str, run_id: str) -> Path:
    return RAW_DIR / segment_id / run_id
