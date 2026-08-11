"""后台任务执行器 — 在 FastAPI BackgroundTasks 中运行 Pipeline/Agent.

支持两种模式:
- auto: 完整跑完，每阶段汇报结果（不等待确认）
- interactive: 分 3 阶段，每阶段完成后暂停等待用户确认继续

每阶段完成后自动审计 DB，汇报已生成/未生成的素材。
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import traceback
from pathlib import Path
from typing import Any

from .events import EventManager
from .db import TaskStore, get_db


class InterruptedError(Exception):
    """任务被用户取消."""


PHASES = [
    {"id": "script_design", "needs_video": False, "needs_images": False, "stop_after": "storyboard-agent",
     "label": "剧本与设计", "desc": "解析小说 → 角色设计 → 场景设计 → 分镜编排", "next": "images",
     "timeout_sec": 600},
    {"id": "images", "needs_video": False, "needs_images": True, "stop_after": "shot-visualizer",
     "label": "图片生成", "desc": "角色图 → 场景图 → 分镜提示词", "next": "video",
     "timeout_sec": 900},
    {"id": "video", "needs_video": True, "needs_images": False, "stop_after": None,
     "label": "视频生成", "desc": "镜头视频 → 合成成品", "next": None,
     "timeout_sec": 1200},
]


class PipelineRunner:
    """在后台运行 Orchestrator.run_chapter(), 支持分阶段执行."""

    def __init__(self, orchestrator, event_mgr: EventManager, task_store: TaskStore,
                 db_path: Path = Path("data/aicomic.db")):
        self.orchestrator = orchestrator
        self.event_mgr = event_mgr
        self.task_store = task_store
        self.db_path = db_path
        self._cancel_flags: dict[str, bool] = {}
        self._phase_states: dict[str, dict] = {}

    async def run_in_background(
        self, chapter_id: int, raw_text: str = "",
        with_images: bool = False, with_video: bool = False,
        task_id: str = "", mode: str = "auto",
    ):
        self._cancel_flags[task_id] = False
        self.task_store.update(task_id, status="running")
        start_phase = "script_design"
        self._phase_states[task_id] = {
            "chapter_id": chapter_id, "raw_text": raw_text,
            "with_images": with_images, "with_video": with_video,
            "mode": mode, "current_phase": start_phase,
        }
        await self._run_from_phase(task_id, start_phase)

    async def _run_from_phase(self, task_id: str, phase_id: str):
        state = self._phase_states.get(task_id)
        if not state: return
        ch = state["chapter_id"]
        raw = state["raw_text"]
        mode = state["mode"]

        # ── Phase completion map: what agents must be "done" for a phase
        #     to be considered complete and auto-skippable ──
        _PHASE_GATE_AGENTS = {
            "images": ["image-generator", "shot-visualizer"],
            "video": ["shot-video-generator"],
        }

        idx = next((i for i, p in enumerate(PHASES) if p["id"] == phase_id), 0)
        last_result = None  # Track for final complete event warnings
        for i in range(idx, len(PHASES)):
            if self._cancel_flags.get(task_id): await self._fail(task_id, "取消"); return
            p = PHASES[i]
            state["current_phase"] = p["id"]

            # ── Skip inapplicable phases ──
            if p["needs_video"] and not state["with_video"]:
                # Video phase not applicable → skip silently
                continue
            if p["needs_images"] and not state["with_images"]:
                continue

            # ── Smart skip: DISABLED ──
            skip_phase = False

            # ── 视频阶段入口预检：所有分镜的参考图必须就位 ──
            if p["needs_video"]:
                preflight_ok, preflight_missing = self._preflight_video_check(ch)
                if not preflight_ok:
                    audit = self._audit(ch, p["id"])
                    missing_str = "\n".join(f"  • {m}" for m in preflight_missing)
                    full_msg = (
                        f"⚠ 视频生成入口检查：{len(preflight_missing)} 项素材缺失，"
                        f"请重新运行「图片生成」阶段补全。\n{missing_str}"
                    )
                    await self.event_mgr.emit(task_id, "phase_rejected", {
                        "phase": p["id"], "label": p["label"],
                        "reason": "assets_missing",
                        "missing": preflight_missing,
                        "missing_count": len(preflight_missing),
                        "audit": audit,
                        "message": full_msg,
                    })
                    if mode == "interactive":
                        self.task_store.update(task_id, status="failed",
                            error=f"视频阶段入口检查失败：{len(preflight_missing)} 项素材缺失",
                            result=json.dumps({
                                "phase": p["id"], "reason": "assets_missing",
                                "missing": preflight_missing,
                                "message": full_msg,
                            }))
                    else:
                        await self._fail(task_id, full_msg)
                    self._phase_states.pop(task_id, None)
                    self._cancel_flags.pop(task_id, None)
                    return

            # ── 预估耗时 ──
            est = self._estimate_time(ch, p["id"])

            await self.event_mgr.emit(task_id, "phase_start", {
                "phase": p["id"], "label": p["label"], "description": p["desc"],
                "mode": mode, "estimate": est,
            })

            try:
                from concurrent.futures import ThreadPoolExecutor
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            pool,
                            lambda: self.orchestrator.run_chapter(
                                ch, raw,
                                with_video=state["with_video"] and (p["id"] == "video"),
                                with_images=state["with_images"] and (p["id"] in ("images", "video")),
                                stop_after=p["stop_after"],
                                max_video_clips=0 if mode == "auto" else 3,
                            ),
                        ),
                        timeout=p.get("timeout_sec", 600),
                    )
                if not result.success:
                    await self._fail(task_id, result.error or "error"); return

                last_result = result
                audit = self._audit(ch, p["id"])
                # Surface partial warnings from orchestrator result data
                rd = result.data or {}
                phase_warning = rd.get("video_warning", "")

                # ── 视频额度检查点 ──
                if rd.get("budget_paused"):
                    budget_msg = rd.get("budget_message", "")
                    await self.event_mgr.emit(task_id, "budget_checkpoint", {
                        "phase": p["id"], "label": p["label"], "mode": mode,
                        "summary": audit["summary"], "audit": audit,
                        "clips_done": rd.get("clips_created", 0),
                        "clips_total": rd.get("clips_created", 0) + rd.get("budget_remaining", 0),
                        "remaining": rd.get("budget_remaining", 0),
                        "budget_per_run": rd.get("budget_per_run", 3),
                        "message": budget_msg,
                    })
                    if mode == "auto":
                        # Auto mode — 不暂停，立即继续下一批次
                        self.task_store.update(task_id, status="running")
                        state["last_audit"] = audit
                        continue
                    else:
                        # Interactive mode — 暂停等用户确认
                        self.task_store.update(task_id, status="awaiting_continue",
                            params=json.dumps({
                                "phase": p["id"],
                                "next_phase": p["id"],
                                "budget_checkpoint": True,
                            }))
                        state["last_audit"] = audit
                        return

                await self.event_mgr.emit(task_id, "phase_complete", {
                    "phase": p["id"], "label": p["label"], "mode": mode,
                    "summary": audit["summary"], "audit": audit,
                    "has_next": p["next"] is not None, "next_phase": p["next"],
                    "warning": phase_warning,
                    "clips_failed": rd.get("clips_failed", 0),
                    "failed_shot_nums": rd.get("failed_shot_nums", []),
                })

                if mode == "interactive" and p["next"]:
                    self.task_store.update(task_id, status="awaiting_continue",
                        params=json.dumps({"phase": p["id"], "next_phase": p["next"]}))
                    state["last_audit"] = audit
                    return
            except asyncio.TimeoutError:
                phase_label = p.get("label", p["id"])
                timeout_mins = p.get("timeout_sec", 600) // 60
                await self._fail(task_id,
                    f"{phase_label}阶段执行超时（{timeout_mins}分钟）。"
                    f"请检查 DeepSeek API 是否正常响应，或减少章节篇幅后重试。"
                )
                return
            except (KeyboardInterrupt, SystemExit): raise
            except Exception as e:
                await self._fail(task_id, str(e)); return

        # Done
        audit = self._audit(ch, "all")
        final_warning = (last_result.data or {}).get("video_warning", "") if last_result else ""
        self.task_store.update(task_id, status="done", progress=1.0,
            result=json.dumps({"pipeline": "complete", "audit": audit, "warning": final_warning}))
        await self.event_mgr.emit(task_id, "complete", {
            "status": "done", "audit": audit,
            "warning": final_warning,
            "clips_failed": (last_result.data or {}).get("clips_failed", 0) if last_result else 0,
            "failed_shot_nums": (last_result.data or {}).get("failed_shot_nums", []) if last_result else [],
        })
        self._phase_states.pop(task_id, None)
        self._cancel_flags.pop(task_id, None)

    def _get_agent_status(self, chapter_id: int, agent_name: str) -> str | None:
        """Read agent status from task_log table (mirrors Repository.get_agent_status)."""
        import json
        db = get_db(self.db_path)
        try:
            row = db.execute(
                """SELECT detail FROM task_log
                   WHERE agent_name = ? AND chapter_id = ? AND event = 'status'
                   ORDER BY id DESC LIMIT 1""",
                (agent_name, chapter_id),
            ).fetchone()
            if row:
                detail = json.loads(row["detail"])
                return detail.get("status")
            return None
        finally:
            db.close()

    def _estimate_time(self, chapter_id: int, phase_id: str) -> dict:
        """预估各阶段耗时."""
        db = get_db(self.db_path)
        # Shot count
        shots = db.execute("""SELECT COUNT(*) as c FROM storyboard_shot ss
            JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""",
            (chapter_id,)).fetchone()
        shot_count = shots["c"] if shots else 0
        db.close()

        if phase_id == "script_design":
            return {"text": "约 1-2 分钟", "minutes": 2}
        elif phase_id == "images":
            return {"text": f"约 2-5 分钟（{shot_count} 个镜头 + 角色场景图）", "minutes": 5}
        elif phase_id == "video":
            mins = max(shot_count * 3, 3)
            return {"text": f"约 {mins} 分钟（{shot_count} 个镜头 × 3分钟/镜头）", "minutes": mins, "shot_count": shot_count,
                    "detail": f"每个分镜视频生成约需 3-5 分钟，共 {shot_count} 个分镜"}
        return {"text": "未知", "minutes": 1}

    async def continue_phase(self, task_id: str):
        state = self._phase_states.get(task_id)
        if not state: await self._fail(task_id, "No state"); return
        if state["mode"] != "interactive": await self._fail(task_id, "Not interactive"); return

        # ── 检测额度检查点：继续当前阶段，不跳进下一阶段 ──
        task = self.task_store.get(task_id)
        if task:
            try:
                params = json.loads(task.get("params", "{}"))
            except (json.JSONDecodeError, TypeError):
                params = {}
            if params.get("budget_checkpoint"):
                self.task_store.update(task_id, status="running")
                await self._run_from_phase(task_id, state.get("current_phase", ""))
                return

        cur = state.get("current_phase", "")
        nxt = None
        for i, p in enumerate(PHASES):
            if p["id"] == cur and i + 1 < len(PHASES): nxt = PHASES[i + 1]["id"]; break
        if not nxt: await self._fail(task_id, "At final phase"); return
        self.task_store.update(task_id, status="running")
        await self._run_from_phase(task_id, nxt)

    async def _fail(self, task_id: str, error: str):
        from .error_i18n import translate_error
        friendly = translate_error(error)
        self.task_store.update(task_id, status="failed", error=error)  # 存技术原文
        await self.event_mgr.emit(task_id, "error", {
            "status": "failed",
            "error": friendly,           # 用户看到友好翻译
            "error_raw": error,           # 前端可折叠的技术原文
        })
        self._phase_states.pop(task_id, None)
        self._cancel_flags.pop(task_id, None)

    def cancel(self, task_id: str):
        self._cancel_flags[task_id] = True

    # ── 自检审计 ──

    def _preflight_video_check(self, chapter_id: int) -> tuple[bool, list[str]]:
        """逐镜头检查视频生成所需的参考图是否全部就位。

        检查项:
        - 每个分镜的场景多景别图 (scene_card.multi_view_image) 是否在磁盘上
        - 每个分镜的角色设定图 (character_outfit.image_path) 是否在磁盘上

        Returns:
            (ok, missing_items) — ok=True 表示所有素材到位可以安全进入视频阶段。
            missing_items 是人类可读的缺失项列表，如 ["镜头3: 场景「婚房」缺少多景别图", ...]
        """
        import json
        import os as _os
        missing: list[str] = []
        conn = get_db(self.db_path)

        try:
            # ── 取本章所有分镜 ──
            shots = conn.execute("""
                SELECT ss.id, ss.shot_num, ss.char_ids, ss.scene_id,
                       sc.name AS scene_name, sc.multi_view_image
                FROM storyboard_shot ss
                JOIN script s ON s.id = ss.script_id
                LEFT JOIN scene_card sc ON sc.id = ss.scene_id
                WHERE s.chapter_id = ?
                ORDER BY ss.shot_num
            """, (chapter_id,)).fetchall()

            if not shots:
                return False, ["尚未生成分镜 — 请先运行「剧本与设计」阶段"]

            for shot in shots:
                shot_id = shot["id"]
                shot_num = shot["shot_num"]
                scene_name = shot["scene_name"] or f"场景#{shot['scene_id']}"

                # ── 1. 场景图 ──
                scene_img = shot["multi_view_image"]
                if not scene_img or not _os.path.exists(scene_img):
                    missing.append(f"镜头{shot_num}: 场景「{scene_name}」缺少多景别参考图")

                # ── 2. 角色设定图 — 从 shot_character_outfit 联结表取 ──
                outfit_rows = conn.execute("""
                    SELECT cc.name, co.image_path, COALESCE(co.tag, '默认') AS tag
                    FROM shot_character_outfit sco
                    JOIN character_card cc ON cc.id = sco.character_id
                    LEFT JOIN character_outfit co ON co.character_id = sco.character_id
                        AND co.tag = COALESCE(sco.outfit_tag, '默认')
                    WHERE sco.shot_id = ?
                """, (shot_id,)).fetchall()

                # Fallback: char_ids JSON (旧数据兼容)
                if not outfit_rows:
                    try:
                        char_ids = json.loads(shot["char_ids"] or "[]")
                    except (json.JSONDecodeError, TypeError):
                        char_ids = []
                    for cid in char_ids:
                        row = conn.execute("""
                            SELECT cc.name, co.image_path, COALESCE(co.tag, '默认') AS tag
                            FROM character_card cc
                            LEFT JOIN character_outfit co ON co.character_id = cc.id
                            WHERE cc.id = ?
                            ORDER BY co.id DESC LIMIT 1
                        """, (cid,)).fetchone()
                        if row:
                            outfit_rows.append(row)

                for orow in outfit_rows:
                    char_name = orow["name"]
                    img_path = orow["image_path"]
                    tag = orow["tag"] or "默认"
                    if not img_path or not _os.path.exists(img_path):
                        missing.append(
                            f"镜头{shot_num}: 角色「{char_name}」缺少 {tag} 设定图"
                        )

            return (len(missing) == 0, missing)

        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _audit(self, chapter_id: int, phase_id: str) -> dict:
        import os, json
        db = get_db(self.db_path)
        a: dict[str, Any] = {"phase": phase_id, "summary": {}}

        # ── 获取本章节专属的角色和场景 ID ──
        char_ids = self._chapter_char_ids(db, chapter_id)
        scene_ids = self._chapter_scene_ids(db, chapter_id)

        # Script
        a["script"] = bool(db.execute(
            "SELECT id FROM script WHERE chapter_id = ?", (chapter_id,)).fetchone())

        # Characters — count by unique char_ids (junction first, char_ids fallback)
        if char_ids:
            placeholders = ",".join("?" * len(char_ids))
            # For each char_id in this chapter, check if ANY outfit has an existing image file
            rows = db.execute(
                f"""SELECT cc.id, cc.name, MAX(CASE WHEN co.image_path != '' THEN 1 ELSE 0 END) as has_image
                    FROM character_card cc
                    LEFT JOIN character_outfit co ON co.character_id = cc.id
                    WHERE cc.id IN ({placeholders})
                    GROUP BY cc.id
                    ORDER BY cc.name""",
                tuple(char_ids),
            ).fetchall()
            done_names = []
            pending_names = []
            import os as _os
            for r in rows:
                if r["has_image"]:
                    # Verify file actually exists on disk
                    img_row = db.execute(
                        "SELECT image_path FROM character_outfit WHERE character_id=? AND image_path!='' LIMIT 1",
                        (r["id"],),
                    ).fetchone()
                    if img_row and _os.path.exists(img_row["image_path"]):
                        done_names.append(r["name"])
                    else:
                        pending_names.append(r["name"])
                else:
                    pending_names.append(r["name"])
            a["characters"] = {
                "total": len(rows), "done": len(done_names), "pending": len(pending_names),
                "done_names": done_names, "pending_names": pending_names,
            }
        else:
            a["characters"] = {"total": 0, "done": 0, "pending": 0, "done_names": [], "pending_names": []}

        # Scenes — only those appearing in this chapter's shots, deduped
        if scene_ids:
            placeholders = ",".join("?" * len(scene_ids))
            srows = db.execute(
                f"""SELECT DISTINCT id, name, multi_view_image, multi_view_prompt
                    FROM scene_card WHERE id IN ({placeholders})"""
                + ("" if phase_id == "script_design" else " AND multi_view_prompt!=''"),
                tuple(scene_ids),
            ).fetchall()
        else:
            srows = []
        a["scenes"] = self._count_done(srows, "multi_view_image", "name")

        # Shots
        a["shots"] = db.execute("""SELECT COUNT(*) as c FROM storyboard_shot ss
            JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""",
            (chapter_id,)).fetchone()["c"]

        # Video clips
        a["video_clips"] = db.execute("""SELECT COUNT(*) as c FROM video_clip vc
            JOIN storyboard_shot ss ON ss.id=vc.shot_id
            JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""",
            (chapter_id,)).fetchone()["c"]

        # Final video
        fv = db.execute("SELECT file_path, file_size FROM final_video WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
                        (chapter_id,)).fetchone()
        a["final_video"] = bool(fv and fv["file_size"] > 0)

        # Build summary
        s = a["summary"]
        s["剧本"] = "✓" if a["script"] else "✗"
        s["角色图"] = f"{a['characters']['done']}/{a['characters']['total']}"
        s["场景图"] = f"{a['scenes']['done']}/{a['scenes']['total']}"
        s["分镜"] = a["shots"]
        if phase_id in ("video", "all"):
            s["视频片段"] = a["video_clips"]
            s["成品视频"] = "✓" if a["final_video"] else "✗"

        # Pending detail
        if a["characters"].get("pending_names"):
            a["characters_pending"] = a["characters"]["pending_names"]
        if a["scenes"].get("pending_names"):
            a["scenes_pending"] = a["scenes"]["pending_names"]

        db.close()
        return a

    @staticmethod
    def _chapter_char_ids(db, chapter_id: int) -> set[int]:
        """Get character IDs appearing in this chapter's shots."""
        # Primary: junction table
        rows = db.execute("""SELECT DISTINCT sco.character_id FROM shot_character_outfit sco
            JOIN storyboard_shot ss ON ss.id=sco.shot_id
            JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""",
            (chapter_id,)).fetchall()
        if rows: return {r[0] for r in rows}
        # Fallback: char_ids JSON column
        import json
        ids = set()
        rows = db.execute("""SELECT ss.char_ids FROM storyboard_shot ss
            JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""",
            (chapter_id,)).fetchall()
        for r in rows:
            try:
                for cid in json.loads(r[0] or "[]"):
                    if isinstance(cid, int): ids.add(cid)
            except: pass
        return ids

    @staticmethod
    def _chapter_scene_ids(db, chapter_id: int) -> set[int]:
        """Get scene IDs appearing in this chapter's shots."""
        rows = db.execute("""SELECT DISTINCT ss.scene_id FROM storyboard_shot ss
            JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""",
            (chapter_id,)).fetchall()
        return {r[0] for r in rows if r[0]}

    @staticmethod
    def _count_done(rows: list, img_col: str, name_col: str) -> dict:
        import os
        done, pending = [], []
        for r in rows:
            fn = r[img_col] if isinstance(r, dict) else (r[img_col] if hasattr(r, "keys") else None)
            nm = r[name_col] if isinstance(r, dict) else (r[name_col] if hasattr(r, "keys") else "?")
            if fn and os.path.exists(fn): done.append(nm)
            else: pending.append(nm)
        return {"total": len(rows), "done": len(done), "pending": len(pending),
                "done_names": list(set(done)), "pending_names": list(set(pending))}


