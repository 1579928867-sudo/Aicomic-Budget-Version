"""Image Generator Agent — generates real images for character variants and scenes.

Uses DoubaoBrowserClient to turn view prompts into actual image files,
then saves file paths back to the database.
"""

from __future__ import annotations

from typing import Any, Callable

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

    def _process_views(
        self,
        db: Database,
        chapter_id: int,
        rows: list[dict],
        view_names: list[str],
        update_fn: Callable,
        entity_type: str,
    ) -> tuple[int, int]:
        """Generate images for each view of each entity. Returns (images_generated, entities_processed)."""
        images_count = 0
        entities_processed = 0
        for entity in rows:
            has_generated_any = False
            for view in view_names:
                prompt = entity.get(f"{view}_view", "")
                if not prompt:
                    continue
                try:
                    result = self.browser.generate_image(prompt=prompt, aspect_ratio="16:9")
                    if result.success:
                        update_fn(entity["id"], view, result.file_path)
                        images_count += 1
                        has_generated_any = True
                    else:
                        db.log(
                            self.agent_name, chapter_id,
                            f"{entity_type}_image_failed",
                            {"entity_id": entity["id"], "view": view, "error": result.error},
                            level="WARNING",
                        )
                except Exception as e:
                    db.log(
                        self.agent_name, chapter_id,
                        f"{entity_type}_image_error",
                        {"entity_id": entity["id"], "view": view, "error": str(e)},
                        level="WARNING",
                    )
            if has_generated_any:
                entities_processed += 1
        return images_count, entities_processed

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
            # ── Load variant rows ──
            variant_rows = db.conn.execute(
                """SELECT id, front_view, side_view, back_view
                   FROM appearance_variant
                   WHERE front_view != '' AND front_image = ''
                   ORDER BY id"""
            ).fetchall()
            variants = [dict(r) for r in variant_rows]

            # ── Load scene rows ──
            scene_rows = db.conn.execute(
                """SELECT id, wide_view, mid_view, close_view
                   FROM scene_card
                   WHERE wide_view != '' AND wide_image = ''
                   ORDER BY id"""
            ).fetchall()
            scenes = [dict(r) for r in scene_rows]

            # ── Generate images ──
            v_images, variants_processed = self._process_views(
                db, chapter_id, variants, ["front", "side", "back"],
                db.update_appearance_variant_image, "variant",
            )
            s_images, scenes_processed = self._process_views(
                db, chapter_id, scenes, ["wide", "mid", "close"],
                db.update_scene_card_image, "scene",
            )
            images_generated = v_images + s_images

            # ── Determine result ──
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
                err_msg = f"No images generated from {len(variants)} variants and {len(scenes)} scenes"
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
                       {"reason": "Nothing to generate"}, level="INFO")
                return AgentResult(success=True, data={
                    "images_generated": 0,
                    "variants_processed": 0,
                    "scenes_processed": 0,
                })
        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
