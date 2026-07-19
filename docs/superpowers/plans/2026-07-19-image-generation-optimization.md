# Image Generation Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce image generation polling from N×3 to N×1 by merging three views into one composite prompt; leverage Doubao's 4-image return with CLI interactive selection.

**Architecture:** Incremental expansion — add `three_view_prompt`/`three_view_image` and `multi_view_prompt`/`multi_view_image` columns alongside existing single-view columns. Old columns remain untouched. Browser client returns all 4 downloaded paths. Image generator runs one prompt per entity, presents 4 candidates to user, keeps selected one, deletes rest.

**Tech Stack:** Python 3.12+, SQLite, Playwright, requests

**Spec:** `docs/superpowers/specs/2026-07-19-image-generation-optimization-design.md`

## Global Constraints

- Old columns (front/side/back_view_prompt, wide/mid/close_view_prompt and their _image columns) **must remain untouched** — used by shot_visualizer later.
- `ImageResult.file_path` must still work for backward compatibility.
- Use `os.startfile()` on Windows, `subprocess.run(["open"])` on macOS, `subprocess.run(["xdg-open"])` on Linux for image viewer.
- Rate limiting (10s between calls) still applies via existing `_wait_rate_limit()`.

---

## Task Dependency Graph

```
Task 1 (DB) ─────┐
                  │
Task 2 (Browser) ─┤──→ Task 5 (Image Generator)
                  │
Task 3 (Char) ────┤
                  │
Task 4 (Scene) ───┘
```

Tasks 1–4 have no mutual dependencies. Task 5 depends on all four.

---

### Task 1: DB Schema + Repository Methods

**Files:**
- Modify: `src/aicomic/db/repository.py`

**Interfaces:**
- Produces:
  - `Database.update_appearance_variant_three_view_prompt(self, variant_id: int, prompt: str) -> None`
  - `Database.update_scene_card_multi_view_prompt(self, scene_id: int, prompt: str) -> None`
  - `Database.update_appearance_variant_three_view(self, variant_id: int, file_path: str) -> None`
  - `Database.update_scene_card_multi_view(self, scene_id: int, file_path: str) -> None`

- [ ] **Step 1: Add migration statements to `migrate_schema()`**

In `repository.py`, inside `migrate_schema()` find the `migrations` list. Append four entries before the closing `]`:

```python
        # v0.7: add three-view / multi-view prompt and image columns
        "ALTER TABLE appearance_variant ADD COLUMN three_view_prompt TEXT DEFAULT ''",
        "ALTER TABLE appearance_variant ADD COLUMN three_view_image TEXT DEFAULT ''",
        "ALTER TABLE scene_card ADD COLUMN multi_view_prompt TEXT DEFAULT ''",
        "ALTER TABLE scene_card ADD COLUMN multi_view_image TEXT DEFAULT ''",
```

- [ ] **Step 2: Add `update_appearance_variant_three_view_prompt`**

Insert after `update_appearance_variant_views` (after line ~389):

```python
    def update_appearance_variant_three_view_prompt(
        self, variant_id: int, prompt: str
    ):
        """Update three_view_prompt column on an appearance_variant."""
        self.conn.execute(
            "UPDATE appearance_variant SET three_view_prompt = ? WHERE id = ?",
            (prompt, variant_id),
        )
        self.conn.commit()
```

- [ ] **Step 3: Add `update_scene_card_multi_view_prompt`**

Insert after `update_scene_card` (after line ~340):

```python
    def update_scene_card_multi_view_prompt(self, scene_id: int, prompt: str):
        """Update multi_view_prompt column on a scene_card."""
        self.conn.execute(
            "UPDATE scene_card SET multi_view_prompt = ? WHERE id = ?",
            (prompt, scene_id),
        )
        self.conn.commit()
```

- [ ] **Step 4: Add `update_appearance_variant_three_view`**

Insert after `update_appearance_variant_image` (after line ~405):

```python
    def update_appearance_variant_three_view(
        self, variant_id: int, file_path: str
    ):
        """Update three_view_image column on an appearance_variant."""
        self.conn.execute(
            "UPDATE appearance_variant SET three_view_image = ? WHERE id = ?",
            (file_path, variant_id),
        )
        self.conn.commit()
```

- [ ] **Step 5: Add `update_scene_card_multi_view`**

Insert after `update_scene_card_image` (after line ~421):