class AgentRunner:
    """在后台运行单个 Agent (用于素材库的"重新生成"按钮)."""

    def __init__(self, bus, event_mgr: EventManager, task_store: TaskStore):
        self.bus = bus; self.event_mgr = event_mgr; self.task_store = task_store

    async def run_in_background(self, agent_name: str, input_data: dict, task_id: str):
        self.task_store.update(task_id, status="running")
        await self.event_mgr.emit(task_id, "progress", {
            "step": agent_name, "status": "running", "pct": 0, "message": f"Running {agent_name}...",
        })
        try:
            from concurrent.futures import ThreadPoolExecutor
            from src.aicomic.db.repository import Database as AICDB
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                db = AICDB(Path("data/aicomic.db"))
                db.connect()
                try:
                    result = await loop.run_in_executor(pool, lambda: self.bus.run(agent_name, input_data, db))
                finally:
                    db.close()
            if result.success:
                # Check for skipped (idempotent) — not really a success for the user
                rd = result.data or {}
                if rd.get("status") == "skipped":
                    self.task_store.update(task_id, status="done", progress=1.0,
                        result=json.dumps({"status": "skipped", "reason": "already done"}))
                    await self.event_mgr.emit(task_id, "complete", {
                        "status": "done", "skipped": True,
                        "message": f"⏭ {agent_name} 已完成（无需重复运行）",
                    })
                else:
                    final_path = rd.get("final_video_path", "")
                    clip_count = rd.get("clip_count", 0)
                    msg = f"✅ {agent_name} 合成完成！"
                    if final_path:
                        msg += f"\n📦 成品: {final_path}"
                    if clip_count:
                        msg += f"\n🎞️ 合并 {clip_count} 个片段"
                    self.task_store.update(task_id, status="done", progress=1.0,
                        result=json.dumps(rd))
                    await self.event_mgr.emit(task_id, "complete", {
                        "status": "done", "data": rd,
                        "message": msg,
                    })
            else:
                raw = result.error or "unknown"
                from .error_i18n import translate_error
                friendly = translate_error(raw)
                self.task_store.update(task_id, status="failed", error=raw)
                await self.event_mgr.emit(task_id, "error", {
                    "status": "failed",
                    "error": friendly,
                    "error_raw": raw,
                })
        except Exception as e:
            raw = str(e)
            from .error_i18n import translate_error
            friendly = translate_error(raw)
            self.task_store.update(task_id, status="failed", error=raw)
            await self.event_mgr.emit(task_id, "error", {
                "status": "failed",
                "error": friendly,
                "error_raw": raw,
            })
