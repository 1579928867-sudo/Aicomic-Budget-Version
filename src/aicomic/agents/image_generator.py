"""Image Generator Agent — generates design sheet images for character outfits
and multi-view images for scenes.

Uses DoubaoBrowserClient to turn prompts into actual image files,
with CLI interactive selection from 4 candidates,
then saves chosen file paths back to the database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database
from .prompt_utils import normalize_prompt_terms, user_select_candidate


class ImageGeneratorAgent(AgentInterface):
    """Generates design sheet images for character outfits and scene multi-views.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"images_generated": int, "outfits_processed": int, "scenes_processed": int}

    Pipeline position: after CharDesigner + SceneDesigner, before ShotVisualizer.
    Only runs when --with-images is passed.
    """

    agent_name = "image-generator"

    def __init__(self, browser_client: "DoubaoBrowserClient",
                 interactive: bool = False) -> None:
        """Args:
            browser_client: DoubaoBrowserClient instance (shared across agents).
            interactive: If True, open candidates with system viewer and prompt
                         user to pick one. Default False — auto-selects first.
        """
        self.browser = browser_client
        self.interactive = interactive

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
        reference_images: list[str] | None = None,
        *,
        aspect_ratio: str = "16:9",
    ) -> bool:
        """Generate and save an image for one entity. Returns True if an image was saved.

        Flow: Doubao returns up to 4 candidates → CLI user selects → save → cleanup.
        """
        prompt = entity.get(prompt_field, "")
        if not prompt:
            return False

        ref_label = f" (+{len(reference_images)}参考图)" if reference_images else ""
        print(f"    [{entity_type} #{entity['id']}]{ref_label} 生成中...")
        try:
            result = self.browser.generate_image(
                prompt=normalize_prompt_terms(prompt), aspect_ratio=aspect_ratio,
                reference_images=reference_images,
            )
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
            chosen = user_select_candidate(
                paths, self.interactive, f"📷 {entity_type} #{entity['id']}",
            )
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

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]

        # ── Idempotency check ──
        skip = begin_agent_run(self.agent_name, chapter_id, db,
                               {"script_id": script_id})
        if skip:
            return skip

        try:
            # ── Load outfits with pending images (prompt exists, image_path empty) ──
            outfit_rows = db.conn.execute(
                """SELECT id, prompt, character_id, tag
                   FROM character_outfit
                   WHERE prompt != '' AND (image_path = '' OR image_path IS NULL)
                   ORDER BY is_default DESC, id"""
            ).fetchall()
            outfits = [dict(r) for r in outfit_rows]

            # ── Load scenes with pending multi-view images (unchanged from old code) ──
            scene_rows = db.conn.execute(
                """SELECT id, multi_view_prompt
                   FROM scene_card
                   WHERE multi_view_prompt != '' AND multi_view_image = ''
                   ORDER BY id"""
            ).fetchall()
            scenes = [dict(r) for r in scene_rows]

            total_entities = len(outfits) + len(scenes)
            print(
                f"  Image Generator: 开始生成图片 "
                f"({total_entities} 实体: {len(outfits)} 角色设定图, {len(scenes)} 场景多景别)..."
            )

            # ── Generate character design sheet images (single call each, no face closeup) ──
            outfits_processed = 0
            for oi, outfit in enumerate(outfits):
                tag_label = outfit.get("tag", "默认")
                label = f"角色设定图 [{tag_label}] {oi+1}/{len(outfits)}"
                print(f"    [{label}]")
                prompt = outfit.get("prompt", "")
                if not prompt:
                    continue
                try:
                    result = self.browser.generate_image(
                        prompt=normalize_prompt_terms(prompt), aspect_ratio="16:9",
                    )
                    if result.success and result.file_paths:
                        chosen = result.file_paths[0]
                        if len(result.file_paths) > 1:
                            chosen = user_select_candidate(
                                result.file_paths, self.interactive,
                                f"📷 角色设定图 #{outfit['id']}",
                            )
                        if chosen:
                            db.update_outfit_image(outfit["id"], chosen)
                            outfits_processed += 1
                            # Delete unchosen
                            for p in result.file_paths:
                                if p != chosen:
                                    try:
                                        Path(p).unlink(missing_ok=True)
                                    except Exception:
                                        pass
                            print(f"    [角色设定图 #{outfit['id']}] ✓ 已保存 {Path(chosen).name}")
                    else:
                        print(f"    [角色设定图 #{outfit['id']}] ✗ 生成失败: {result.error}")
                except Exception as e:
                    db.log(
                        self.agent_name, chapter_id,
                        "outfit_image_error",
                        {"outfit_id": outfit["id"], "error": str(e)},
                        level="WARNING",
                    )
                    print(f"    [角色设定图 #{outfit['id']}] ✗ 异常: {e}")

            # ── Generate scene multi-view images (9:16 portrait for triptych) ──
            scenes_processed = 0
            for si, scene in enumerate(scenes):
                label = f"场景多景别 {si+1}/{len(scenes)}"
                print(f"    [{label}]")
                if self._process_entity(
                    db, chapter_id, scene, "multi_view_prompt",
                    db.update_scene_card_multi_view, "场景",
                    aspect_ratio="9:16",
                ):
                    scenes_processed += 1

            images_generated = outfits_processed + scenes_processed
            had_pending = bool(outfits) or bool(scenes)
            # Check if any entities failed (partial success)
            failed_outfits = len(outfits) - outfits_processed
            failed_scenes = len(scenes) - scenes_processed
            all_succeeded = (failed_outfits == 0 and failed_scenes == 0)

            if images_generated > 0:
                final_status = "done" if all_succeeded else "partial"
                db.set_agent_status(self.agent_name, chapter_id, final_status)
                db.log(self.agent_name, chapter_id,
                       "completed" if all_succeeded else "partial", {
                    "images_generated": images_generated,
                    "outfits_processed": outfits_processed,
                    "scenes_processed": scenes_processed,
                    "failed_outfits": failed_outfits,
                    "failed_scenes": failed_scenes,
                    "status": final_status,
                })
                return AgentResult(success=True, data={
                    "images_generated": images_generated,
                    "outfits_processed": outfits_processed,
                    "scenes_processed": scenes_processed,
                    "failed_outfits": failed_outfits,
                    "failed_scenes": failed_scenes,
                    "status": final_status,
                })
            elif had_pending:
                db.set_agent_status(self.agent_name, chapter_id, "failed")
                err_msg = f"No images from {len(outfits)} outfits + {len(scenes)} scenes"
                db.log(self.agent_name, chapter_id, "completed_all_failed",
                       {"reason": err_msg}, level="ERROR")
                return AgentResult(success=False, error=err_msg)
            else:
                db.set_agent_status(self.agent_name, chapter_id, "done")
                db.log(self.agent_name, chapter_id, "completed_nothing_pending",
                       {"reason": "No pending outfit or scene images"}, level="INFO")
                return AgentResult(success=True, data={"images_generated": 0})

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
