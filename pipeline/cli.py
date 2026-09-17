from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv

from pipeline.config import load_segment
from pipeline.extract.runner import (
    LegalGateError,
    raw_dir_has_payloads,
    run_extract,
)
from pipeline.load.upsert import (
    apply_schema,
    connect,
    load_batch,
    record_run_finish,
    record_run_start,
)
from pipeline.paths import RAW_DIR, REPO_ROOT, segment_raw_dir
from pipeline.transform import run_transform

ALLOWED_PHASES = ("extract", "transform", "load")


def git_sha() -> str | None:
    env = os.environ.get("GITHUB_SHA")
    if env:
        return env
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def parse_phases(raw: str) -> list[str]:
    if raw.strip() == "full":
        return list(ALLOWED_PHASES)
    phases = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [phase for phase in phases if phase not in ALLOWED_PHASES]
    if unknown:
        raise SystemExit(f"Unknown phase(s): {', '.join(unknown)}")
    if not phases:
        raise SystemExit("At least one phase is required")
    return phases


def latest_run_dir(segment_id: str) -> Path | None:
    root = RAW_DIR / segment_id
    if not root.exists():
        return None
    dirs = [path for path in root.iterdir() if path.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda path: path.stat().st_mtime)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run extract, transform, and/or load for one segment")
    run.add_argument("--segment", required=True)
    run.add_argument(
        "--phase",
        default="full",
        help="extract | transform | load | full | comma-separated phases",
    )
    run.add_argument("--run-id", default=None)
    run.add_argument(
        "--allow-fixtures",
        action="store_true",
        help="Land checked-in fixtures instead of hitting a registry",
    )
    run.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    if args.command != "run":
        return 1
    return run_command(args)


def run_command(args: argparse.Namespace) -> int:
    config = load_segment(args.segment)
    phases = parse_phases(args.phase)
    run_id = UUID(args.run_id) if args.run_id else uuid4()
    run_dir = segment_raw_dir(config.segment_id, str(run_id))
    row_counts: dict = {}
    conn = None

    try:
        if "extract" in phases:
            try:
                result = run_extract(config, run_dir, allow_fixtures=args.allow_fixtures)
            except FileNotFoundError as exc:
                print(exc, file=sys.stderr)
                return 1
            except LegalGateError as exc:
                existing = run_dir if raw_dir_has_payloads(run_dir) else None
                if existing is None and args.run_id is None:
                    candidate = latest_run_dir(config.segment_id)
                    if candidate and raw_dir_has_payloads(candidate):
                        existing = candidate
                if phases == ["extract"]:
                    print(exc)
                    if conn:
                        record_run_finish(
                            conn, run_id=run_id, status=exc.status, error=str(exc)
                        )
                    return 0
                if existing is not None:
                    run_dir = existing
                    run_id = UUID(run_dir.name)
                    print(f"{exc} Using existing raw landing at {run_dir}")
                else:
                    print(exc, file=sys.stderr)
                    if conn:
                        record_run_finish(
                            conn, run_id=run_id, status=exc.status, error=str(exc)
                        )
                    return 2
            else:
                row_counts["raw"] = result.file_count
                print(f"extract {result.status}: {result.message} ({run_dir})")
        elif args.run_id is None:
            latest = latest_run_dir(config.segment_id)
            if latest is None:
                print(
                    f"No raw landing for {config.segment_id}. Pass --run-id or run extract.",
                    file=sys.stderr,
                )
                return 1
            run_dir = latest
            run_id = UUID(run_dir.name)

        batch = None
        if "transform" in phases:
            batch = run_transform(run_dir, config)
            row_counts.update(
                {
                    "practitioners": len(batch.practitioners),
                    "orgs": len(batch.organizations),
                    "contacts": len(batch.contacts),
                    "members": len(batch.members),
                }
            )
            print(
                f"transform succeeded: {row_counts.get('practitioners')} practitioners, "
                f"{row_counts.get('orgs')} orgs, "
                f"{row_counts.get('contacts')} contacts, {row_counts.get('members')} members"
            )

        if "load" in phases:
            if not args.database_url:
                print("DATABASE_URL is required for the load phase", file=sys.stderr)
                return 1
            if batch is None:
                batch = run_transform(run_dir, config)
            conn = connect(args.database_url)
            apply_schema(conn)
            record_run_start(
                conn,
                run_id=run_id,
                segment_id=config.segment_id,
                phase=args.phase,
                git_sha=git_sha(),
            )
            loaded = load_batch(conn, config, batch, run_id)
            row_counts.update(loaded)
            print(f"load succeeded: {loaded}")

        if conn:
            record_run_finish(conn, run_id=run_id, status="succeeded", row_counts=row_counts)
        return 0
    except Exception as exc:
        if conn:
            conn.rollback()
            record_run_finish(conn, run_id=run_id, status="failed", error=str(exc))
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