```python
    def update_scene_card_multi_view(self, scene_id: int, file_path: str):
        """Update multi_view_image column on a scene_card."""
        self.conn.execute(
            "UPDATE scene_card SET multi_view_image = ? WHERE id = ?",
            (file_path, scene_id),
        )
        self.conn.commit()
```

- [ ] **Step 6: Verify migration is idempotent**

```bash
python -c "from src.aicomic.db.repository import Database; from pathlib import Path; db = Database(Path('data/aicomic.db')); db.connect(); db.migrate_schema(); print('OK')"
```

Expected: `OK` (no errors on rerun)

- [ ] **Step 7: Commit**

```bash
git add src/aicomic/db/repository.py
git commit -m "feat(db): add three_view / multi_view columns and update methods"
```

---

### Task 2: Browser Client — Return All Downloaded Images

**Files:**
- Modify: `src/aicomic/doubao/browser.py`

**Interfaces:**
- Produces: `ImageResult.file_paths: list[str]` — new field populated by `generate_image()`

- [ ] **Step 1: Add `file_paths` field to `ImageResult` dataclass**

Find `ImageResult` dataclass (~line 14). Change the fields to:

```python
@dataclass
class ImageResult:
    """Result from an image generation call.

    Attributes:
        success: Whether generation succeeded.
        file_path: Local path to the first downloaded image (backward compat).
        file_paths: All successfully downloaded image paths.
        url: Original URL the image was downloaded from.
        metadata: Arbitrary metadata (width, height, aspect_ratio, etc.).
        error: Error message if success is False.
    """

    success: bool
    file_path: str
    file_paths: list[str] = field(default_factory=list)
    url: str = ""
    metadata: dict = field(default_factory=dict)
    error: str | None = None
```

**Critical:** Use `field(default_factory=list)`, not `= []`. Mutable defaults are shared across instances.

- [ ] **Step 2: Change download loop in `generate_image()` to collect all paths**

Find the block (~lines 374-391) where `first_path` is collected from the grid loop. Replace from `first_path = None` through the final `return ImageResult(...)`:

```python
                downloaded = []
                for i, gimg in enumerate(grid):
                    result_path = self._download_grid_image(
                        page, gimg, img_dir
                    )
                    if result_path:
                        downloaded.append(result_path)

                if downloaded:
                    return ImageResult(
                        success=True,
                        file_path=downloaded[0],
                        file_paths=downloaded,
                        metadata={"generator": "doubao", "image_id": img_id,
                                   "total_downloaded": len(downloaded)},
                    )
                return ImageResult(
                    success=False, file_path="",
                    error="Failed to download any image from grid",
                )
```

- [ ] **Step 3: Verify syntax and backward compat**

```bash
python -c "from src.aicomic.doubao.browser import ImageResult; r = ImageResult(success=True, file_path='a.png', file_paths=['a.png','b.png']); print('OK:', r.file_path, r.file_paths)"
```

Expected: `OK: a.png ['a.png', 'b.png']`

Also verify old code still works (no file_paths arg):
```bash
python -c "from src.aicomic.doubao.browser import ImageResult; r = ImageResult(success=False, file_path='', error='test'); print('OK:', r.file_paths)"
```

Expected: `OK: []`

- [ ] **Step 4: Commit**

```bash
git add src/aicomic/doubao/browser.py
git commit -m "feat(browser): ImageResult.file_paths — return all downloaded images"
```

---

### Task 3: Char Designer — three_view_prompt Output

**Files:**
- Modify: `src/aicomic/agents/char_designer.py`

**Interfaces:**
- Produces: `three_view_prompt` string per variant in LLM JSON output + saved to DB via `update_appearance_variant_three_view_prompt`

- [ ] **Step 1: Add format instruction (item 11) to `CHAR_DESIGNER_SYSTEM_PROMPT`**

Find the end of item 10 (text: `All three-view prompts keep the same style prefix...`). Append right after it:

```

	11. **Composite three-view prompt (三视图合并提示词)**: For every variant, generate ONE composite prompt that renders front, side, and back views together in a single image:
	    - `three_view_prompt`: Left-to-right horizontal layout — left = side view (侧面全身站立), center = front view (正面特写全身站立), right = back view (背面全身站立). Same horizontal baseline, evenly spaced. Same style prefix (古代仙侠风格 for ancient, omitted for modern), same era tag (e.g. 【中国古代·仙侠】), pure white background (纯白色背景), 写实电影感风格.
	    - The prompt MUST explicitly describe the layout: "三视图角色设定图，纯白色背景。画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。三视图间距均匀，同一水平线对齐。"
	    - Then append the full character appearance details (same level as full_prompt), describing features visible from all three angles collectively.
	    - "双手自然下垂，手里无任何物品" say once at the end — do NOT repeat per view.
```

