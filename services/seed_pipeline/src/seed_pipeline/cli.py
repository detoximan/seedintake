from __future__ import annotations

import logging, sys, os
logging.basicConfig(level=logging.DEBUG if os.getenv("SEED_DEBUG") else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr, force=True)

import argparse
import json
from pathlib import Path

# Попытка загрузить переменные окружения из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from seed_pipeline.integrations import (
    LiveGoogleWorkspace,
    LiveGoogleWorkspaceConfigError,
    LiveGoogleWorkspaceDependencyError,
    MockGoogleWorkspace,
    config_error_record,
    dependency_error_record,
)
from seed_pipeline.intake import build_dry_run, build_seed_orchestrator_from_env
from seed_pipeline.intake.dry_run import parse_case_file
from seed_pipeline.link_worker.cli import add_link_worker_parser, run_link_worker
from seed_pipeline.schemas import ErrorRecord, SeedCreationResult, SeedInput

def run_smoke(args: argparse.Namespace) -> int:
    try:
        from seed_pipeline.intake.github_storage import GitHubStorageConfigError
        build_seed_orchestrator_from_env()
    except GitHubStorageConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Smoke error: {exc}", file=sys.stderr)
        return 1
    print("Smoke OK")
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke_parser = subparsers.add_parser("smoke", help="Run a quick smoke test")
    add_link_worker_parser(subparsers)

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "smoke":
        return run_smoke(args)
    if args.command == "link-worker":
        return run_link_worker(args)

    parser.error("Unknown command")
    return 2

if __name__ == "__main__":
    sys.exit(main())
