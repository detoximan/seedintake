from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from seed_pipeline.integrations import LiveGoogleWorkspace, LiveGoogleWorkspaceConfigError, LiveGoogleWorkspaceDependencyError, MockGoogleWorkspace
from seed_pipeline.intake import build_seed_orchestrator_from_env
from seed_pipeline.intake.dry_run import find_repo_root
from seed_pipeline.intake.markdown_writer import ProcessedMessageRegistry, SeedMarkdownWriter
from seed_pipeline.link_worker.processors import FakeLinkProcessor, PlatformLinkProcessor, RateLimiter
from seed_pipeline.link_worker.queue import LinkQueueStore
from seed_pipeline.link_worker.worker import LinkWorker


def run_link_worker(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root()
    queue_store = LinkQueueStore(repo_root=repo_root)

    if args.link_worker_command == "list":
        if args.summary:
            # Print summary statistics
            new_items = queue_store.list_items(status="new", include_fallback=False)
            fallback_items = queue_store.list_items(status="pending_cookies", include_fallback=True)
            from collections import Counter
            counter_new = Counter(item.platform for item in new_items)
            print("В очереди на обработку:")
            for platform, count in sorted(counter_new.items()):
                print(f"  {platform}: {count}")
            print(f"Проблемных (требуют cookies): {len(fallback_items)}")
            return 0
        else:
            items = queue_store.list_items(status=args.status, platform=args.platform, include_fallback=True)
            payload = [
                {
                    "path": item.relative_path,
                    "status": item.status,
                    "platform": item.platform,
                    "url": item.url,
                }
                for item in items
            ]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                for item in payload:
                    print(f"{item['status']}\t{item['platform']}\t{item['path']}\t{item['url']}")
            return 0

    if args.link_worker_command == "process":
        google_workspace = _build_google_workspace(args)
        orchestrator = build_seed_orchestrator_from_env(
            google_workspace=google_workspace,
            repo_root=repo_root,
        )
        worker = LinkWorker(
            queue_store=queue_store,
            processor=FakeLinkProcessor() if args.fake_processor else PlatformLinkProcessor(),
            orchestrator=orchestrator,
        )
        if args.file:
            results = [worker.process_file(_resolve_cli_file_arg(args.file))]
        else:
            results = worker.process(limit=args.limit, platform=args.platform)
        payload = [result.to_dict() for result in results]
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for result in results:
                detail = result.seed_path or result.reason or ""
                print(f"{result.status}\t{result.path}\t{detail}")

        # Авто-коммит и пуш после завершения обработки, если были успешные
        if any(r.status == "processed" for r in results):
            print("\nAuto-committing processed seeds to GitHub...")
            try:
                subprocess.run(["git", "add", "Inbox/"], cwd=repo_root, check=True)
                subprocess.run(["git", "commit", "-m", "Auto-processed seed links"], cwd=repo_root, check=True)
                subprocess.run(["git", "push"], cwd=repo_root, check=True)
                print("Successfully pushed to GitHub.")
            except subprocess.CalledProcessError as exc:
                print(f"Warning: Git push failed: {exc}", file=sys.stderr)

        return 1 if any(result.status == "failed" for result in results) else 0

    if args.link_worker_command == "process-fallback":
        # Process items from links_fall directory with cookies, one by one with delay
        import time
        # ВСЕГДА пробуем использовать Live Google Sheets для process-fallback
        google_workspace = _build_google_workspace(args)
        print(f"DEBUG: Google Workspace type = {type(google_workspace).__name__}")
        orchestrator = build_seed_orchestrator_from_env(
            google_workspace=google_workspace,
            repo_root=repo_root,
        )
        # Create a processor with cookies for all platforms
        rate_limiter = RateLimiter(
            Path("/tmp/yt_dlp_cookie_rate_limit.json"),
            min_interval=float(os.getenv("COOKIE_REQUEST_INTERVAL", "240"))
        )
        from seed_pipeline.link_worker.processors import UniversalMediaProcessor
        cookie_processor = PlatformLinkProcessor(
            youtube_shorts=UniversalMediaProcessor.from_env(use_cookies=True, rate_limiter=rate_limiter),
            text_post=UniversalMediaProcessor.from_env(use_cookies=True, rate_limiter=rate_limiter),
            instagram_reels=UniversalMediaProcessor.from_env(use_cookies=True, rate_limiter=rate_limiter),
            tiktok=UniversalMediaProcessor.from_env(use_cookies=True, rate_limiter=rate_limiter),
            instagram_post=UniversalMediaProcessor.from_env(use_cookies=True, rate_limiter=rate_limiter),
        )
        
        worker = LinkWorker(
            queue_store=queue_store,
            processor=cookie_processor,
            orchestrator=orchestrator,
        )
        # List items with status pending_cookies in links_fall
        fallback_items = queue_store.list_items(status="pending_cookies", include_fallback=True)
        if not fallback_items:
            print("No fallback items to process.")
            return 0
        
        print(f"Found {len(fallback_items)} fallback items. Processing with 5-minute delay between items...")
        results = []
        for idx, item in enumerate(fallback_items):
            print(f"\nProcessing {idx+1}/{len(fallback_items)}: {item.relative_path}")
            result = worker.process_file(item.path)
            results.append(result)
            if result.status == "processed":
                print(f"Success: {result.seed_path}")
                # After successful processing, leave file in links_fall with status processed.
            else:
                print(f"Failed: {result.reason}")
            # Wait before next item, but not after the last one
            if idx < len(fallback_items) - 1:
                delay = int(os.getenv("COOKIE_REQUEST_INTERVAL", "65"))
                print(f"Waiting {delay} seconds before next item...")
                time.sleep(delay)
        
        # Auto-commit and push after successful processing
        if any(r.status == "processed" for r in results):
            print("\nAuto-committing processed seeds to GitHub...")
            try:
                subprocess.run(["git", "add", "Inbox/"], cwd=repo_root, check=True)
                subprocess.run(["git", "commit", "-m", "Auto-processed seed links (fallback)"], cwd=repo_root, check=True)
                subprocess.run(["git", "push"], cwd=repo_root, check=True)
                print("Successfully pushed to GitHub.")
            except subprocess.CalledProcessError as exc:
                print(f"Warning: Git push failed: {exc}", file=sys.stderr)

        # Output summary
        print("\nSummary:")
        for result in results:
            print(f"{result.status}\t{result.path}\t{result.reason or result.seed_path}")
        return 1 if any(r.status == "failed" for r in results) else 0

    raise ValueError(f"Unknown link worker command: {args.link_worker_command}")


def add_link_worker_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("link-worker", help="List and process local Seed link queue items")
    parser.add_argument("--repo-root", help="Repository root. Defaults to auto-detection.")
    worker_subparsers = parser.add_subparsers(dest="link_worker_command", required=True)

    list_parser = worker_subparsers.add_parser("list", help="List link queue items")
    list_parser.add_argument("--status", choices=["new", "processed", "failed", "pending_cookies"], default="new")
    list_parser.add_argument("--platform", help="Filter by platform")
    list_parser.add_argument("--json", action="store_true")
    list_parser.add_argument("--summary", action="store_true", help="Print summary statistics")

    process_parser = worker_subparsers.add_parser("process", help="Process link queue items with platform processors")
    process_parser.add_argument("--limit", type=int, default=None)
    process_parser.add_argument("--platform", help="Process only items for this platform")
    process_parser.add_argument("--file", help="Process a single queue item path")
    process_parser.add_argument("--json", action="store_true")
    process_parser.add_argument(
        "--fake-processor",
        action="store_true",
        help="Use deterministic fake processing instead of platform download/transcription",
    )
    process_parser.add_argument(
        "--live-google",
        action="store_true",
        help="Use live Google Sheets registry adapter instead of the mock adapter",
    )
    process_parser.add_argument(
        "--mock-google-fail-step",
        choices=["google_sheets"],
        default=None,
        help="Simulate a mock Google Sheets failure for worker recovery checks",
    )

    fallback_parser = worker_subparsers.add_parser("process-fallback", help="Process fallback items (with cookies) with delay")
    fallback_parser.add_argument("--live-google", action="store_true", help="Use live Google Sheets")
    fallback_parser.add_argument("--fake-processor", action="store_true", help="Use fake processor (testing)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed Link Worker local commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    # Re-use add_link_worker_parser but we need to adapt it slightly for standalone use
    # Since add_link_worker_parser expects a subparser, we can't call it directly on 'parser'
    # but we can call it on a fake subparser object or just keep a minimal copy here.
    # Actually, let's just make it a real standalone parser by duplicating the core.
    # Wait, better: add_link_worker_parser IS the core.
    add_link_worker_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # For standalone use, the command is 'link-worker'
    return run_link_worker(args)


def _build_google_workspace(args: argparse.Namespace) -> MockGoogleWorkspace | LiveGoogleWorkspace:
    # Handle the fact that in standalone mode we don't have --live-google etc at the top level
    # but they are in the 'process' command. 
    # args is a Namespace with all attributes flattened.
    live_google = getattr(args, "live_google", False)
    mock_google_fail_step = getattr(args, "mock_google_fail_step", None)

    if live_google and mock_google_fail_step:
        raise ValueError("--mock-google-fail-step can only be used with mock Google mode")
    
    # Auto-detect: if --live-google is not set, check environment variables
    if not live_google:
        # Try to load .env file if it exists
        dotenv_path = Path.cwd() / ".env"
        if dotenv_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(dotenv_path)
                print("Loaded .env file")
            except ImportError:
                # Manual parse
                with open(dotenv_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
                print("Loaded .env file (manual parse)")
        
        # Also try to get variables from shell profile by running a subshell
        try:
            import subprocess
            shell = os.environ.get('SHELL', '/bin/bash')
            rc_file = Path.home() / ('.zshrc' if 'zsh' in shell else '.bashrc')
            if rc_file.exists():
                result = subprocess.run(
                    f"{shell} -c 'source {rc_file} && echo GOOGLE_APPLICATION_CREDENTIALS=$GOOGLE_APPLICATION_CREDENTIALS && echo GOOGLE_SHEET_ID=$GOOGLE_SHEET_ID'",
                    shell=True, capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        if key.strip() and value.strip() and key.strip() not in os.environ:
                            os.environ[key.strip()] = value.strip()
                print(f"Loaded from shell profile: {rc_file}")
        except Exception as e:
            print(f"Could not load from shell profile: {e}")
        
        google_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        google_sheet_id = os.getenv("GOOGLE_SHEET_ID", os.getenv("GOOGLE_SHEETS_ID", "")).strip()
        if google_creds and google_sheet_id:
            live_google = True
            print(f"Auto-detected Google credentials: {google_creds[:20]}..., Sheet: {google_sheet_id}")
    
    if not live_google:
        print("WARNING: Using MockGoogleWorkspace - data will NOT be written to Google Sheets")
        return MockGoogleWorkspace(fail_step=mock_google_fail_step)
    try:
        print("Using LiveGoogleWorkspace - data WILL be written to Google Sheets")
        return LiveGoogleWorkspace.from_env()
    except (LiveGoogleWorkspaceConfigError, LiveGoogleWorkspaceDependencyError) as exc:
        print(str(exc), file=sys.stderr)
        raise


def _resolve_cli_file_arg(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    cwd_path = (Path.cwd() / path).resolve()
    if cwd_path.exists():
        return cwd_path
    return path


if __name__ == "__main__":
    raise SystemExit(main())