- [ ] **Step 2: Add `three_view_prompt` to the example JSON in the system prompt**

Find the example variant's `back_view_prompt` line. Add after it:

```
          "three_view_prompt": "古代仙侠风格，【中国古代·仙侠】萧澈（云澈），男 16岁，写实电影感风格，三视图角色设定图，纯白色背景。画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。三视图间距均匀，同一水平线对齐。黑色长发束髻，白玉发冠；剑眉星目，清秀俊朗面容，肤色白净，气质坚毅淡然；上身白色交领长袍，领口云纹刺绣，袖口收束；下身同色系长衫，腰间墨玉腰带；脚上黑色云纹布靴；配饰左手掌心绿色天毒珠印记；双手自然下垂，手里无任何物品。"
```

- [ ] **Step 3: Update `_build_appearance_json` to include `three_view_prompt`**

In the static method `_build_appearance_json`, add to the `appearance` dict after `"back_view_prompt"`:

```python
            "three_view_prompt": variant.get("three_view_prompt", ""),
```

- [ ] **Step 4: Save `three_view_prompt` to DB in `execute()`**

Find the `db.update_appearance_variant_views(...)` call in `execute()`. Add after it:

```python
                    # v0.7: save three_view_prompt
                    db.update_appearance_variant_three_view_prompt(
                        variant_id=variant_id,
                        prompt=variant.get("three_view_prompt", ""),
                    )
```

- [ ] **Step 5: Verify syntax**

```bash
python -c "from src.aicomic.agents.char_designer import CharacterDesignerAgent, CHAR_DESIGNER_SYSTEM_PROMPT; print('OK:', len(CHAR_DESIGNER_SYSTEM_PROMPT))"
```

Expected: `OK: <number>` (prompt loaded successfully)

- [ ] **Step 6: Commit**

```bash
git add src/aicomic/agents/char_designer.py
git commit -m "feat(char-designer): add three_view_prompt output for composite character views"
```

---

### Task 4: Scene Designer — multi_view_prompt Output

**Files:**
- Modify: `src/aicomic/agents/scene_designer.py`

**Interfaces:**
- Produces: `multi_view_prompt` string per scene in LLM JSON output + saved to DB via `update_scene_card_multi_view_prompt`

- [ ] **Step 1: Add format instruction (item 10) to `SCENE_DESIGNER_SYSTEM_PROMPT`**

Find the end of item 9 (text: `All three-view prompts must follow the same rules...`). Append right after it:

```

	10. **Composite multi-view scene prompt (场景多景别合并提示词)**: For every scene, generate ONE composite prompt that renders all three camera distances together in a single image:
	    - `multi_view_prompt`: Top-to-bottom vertical layout — top = wide/panoramic view (全景广角，展示完整空间关系), middle = mid view (中景，展示核心活动区域), bottom = close-up view (特写，展示材质纹理与关键道具细节). Each section separated clearly.
	    - The prompt MUST explicitly describe the layout: "场景多景别设定图，横向16:9，从上到下排列三个景别：上方为全景广角（展示完整空间关系），中间为中景（展示核心活动区域），下方为特写（展示材质纹理与关键道具细节）。"
	    - Same rules as individual views: "不能出现其他人，无人纯场景，no humans, empty, landscape only", 写实电影感风格, 横向16:9, era style prefix for ancient settings, real environment backgrounds (NOT pure white).
	    - Then append full scene description details.
```

- [ ] **Step 2: Add `multi_view_prompt` to the example JSON in the system prompt**

Find the example scene's `close_view_prompt` line. Add after it:

```
        "multi_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，场景多景别设定图，横向16:9，从上到下排列三个景别：上方为全景广角（展示完整空间关系），中间为中景（展示核心活动区域），下方为特写（展示材质纹理与关键道具细节）。萧澈卧室｜长方形中式古典卧室，深约5米宽约4米，地面深色木质地板，墙面浅米色墙纸，雕花窗棂透入柔和晨光，松软雕花大床垂下红色曼联，床头大红喜字贴窗，喜庆中带着昏沉，暖黄色调。"
```

- [ ] **Step 3: Save `multi_view_prompt` to DB in `execute()`**

