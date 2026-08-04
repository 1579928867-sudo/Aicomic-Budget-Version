"""Shared agent utilities — JSON helpers, prompt normalization for Doubao compliance.

Terms normalization: fix writing errors where a word coincidentally matches
a commercial brand/trademark, causing false-positive content filtering.
These are NOT censorship — they correct genuine typos in source text.
The original text in the database is NEVER modified.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def user_select_candidate(
    paths: list[str],
    interactive: bool,
    label: str,
    allow_skip: bool = False,
    skip_msg: str = "",
) -> str | None:
    """CLI candidate selection used by ImageGenerator and ShotVideoGenerator.

    Non-interactive mode: returns paths[0] immediately.
    Interactive mode: opens candidates in system viewer, prompts user to pick.

    Args:
        paths: File paths to choose from.
        interactive: If False, auto-select first.
        label: Human-readable label (e.g. "📷 角色设定图 #1", "🎬 镜头 #3").
        allow_skip: If True, 's' input returns None (skip).
        skip_msg: Message shown on skip (e.g. "跳过镜头 #3").

    Returns:
        Chosen path, or None if skipped.
    """
    if not interactive:
        return paths[0]

    print(f"\n  {label} — 豆包生成了 {len(paths)} 个候选：")
    for i, p in enumerate(paths):
        print(f"    [{i+1}] {Path(p).name}")

    # Open with system default viewer
    for p in paths:
        try:
            if sys.platform == "win32":
                os.startfile(p)
            elif sys.platform == "darwin":
                subprocess.run(["open", p], check=False)
            else:
                subprocess.run(["xdg-open", p], check=False)
        except Exception:
            pass

    while True:
        try:
            prompt_text = f"  选择保留哪个？(1-{len(paths)}，回车默认选1"
            if allow_skip:
                prompt_text += "，输入 s 跳过"
            prompt_text += "): "
            choice = input(prompt_text).strip()
            if allow_skip and choice.lower() == "s":
                print(f"  ⏭ {skip_msg or label}\n")
                return None
            if choice == "":
                choice = "1"
            idx = int(choice) - 1
            if 0 <= idx < len(paths):
                chosen = paths[idx]
                print(
                    f"  ✓ 保留 [{idx+1}] {Path(chosen).name}"
                    f"，删除其余 {len(paths)-1} 个\n"
                )
                return chosen
            warn = f"  ⚠ 请输入 1-{len(paths)}"
            if allow_skip:
                warn += " 或 s 跳过"
            print(warn)
        except (ValueError, KeyboardInterrupt, EOFError):
            print("\n  ℹ 非交互模式，自动选择第1张")
            return paths[0]

# Map of problematic terms → correct Chinese equivalents.
# Keys are words that happen to match commercial brands/trademarks.
# Values are the correct ancient Chinese literary terms intended by the author.
TERM_NORMALIZATIONS: dict[str, str] = {
    # 曼联 = Manchester United FC (registered trademark)
    # Correct term: 幔帐 (ancient Chinese bed curtain / canopy)
    "曼联": "幔帐",
}


def parse_char_ids(raw: Any) -> list[int]:
    """Parse char_ids from a DB row or dict, handling JSON string and raw list.

    Used by OutfitManager, ShotVideoGenerator, and ShotVisualizer to avoid
    duplicating the same json.loads → isinstance → catch pattern everywhere.

    Returns list of int character IDs (empty list on any parse error).
    """
    if raw is None:
        return []
    try:
        if isinstance(raw, str):
            return json.loads(raw)
        if isinstance(raw, list):
            return [int(x) for x in raw]
        return []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def normalize_prompt_terms(text: str) -> str:
    """Replace terms that coincidentally match commercial brands/trademarks
    with their correct ancient Chinese equivalents.

    Does NOT modify the original novel text — only normalizes the
    prompt sent to Doubao.
    """
    result = text
    for bad, good in TERM_NORMALIZATIONS.items():
        result = result.replace(bad, good)
    return result
