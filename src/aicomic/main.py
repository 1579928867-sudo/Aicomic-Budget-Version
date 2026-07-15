"""CLI entry point for AI 漫剧生成助手.

Usage:
    python -m aicomic run chapter.txt
    python -m aicomic run chapter.txt --db data/aicomic.db
"""

import argparse
import os
import sys
from pathlib import Path

import yaml


def _load_config(config_path: Path) -> dict:
    """Load YAML config, with env var overrides."""
    config = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    # Env var overrides (AICOMIC_ prefix)
    env_api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("AICOMIC_ANTHROPIC_API_KEY")
    if env_api_key:
        config.setdefault("anthropic", {})["api_key"] = env_api_key

    env_db_path = os.environ.get("AICOMIC_DATABASE_PATH")
    if env_db_path:
        config.setdefault("database", {})["path"] = env_db_path

    return config


def _resolve_db_path(cli_db: Path | None, config: dict) -> Path:
    if cli_db:
        return cli_db.resolve()
    db_path_str = config.get("database", {}).get("path", "data/aicomic.db")
    return Path(db_path_str).resolve()


def _resolve_api_key(config: dict) -> str:
    api_key = config.get("anthropic", {}).get("api_key", "")
    if not api_key:
        print(
            "Error: Claude API key not found. Set ANTHROPIC_API_KEY env var "
            "or add anthropic.api_key to config/settings.yaml",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key


def cmd_run(args: argparse.Namespace, config: dict):
    """Handle the 'run' subcommand."""
    from .interface import AgentResult
    from .db.repository import Database
    from .bus import AgentBus
    from .llm.claude import ClaudeClient
    from .agents.screenwriter import ScreenwriterAgent
    from .orchestrator import Orchestrator

    chapter_file: Path = args.file
    if not chapter_file.exists():
        print(f"Error: File not found: {chapter_file}", file=sys.stderr)
        sys.exit(1)

    raw_text = chapter_file.read_text(encoding="utf-8")
    if not raw_text.strip():
        print("Error: File is empty", file=sys.stderr)
        sys.exit(1)

    db_path = _resolve_db_path(args.db, config)

    # ── Setup ──
    api_key = _resolve_api_key(config)
    model = config.get("anthropic", {}).get("model", "claude-sonnet-5-20251001")

    db = Database(db_path)
    db.connect()
    db.init_schema()

    try:
        # ── Scaffold novel + chapter in DB ──
        novel_id = db.create_novel(
            title=chapter_file.stem,
            author="",
        )
        chapter_id = db.create_chapter(novel_id, 1, raw_text)

        print(f"Novel created (id={novel_id}), Chapter created (id={chapter_id})")

        # ── Wire up agents ──
        claude = ClaudeClient(api_key=api_key, model=model)
        screenwriter = ScreenwriterAgent(llm_client=claude)

        bus = AgentBus()
        bus.register(screenwriter)

        orchestrator = Orchestrator(bus, db)

        # ── Run ──
        print("Running pipeline...")
        result = orchestrator.run_chapter(chapter_id, raw_text)

        if result.success:
            print("Pipeline completed successfully!")
            if result.data:
                print(f"  Script ID: {result.data.get('script_id')}")
                print(f"  Characters: {result.data.get('characters')}")
                print(f"  Scenes: {result.data.get('scenes_list')}")
        else:
            print(f"Pipeline failed: {result.error}", file=sys.stderr)
            sys.exit(1)

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        prog="aicomic",
        description="AI 漫剧生成助手 — 多 Agent 协作框架",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'run' command
    run_parser = subparsers.add_parser("run", help="Process a chapter through the pipeline")
    run_parser.add_argument(
        "file",
        type=Path,
        help="Path to chapter text file (.txt)",
    )
    run_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database (default: data/aicomic.db)",
    )
    run_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/settings.yaml"),
        help="Path to config file (default: config/settings.yaml)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    config = _load_config(args.config)

    if args.command == "run":
        cmd_run(args, config)


if __name__ == "__main__":
    main()
