"""CLI entry point for AI 漫剧生成助手.

Usage:
    python -m aicomic run chapter.txt
    python -m aicomic run chapter.txt --backend deepseek
    python -m aicomic run chapter.txt --backend claude
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

    # Env var overrides
    for key, env_var in [
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
    ]:
        env_val = os.environ.get(env_var) or os.environ.get(f"AICOMIC_{env_var}")
        if env_val:
            config.setdefault(key, {})["api_key"] = env_val

    env_db_path = os.environ.get("AICOMIC_DATABASE_PATH")
    if env_db_path:
        config.setdefault("database", {})["path"] = env_db_path

    return config


def _resolve_db_path(cli_db: Path | None, config: dict) -> Path:
    if cli_db:
        return cli_db.resolve()
    db_path_str = config.get("database", {}).get("path", "data/aicomic.db")
    return Path(db_path_str).resolve()


def _resolve_backend(cli_backend: str | None, config: dict) -> str:
    if cli_backend:
        return cli_backend
    return config.get("backend", "deepseek")


def _get_api_key(backend: str, config: dict) -> str:
    key = config.get(backend, {}).get("api_key", "")
    if not key:
        env_map = {"deepseek": "DEEPSEEK_API_KEY", "claude": "ANTHROPIC_API_KEY"}
        print(
            f"Error: {backend} API key not found. "
            f"Set {env_map.get(backend, 'API_KEY')} env var "
            f"or add {backend}.api_key to config/settings.yaml",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def _build_llm_client(backend: str, config: dict):
    """Build the LLM client based on backend choice."""
    api_key = _get_api_key(backend, config)
    backend_config = config.get(backend, {})

    if backend == "deepseek":
        from .llm.deepseek import DeepSeekClient

        return DeepSeekClient(
            api_key=api_key,
            model=backend_config.get("model", "deepseek-chat"),
            base_url=backend_config.get("base_url", "https://api.deepseek.com"),
        )
    elif backend == "claude":
        from .llm.claude import ClaudeClient

        return ClaudeClient(
            api_key=api_key,
            model=backend_config.get("model", "claude-sonnet-5-20251001"),
        )
    else:
        print(f"Error: Unknown backend '{backend}'. Use 'deepseek' or 'claude'.", file=sys.stderr)
        sys.exit(1)


def cmd_run(args: argparse.Namespace, config: dict):
    """Handle the 'run' subcommand."""
    from .db.repository import Database
    from .bus import AgentBus
    from .agents.screenwriter import ScreenwriterAgent
    from .agents.char_designer import CharacterDesignerAgent
    from .agents.scene_designer import SceneDesignerAgent
    from .agents.shot_visualizer import ShotVisualizerAgent
    from .agents.video_generator import VideoGeneratorAgent
    from .agents.video_composer import VideoComposerAgent
    from .doubao.client import MockVideoGenerator, DoubaoVideoGenerator
    from .agents.image_generator import ImageGeneratorAgent
    from .doubao.browser import DoubaoBrowserClient
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
    backend = _resolve_backend(args.backend, config)

    print(f"Backend: {backend}")

    db = Database(db_path)
    db.connect()
    db.init_schema()
    db.migrate_schema()

    try:
        # ── Scaffold novel + chapter in DB ──
        novel_id = db.create_novel(
            title=chapter_file.stem,
            author="",
        )
        chapter_id = db.create_chapter(novel_id, 1, raw_text)

        print(f"Novel created (id={novel_id}), Chapter created (id={chapter_id})")

        # ── Wire up agents ──
        llm = _build_llm_client(backend, config)
        screenwriter = ScreenwriterAgent(llm_client=llm)
        char_designer = CharacterDesignerAgent(llm_client=llm)
        scene_designer = SceneDesignerAgent(llm_client=llm)
        shot_visualizer = ShotVisualizerAgent(llm_client=llm)

        bus = AgentBus()
        bus.register(screenwriter)
        bus.register(char_designer)
        bus.register(scene_designer)
        bus.register(shot_visualizer)

        with_images = getattr(args, "with_images", False)
        with_video = getattr(args, "with_video", False)

        # Resolve video_backend early for shared browser_client decision
        video_cfg = config.get("video", {})
        video_output_dir = Path(video_cfg.get("output_dir", "data/videos"))
        video_backend = None
        if with_video:
            video_backend = getattr(args, "video_backend", None) or video_cfg.get("generator", "mock")

        # v0.6: Shared browser client (created once, shared across agents)
        browser_client = None
        if with_images or (with_video and video_backend == "doubao"):
            doubao_cfg = config.get("doubao", {})
            browser_client = DoubaoBrowserClient(
                cookie_file=Path(doubao_cfg.get("cookie_file", "data/doubao_cookies.json")),
                headless=doubao_cfg.get("headless", True),
                output_dir=doubao_cfg.get("output_dir", "data/"),
                timeout_sec=doubao_cfg.get("timeout_sec", 300),
                poll_interval_sec=doubao_cfg.get("poll_interval_sec", 3),
                rate_limit_sec=doubao_cfg.get("rate_limit_sec", 10),
                selectors=doubao_cfg.get("selectors", {}),
            )
            # Inject page URLs from config if present
            pages_cfg = doubao_cfg.get("pages", {})
            if pages_cfg:
                browser_client.page_urls.update(pages_cfg)

        if with_images:
            image_generator = ImageGeneratorAgent(browser_client=browser_client)
            bus.register(image_generator)

        if with_video:
            if video_backend == "doubao":
                doubao_cfg = config.get("doubao", {})
                video_gen = DoubaoVideoGenerator(
                    cookie_file=Path(doubao_cfg.get("cookie_file", "data/doubao_cookies.json")),
                    headless=doubao_cfg.get("headless", True),
                    output_dir=str(video_output_dir),
                    timeout_sec=doubao_cfg.get("timeout_sec", 300),
                    poll_interval_sec=doubao_cfg.get("poll_interval_sec", 3),
                    video_page_url=doubao_cfg.get("video_page_url", "https://jimeng.jianying.com/ai-tool/video/generate"),
                    selectors=doubao_cfg.get("selectors", {}).get("video", {}),
                    browser_client=browser_client,  # v0.6: shared
                )
            else:
                video_gen = MockVideoGenerator(output_dir=video_output_dir)

            video_agent = VideoGeneratorAgent(llm_client=llm, video_generator=video_gen)
            bus.register(video_agent)

            # v0.5: Video Composer
            composer_output_dir = str(video_output_dir)
            video_composer = VideoComposerAgent(output_dir=composer_output_dir)
            bus.register(video_composer)

        orchestrator = Orchestrator(bus, db)

        # ── Run ──
        pipeline_label = "v0.6"
        steps = "Screenwriter → CharDesigner → SceneDesigner"
        steps += " → ImageGenerator" if with_images else ""
        steps += " → ShotVisualizer"
        steps += " → VideoGenerator → VideoComposer" if with_video else ""
        print(f"Running pipeline ({pipeline_label}: {steps})...")
        result = orchestrator.run_chapter(
            chapter_id, raw_text, with_video=with_video, with_images=with_images,
        )

        if result.success:
            print("Pipeline completed successfully!")
            if result.data:
                print(f"  Script ID: {result.data.get('script_id')}")
                print(f"  Characters: {result.data.get('characters')}")
                print(f"  Scenes: {result.data.get('scenes_list')}")
                print(f"  Char variants created: {result.data.get('char_variants_created', 0)}")
                print(f"  Scenes updated: {result.data.get('scenes_updated', 0)}")
                if with_images:
                    print(f"  Images generated: {result.data.get('images_generated', 0)}")
                print(f"  Shots visualized: {result.data.get('shots_visualized', 0)}")
                if with_video:
                    print(f"  Video clips created: {result.data.get('clips_created', 0)}")
                    final_path = result.data.get("final_video_path")
                    if final_path:
                        print(f"  Final video: {final_path}")
        else:
            print(f"Pipeline failed: {result.error}", file=sys.stderr)
            sys.exit(1)

    finally:
        if browser_client:
            browser_client.close()
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
        "--backend",
        type=str,
        choices=["deepseek", "claude"],
        default=None,
        help="LLM backend: deepseek (default) or claude",
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
    run_parser.add_argument(
        "--with-images",
        action="store_true",
        default=False,
        help="Also generate real images for characters and scenes via Doubao (default: off)",
    )
    run_parser.add_argument(
        "--with-video",
        action="store_true",
        default=False,
        help="Also generate video clips via VideoGenerator (default: off, expensive)",
    )
    run_parser.add_argument(
        "--video-backend",
        type=str,
        choices=["mock", "doubao"],
        default=None,
        help="Video generator backend: mock (default, safe) or doubao (real generation)",
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