Find the `db.update_scene_card(...)` call in `execute()`. Add after it:

```python
                # v0.7: save multi_view_prompt
                db.update_scene_card_multi_view_prompt(
                    scene_id=scene_id,
                    prompt=scene_data.get("multi_view_prompt", ""),
                )
```

- [ ] **Step 4: Verify syntax**

```bash
python -c "from src.aicomic.agents.scene_designer import SceneDesignerAgent, SCENE_DESIGNER_SYSTEM_PROMPT; print('OK:', len(SCENE_DESIGNER_SYSTEM_PROMPT))"
```

Expected: `OK: <number>` (prompt loaded successfully)

- [ ] **Step 5: Commit**

```bash
git add src/aicomic/agents/scene_designer.py
git commit -m "feat(scene-designer): add multi_view_prompt output for composite scene views"
```

---

### Task 5: Image Generator — Core Refactor

**Files:**
- Modify: `src/aicomic/agents/image_generator.py`

**Interfaces:**
- Consumes:
  - `ImageResult.file_paths` (from Task 2)
  - `Database.update_appearance_variant_three_view` (from Task 1)
  - `Database.update_scene_card_multi_view` (from Task 1)
  - `three_view_prompt` column on `appearance_variant` (from Task 3)
  - `multi_view_prompt` column on `scene_card` (from Task 4)
- Produces: Same `AgentResult` shape as before (`images_generated`, `variants_processed`, `scenes_processed`)

- [ ] **Step 1: Add new imports**

Replace the imports section:

```python
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
```

(Remove `Callable` from typing import — no longer needed.)

- [ ] **Step 2: Remove `_process_views` method**

Delete the entire `_process_views` method (lines 39-85).

- [ ] **Step 3: Add `_process_entity` method**

Insert where `_process_views` was:

```python
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
```

- [ ] **Step 4: Add `_user_select_image` method**

Insert after `_process_entity`:

```python
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
            except (ValueError, KeyboardInterrupt):
                print("\n  ✗ 已取消")
                return None
```

- [ ] **Step 5: Rewrite `execute()` method**

Replace the entire `execute()` method:

```python
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
                f"({len(variants)} 角色三视图, {len(scenes)} 场景多景别)..."
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
```

- [ ] **Step 6: Verify syntax and import integrity**

```bash
python -c "from src.aicomic.agents.image_generator import ImageGeneratorAgent; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Run existing tests (should still pass — old behavior for non-three-view rows is no-op)**

```bash
python -m pytest tests/test_image_generator.py -v
```

Expected: existing tests pass (the agent skips when no pending rows exist)

- [ ] **Step 8: Commit**

```bash
git add src/aicomic/agents/image_generator.py
git commit -m "feat(image-generator): composite prompt + CLI interactive selection"
```

---

## Plan Self-Review

1. **Spec coverage:**
   - DB schema (three_view_prompt/image, multi_view_prompt/image) → Task 1 ✓
   - Repository methods → Task 1 ✓
   - ImageResult.file_paths → Task 2 ✓
   - generate_image returns all paths → Task 2 ✓
   - char_designer three_view_prompt → Task 3 ✓
   - scene_designer multi_view_prompt → Task 4 ✓
   - _process_entity replaces _process_views → Task 5 ✓
   - _user_select_image CLI interaction → Task 5 ✓
   - Old columns untouched → verified in all tasks ✓

2. **Placeholder scan:** No TBD, TODO, "add error handling", or vague instructions. All code is concrete. ✓

3. **Type consistency:**
   - `update_appearance_variant_three_view(variant_id: int, file_path: str)` — defined in Task 1, consumed in Task 5 with matching signature ✓
   - `update_scene_card_multi_view(scene_id: int, file_path: str)` — defined in Task 1, consumed in Task 5 with matching signature ✓
   - `update_appearance_variant_three_view_prompt(variant_id: int, prompt: str)` — defined in Task 1, consumed in Task 3 with matching signature ✓
   - `update_scene_card_multi_view_prompt(scene_id: int, prompt: str)` — defined in Task 1, consumed in Task 4 with matching signature ✓
   - `ImageResult.file_paths: list[str]` — defined in Task 2, consumed in Task 5 as `result.file_paths` ✓
   - `_process_entity(entity: dict, prompt_field: str, ...)` — Task 5 passes `"three_view_prompt"` and `"multi_view_prompt"` matching the columns from Tasks 3/4 ✓
