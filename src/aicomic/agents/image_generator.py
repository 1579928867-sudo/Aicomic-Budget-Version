"""Image Generator Agent — generates real images for character variants and scenes.

Uses DoubaoBrowserClient to turn view prompts into actual image files,
then saves file paths back to the database.
"""

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

    def __init__(self, browser_client):
        """Args:
            browser_client: DoubaoBrowserClient instance (shared across agents).
        """
        self.browser = browser_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

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

        images_generated = 0
        variants_processed = 0
        scenes_processed = 0

        try:
            # ── Load character variants with view prompts ──
            variant_rows = db.conn.execute(
                """SELECT id, front_view, side_view, back_view
                   FROM appearance_variant
                   WHERE front_view != '' AND front_image = ''
                   ORDER BY id"""
            ).fetchall()
            variants = [dict(r) for r in variant_rows]

            if variants:
                db.log(
                    self.agent_name, chapter_id, "generating_variant_images",
                    {"variant_count": len(variants)},
                )

            for v in variants:
                any_view = False
                for view in ["front", "side", "back"]:
                    prompt = v.get(f"{view}_view", "")
                    if not prompt:
                        continue

                    try:
                        result = self.browser.generate_image(
                            prompt=prompt, aspect_ratio="16:9"
                        )
                        if result.success:
                            db.update_appearance_variant_image(
                                v["id"], view, result.file_path
                            )
                            images_generated += 1
                            any_view = True
                        else:
                            db.log(
                                self.agent_name, chapter_id,
                                "variant_image_failed",
                                {"variant_id": v["id"], "view": view,
                                 "error": result.error},
                                level="WARNING",
                            )
                    except Exception as e:
                        db.log(
                            self.agent_name, chapter_id,
                            "variant_image_error",
                            {"variant_id": v["id"], "view": view, "error": str(e)},
                            level="WARNING",
                        )

                if any_view:
                    variants_processed += 1

            # ── Load scene cards with view prompts ──
            scene_rows = db.conn.execute(
                """SELECT id, wide_view, mid_view, close_view
                   FROM scene_card
                   WHERE wide_view != '' AND wide_image = ''
                   ORDER BY id"""
            ).fetchall()
            scenes = [dict(r) for r in scene_rows]

            if scenes:
                db.log(
                    self.agent_name, chapter_id, "generating_scene_images",
                    {"scene_count": len(scenes)},
                )

            for s in scenes:
                any_view = False
                for view in ["wide", "mid", "close"]:
                    prompt = s.get(f"{view}_view", "")
                    if not prompt:
                        continue

                    try:
                        result = self.browser.generate_image(
                            prompt=prompt, aspect_ratio="16:9"
                        )
                        if result.success:
                            db.update_scene_card_image(
                                s["id"], view, result.file_path
                            )
                            images_generated += 1
                            any_view = True
                        else:
                            db.log(
                                self.agent_name, chapter_id,
                                "scene_image_failed",
                                {"scene_id": s["id"], "view": view,
                                 "error": result.error},
                                level="WARNING",
                            )
                    except Exception as e:
                        db.log(
                            self.agent_name, chapter_id,
                            "scene_image_error",
                            {"scene_id": s["id"], "view": view, "error": str(e)},
                            level="WARNING",
                        )

                if any_view:
                    scenes_processed += 1

            # ── Determine success ──
            attempted_any = bool(variants) or bool(scenes)

            if images_generated > 0:
                db.set_agent_status(self.agent_name, chapter_id, "done")
                db.log(
                    self.agent_name, chapter_id, "completed",
                    {
                        "images_generated": images_generated,
                        "variants_processed": variants_processed,
                        "scenes_processed": scenes_processed,
                    },
                )
                return AgentResult(
                    success=True,
                    data={
                        "images_generated": images_generated,
                        "variants_processed": variants_processed,
                        "scenes_processed": scenes_processed,
                    },
                )
            elif attempted_any:
                # Tried but all failed — report as failure
                db.set_agent_status(self.agent_name, chapter_id, "done")
                db.log(
                    self.agent_name, chapter_id, "completed_no_images",
                    {"reason": "No images were generated",
                     "variants_found": len(variants),
                     "scenes_found": len(scenes)},
                    level="WARNING",
                )
                return AgentResult(
                    success=False,
                    error="No images were generated",
                    data={
                        "images_generated": 0,
                        "variants_processed": 0,
                        "scenes_processed": 0,
                    },
                )
            else:
                # Nothing to generate — still a success
                db.set_agent_status(self.agent_name, chapter_id, "done")
                db.log(
                    self.agent_name, chapter_id, "completed_no_images",
                    {"reason": "No pending variants or scenes to generate"},
                )
                return AgentResult(
                    success=True,
                    data={
                        "images_generated": 0,
                        "variants_processed": 0,
                        "scenes_processed": 0,
                    },
                )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(
                self.agent_name, chapter_id, "failed",
                {"error": str(e)}, level="ERROR",
            )
            return AgentResult(success=False, error=str(e))
