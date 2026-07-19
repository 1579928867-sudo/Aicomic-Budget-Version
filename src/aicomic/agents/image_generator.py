"""Image Generator Agent — generates real images for character variants and scenes.

Uses DoubaoBrowserClient to turn composite three-view / multi-view prompts
into actual image files, with CLI interactive selection from 4 candidates,
then saves chosen file paths back to the database.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database


class ImageGeneratorAgent(AgentInterface):
    """Generates real images for character variants and scene cards via Doubao.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"images_generated": int, "variants_processed": int, "scenes_processed": int}

    Pipeline position: Step 3.5 — after SceneDesigner, before ShotVisualizer.
    Only runs when --with-images is passed.
    """

    agent_name = "image-generator"

    def __init__(self, browser_client: "DoubaoBrowserClient") -> None:
        """Args:
            browser_client: DoubaoBrowserClient instance (shared across agents).
        """
        self.browser = browser_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

    def _process_entity(
        self,
        db: Database,
        chapter_id: int,
        entity: dict,
        prompt_field: str,
        update_fn: Any,
        entity_type: str,
    ) -> bool:
        """Generate composite image for one entity. Returns True if an image was saved.

        Flow: send composite prompt → Doubao returns up to 4 candidates →
        CLI user selects best one → save path to DB → delete unchosen files.
        """
        prompt = entity.get(prompt_field, "")
        if not prompt:
            return False

        print(f"    [{entity_type} #{entity['id']}] 生成中...")
        try:
            result = self.browser.generate_image(prompt=prompt, aspect_ratio="16:9")
            if not result.success or not result.file_paths:
                db.log(
                    self.agent_name, chapter_id,
                    f"{entity_type}_image_failed",
                    {"entity_id": entity["id"], "error": result.error},
                    level="WARNING",
                )
                print(f"    [{entity_type} #{entity['id']}] ✗ 生成失败: {result.error}")
                return False

            paths = result.file_paths
            # Only 1 image — auto-save, no selection needed
            if len(paths) == 1:
                update_fn(entity["id"], paths[0])
                print(f"    [{entity_type} #{entity['id']}] ✓ 已保存 (仅1张候选)")
                return True

            # Multiple candidates — user selection
            chosen = self._user_select_image(paths, entity_type, entity["id"])
            if chosen is None:
                return False

            update_fn(entity["id"], chosen)

            # Delete unchosen files
            for p in paths:
                if p != chosen:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except Exception:
                        pass

            return True

        except Exception as e:
            db.log(
                self.agent_name, chapter_id,
                f"{entity_type}_image_error",
                {"entity_id": entity["id"], "error": str(e)},
                level="WARNING",
            )
            print(f"    [{entity_type} #{entity['id']}] ✗ 异常: {e}")
            return False

    def _user_select_image(
        self, paths: list[str], entity_type: str, entity_id: int
    ) -> str | None:
        """Open all candidate images with system viewer, prompt user to pick one.

        Returns the chosen path, or None if user cancels.
        """
        print(f"\n  📷 {entity_type} #{entity_id} — 豆包生成了 {len(paths)} 张候选图：")
        for i, p in enumerate(paths):
            print(f"    [{i+1}] {Path(p).name}")

        # Open images with system default viewer
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
                choice = input(
                    f"  选择保留哪张？(1-{len(paths)}，回车默认选1): "
                ).strip()
                if choice == "":
                    choice = "1"
                idx = int(choice) - 1
                if 0 <= idx < len(paths):
                    chosen = paths[idx]
                    print(
                        f"  ✓ 保留 [{idx+1}] {Path(chosen).name}"
                        f"，删除其余 {len(paths)-1} 张\n"
                    )
                    return chosen
                print(f"  ⚠ 请输入 1-{len(paths)}")
            except (ValueError, KeyboardInterrupt, EOFError):
                print("\n  ℹ 非交互模式，自动选择第1张")
                return paths[0]

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]

        # ── Idempotency check ──
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"script_id": script_id})

        try:
            # ── Load variant rows with pending three-view images ──
            variant_rows = db.conn.execute(
                """SELECT id, three_view_prompt
                   FROM appearance_variant
                   WHERE three_view_prompt != '' AND three_view_image = ''
                   ORDER BY id"""
            ).fetchall()
            variants = [dict(r) for r in variant_rows]

            # ── Load scene rows with pending multi-view images ──
            scene_rows = db.conn.execute(
                """SELECT id, multi_view_prompt
                   FROM scene_card
                   WHERE multi_view_prompt != '' AND multi_view_image = ''
                   ORDER BY id"""
            ).fetchall()
            scenes = [dict(r) for r in scene_rows]

            total_entities = len(variants) + len(scenes)
            print(
                f"  Image Generator: 开始生成图片 "
                f"({total_entities} 实体: {len(variants)} 角色三视图, {len(scenes)} 场景多景别)..."
            )

            # ── Generate character three-view images ──
            variants_processed = 0
            for vi, variant in enumerate(variants):
                label = f"角色三视图 {vi+1}/{len(variants)}"
                print(f"    [{label}]")
                if self._process_entity(
                    db, chapter_id, variant, "three_view_prompt",
                    db.update_appearance_variant_three_view, "角色变体",
                ):
                    variants_processed += 1

            # ── Generate scene multi-view images ──
            scenes_processed = 0
            for si, scene in enumerate(scenes):
                label = f"场景多景别 {si+1}/{len(scenes)}"
                print(f"    [{label}]")
                if self._process_entity(
                    db, chapter_id, scene, "multi_view_prompt",
                    db.update_scene_card_multi_view, "场景",
                ):
                    scenes_processed += 1

            images_generated = variants_processed + scenes_processed
            had_pending_work = bool(variants) or bool(scenes)

            if images_generated > 0:
                db.set_agent_status(self.agent_name, chapter_id, "done")
                db.log(self.agent_name, chapter_id, "completed", {
                    "images_generated": images_generated,
                    "variants_processed": variants_processed,
                    "scenes_processed": scenes_processed,
                })
                return AgentResult(success=True, data={
                    "images_generated": images_generated,
                    "variants_processed": variants_processed,
                    "scenes_processed": scenes_processed,
                })
            elif had_pending_work:
                db.set_agent_status(self.agent_name, chapter_id, "failed")
                err_msg = (
                    f"No images generated from {len(variants)} variants "
                    f"and {len(scenes)} scenes"
                )
                db.log(self.agent_name, chapter_id, "completed_all_failed",
                       {"reason": err_msg}, level="ERROR")
                return AgentResult(success=False, error=err_msg, data={
                    "images_generated": 0,
                    "variants_processed": 0,
                    "scenes_processed": 0,
                })
            else:
                db.set_agent_status(self.agent_name, chapter_id, "done")
                db.log(self.agent_name, chapter_id, "completed_nothing_pending",
                       {"reason": "No pending three-view or multi-view images"},
                       level="INFO")
                return AgentResult(success=True, data={
                    "images_generated": 0,
                    "variants_processed": 0,
                    "scenes_processed": 0,
                })
        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
