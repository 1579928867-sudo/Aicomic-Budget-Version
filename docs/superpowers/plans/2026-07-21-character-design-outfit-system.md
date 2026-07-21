# Character Design + Outfit System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the variant-based character design system with single design-sheet images + tag-based outfit anchoring, simplifying the pipeline from two-stage image generation to single-call.

**Architecture:** CharDesigner outputs one `design_prompt` per character (using user-tested Xianxia design-sheet template). ImageGenerator simplifies to single-call. New OutfitManager agent detects long-term outfit changes at scene transitions with keyword pre-filtering, triggering new design-sheet generation on demand. ShotVideoGenerator references a single design image instead of face-closeup + three-view. Old `appearance_variant` table is deprecated but kept for backward compat.

**Tech Stack:** Python 3.12, SQLite WAL, DeepSeek V3 (LLM), Playwright (Doubao browser automation)

## Global Constraints

- All DB writes use existing `Database` class patterns (parameterized queries, `self.conn.commit()`)
- Agents follow `AgentInterface` (`validate_input` + `execute` returning `AgentResult`)
- Agent registration via `AgentBus.register()` in `main.py`
- LLM calls use `self.llm.generate_json(system_prompt, user_prompt)`
- Image generation uses `self.browser.generate_image(prompt)` returning `ImageResult`
- Idempotency pattern: `get_agent_status()` → skip if "done", else mark "running" → execute → mark "done"/"failed"
- The old `appearance_variant` table is NOT dropped — just no longer written to

---

### Task 1: Database schema — character_outfit table + outfit_tag column

**Files:**
- Modify: `src/aicomic/db/repository.py:36-101` (init_schema: add CREATE TABLE)
- Modify: `src/aicomic/db/repository.py:143-175` (migrate_schema: add migration)

**Interfaces:**
- Produces: `character_outfit` table with columns `id, character_id, tag, prompt, image_path, is_default, activation_condition, created_at`
- Produces: `storyboard_shot.outfit_tag` column (TEXT DEFAULT NULL)

- [ ] **Step 1: Add `character_outfit` CREATE TABLE to `init_schema()`**

In `Database.init_schema()`, add after the `appearance_variant` block and before `scene_card`:

```python
CREATE TABLE IF NOT EXISTS character_outfit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES character_card(id),
    tag TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    image_path TEXT DEFAULT '',
    is_default INTEGER DEFAULT 0,
    activation_condition TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(character_id, tag)
);
```

- [ ] **Step 2: Add migration for `outfit_tag` on `storyboard_shot`**

In `Database.migrate_schema()`, append to the `migrations` list:

```python
# v0.9: outfit_tag for character outfit system
"ALTER TABLE storyboard_shot ADD COLUMN outfit_tag TEXT DEFAULT NULL",
# v0.9: character_outfit table (IF NOT EXISTS handled by init_schema)
"CREATE TABLE IF NOT EXISTS character_outfit ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "character_id INTEGER NOT NULL REFERENCES character_card(id),"
    "tag TEXT NOT NULL,"
    "prompt TEXT NOT NULL DEFAULT '',"
    "image_path TEXT DEFAULT '',"
    "is_default INTEGER DEFAULT 0,"
    "activation_condition TEXT DEFAULT '',"
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "UNIQUE(character_id, tag)"
")",
```

Note: SQLite `CREATE TABLE IF NOT EXISTS` in migration won't fail even if `init_schema()` already ran. Split the long string across list items using tuple joining to avoid multi-line f-string issues.

- [ ] **Step 3: Verify schema**

Run a quick Python check:

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
from pathlib import Path
import sys; sys.path.insert(0, 'src')
from aicomic.db.repository import Database
db = Database(Path('data/aicomic.db'))
db.connect()
db.init_schema()
db.migrate_schema()
# Check tables exist
tables = db.conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print([t['name'] for t in tables])
# Check outfit_tag column
cols = [c['name'] for c in db.conn.execute('PRAGMA table_info(storyboard_shot)')]
print('outfit_tag' in cols)
db.close()
"
```

Expected: `'character_outfit'` in table list, `outfit_tag` column present → `True`

- [ ] **Step 4: Commit**

```bash
git add src/aicomic/db/repository.py
git commit -m "feat(db): add character_outfit table + outfit_tag column for v0.9 outfit system"
```

---

### Task 2: Database repo methods for character_outfit

**Files:**
- Modify: `src/aicomic/db/repository.py` — add new methods after line 484 (after `set_character_default_look`)

**Interfaces:**
- Consumes: `character_outfit` table (Task 1)
- Produces: `create_character_outfit()`, `get_character_outfit()`, `get_character_outfits()`, `update_outfit_image()`, `update_shot_outfit_tag()`

- [ ] **Step 1: Add repo methods**

Add the following block after the `set_character_default_look` method (after line 483) and before `# ── Agent Status`:

```python
    # ── Character Outfits (v0.9) ──

    def create_character_outfit(
        self,
        character_id: int,
        tag: str,
        prompt: str = "",
        image_path: str = "",
        is_default: int = 0,
        activation_condition: str = "",
    ) -> int:
        """Create or replace a character_outfit row. Returns the outfit id."""
        cursor = self.conn.execute(
            """INSERT INTO character_outfit
               (character_id, tag, prompt, image_path, is_default, activation_condition)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(character_id, tag) DO UPDATE SET
               prompt = excluded.prompt,
               image_path = excluded.image_path,
               is_default = excluded.is_default,
               activation_condition = excluded.activation_condition""",
            (character_id, tag, prompt, image_path, is_default, activation_condition),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_character_outfit(
        self, character_id: int, tag: str | None = None
    ) -> dict | None:
        """Get outfit for a character. If tag is None, returns the default (is_default=1)."""
        if tag:
            row = self.conn.execute(
                """SELECT * FROM character_outfit
                   WHERE character_id = ? AND tag = ? LIMIT 1""",
                (character_id, tag),
            ).fetchone()
        else:
            row = self.conn.execute(
                """SELECT * FROM character_outfit
                   WHERE character_id = ? AND is_default = 1 LIMIT 1""",
                (character_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_character_outfits(self, character_id: int) -> list[dict]:
        """Get all outfits for a character, default first."""
        rows = self.conn.execute(
            """SELECT * FROM character_outfit
               WHERE character_id = ? ORDER BY is_default DESC, id""",
            (character_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_outfit_image(self, outfit_id: int, image_path: str):
        """Update image_path on a character_outfit."""
        self.conn.execute(
            "UPDATE character_outfit SET image_path = ? WHERE id = ?",
            (image_path, outfit_id),
        )
        self.conn.commit()

    def update_shot_outfit_tag(self, shot_id: int, outfit_tag: str | None):
        """Update outfit_tag on a storyboard_shot."""
        self.conn.execute(
            "UPDATE storyboard_shot SET outfit_tag = ? WHERE id = ?",
            (outfit_tag, shot_id),
        )
        self.conn.commit()
```

- [ ] **Step 2: Verify repo methods**

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
from pathlib import Path
import sys; sys.path.insert(0, 'src')
from aicomic.db.repository import Database
db = Database(Path('data/aicomic.db'))
db.connect()
db.init_schema(); db.migrate_schema()
# Test create
cid, _ = db.get_or_create_character('测试角色')
oid = db.create_character_outfit(cid, '默认', 'test prompt', '', 1, '')
print(f'Created outfit id={oid}')
# Test get
o = db.get_character_outfit(cid)
print(f'Default outfit: {o[\"tag\"]}')
o2 = db.get_character_outfit(cid, '默认')
print(f'By tag: {o2[\"tag\"]}')
# Test list
all_o = db.get_character_outfits(cid)
print(f'All outfits: {len(all_o)}')
# Test update
db.update_outfit_image(oid, 'test.png')
o3 = db.get_character_outfit(cid)
print(f'Image path: {o3[\"image_path\"]}')
# Clean up
db.conn.execute('DELETE FROM character_outfit WHERE id = ?', (oid,))
db.conn.execute('DELETE FROM character_card WHERE id = ?', (cid,))
db.conn.commit()
db.close()
print('All tests passed')
"
```

Expected: All prints show correct data, no errors.

- [ ] **Step 3: Commit**

```bash
git add src/aicomic/db/repository.py
git commit -m "feat(db): add character_outfit CRUD methods for v0.9 outfit system"
```

---

### Task 3: CharDesigner rebuild — single design_prompt output

**Files:**
- Modify: `src/aicomic/agents/char_designer.py` — full rewrite of system prompt and execute logic

**Interfaces:**
- Consumes: `Database.create_character_outfit()`, `Database.get_or_create_character()` (existing)
- Produces: `design_prompt` per character saved to `character_outfit` table (is_default=1, tag="默认")

- [ ] **Step 1: Replace the system prompt**

Replace the entire `CHAR_DESIGNER_SYSTEM_PROMPT` constant (lines 12-99) with:

```python
CHAR_DESIGNER_SYSTEM_PROMPT = """You are a professional character designer for Chinese animation/comic production. Your task is to generate a single detailed character design sheet prompt (人物设定图提示词) for each character, in a format suitable for AI image generation.

## Core Requirements

1. **Extract ALL characters** from the provided character list. Generate ONE design_prompt per character.
2. **Detect era background** (时代背景) from the text. Must be one of: "中国古代·仙侠", "中国古代·武侠", "中国古代·宫廷", "中国现代·都市", "中国现代·校园", "民国", "西方奇幻", "科幻未来", "架空世界".
3. **Art style**: Always use "8k 类 3D 游戏 cg 电影风格" for ancient/Xianxia settings. The design sheet should look like a professional game concept art sheet.

## Design Prompt Template

For each character, generate a `design_prompt` following this format:

For ancient Chinese settings:
```
【中国古代·仙侠】角色名（代称），性别 年龄岁，8k 类 3D 游戏 cg 电影风格，
包括左侧人物全身设计图含衣着细节，右侧画面三视图，同时左侧上方为人物名称，
带一些人物简介：[1-2句角色核心背景]。
画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），
中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。
三视图间距均匀，同一水平线对齐。
[角色外貌与衣着细节描写]
[若有法宝/装备]所有画面底下可以给一套法宝细节图，[法宝名称和描述]。
```

For modern settings: replace "【中国古代·仙侠】" with the correct era tag, adjust art style to "8k 高质量 cg 渲染风格".

## Key Rules

4. **No variants** — each character gets exactly ONE design_prompt (their default/default look).
5. **Hands rule**: "双手自然下垂，手里无任何物品" unless the character has a specific held item that is part of their core design.
6. **The design_prompt is a COMPLETE image generation prompt ready to use** — it must contain all visual details.
7. **Character names MUST exactly match the provided character list**.
8. **For animals/beasts/monsters**: Different format — describe species, body shape, fur/skin, distinctive features. Use "【时代背景】角色名（代称），8k 类 3D 游戏 cg 电影风格，全身设定图". Skip three-view layout; describe a single full-body design view.

## Output Format

Return ONLY valid JSON in this exact structure (no other text):

{
  "era_background": "中国古代·仙侠",
  "characters": [
    {
      "name": "萧澈",
      "aliases": ["云澈"],
      "gender": "男",
      "age": 16,
      "is_human": true,
      "design_prompt": "【中国古代·仙侠】萧澈（云澈），男 16岁，8k 类 3D 游戏 cg 电影风格，包括左侧人物全身设计图含衣着细节，右侧画面三视图..."
    }
  ]
}
"""
```

- [ ] **Step 2: Rewrite the `execute()` method**

Replace the `execute` method body (lines 124-242) — keeping the method signature and idempotency pattern, but changing the save logic to use `character_outfit`:

```python
    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        raw_text = input_data["raw_text"]
        characters = input_data["characters"]

        # ── Idempotency check ──
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"characters": characters})

        try:
            user_prompt = (
                f"请为以下小说角色生成人物设定图提示词（JSON 格式）：\n\n"
                f"角色列表：{characters}\n\n"
                f"小说原文：\n{raw_text[:3000]}"
            )

            # ── Call LLM ──
            result_json = self.llm.generate_json(
                system_prompt=CHAR_DESIGNER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )

            # ── Validate structure ──
            self._validate_char_design(result_json, characters)

            # ── Save to character_outfit table ──
            outfits_created = 0
            char_list = result_json.get("characters", [])

            for char_data in char_list:
                name = char_data.get("name", "")
                char_id, _ = db.get_or_create_character(name)
                design_prompt = char_data.get("design_prompt", "")

                if not design_prompt:
                    continue

                # Create default outfit record (image_path empty — ImageGenerator fills it)
                db.create_character_outfit(
                    character_id=char_id,
                    tag="默认",
                    prompt=design_prompt,
                    image_path="",
                    is_default=1,
                    activation_condition="",
                )
                outfits_created += 1

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "outfits_created": outfits_created,
                    "characters_processed": len(char_list),
                },
            )

            return AgentResult(
                success=True,
                data={
                    "outfits_created": outfits_created,
                    "character_names": [c["name"] for c in char_list],
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
```

- [ ] **Step 3: Update `_validate_char_design()` and remove `_build_appearance_json()`**

Replace `_validate_char_design` (lines 245-253) to check for `design_prompt` instead of `variants`:

```python
    @staticmethod
    def _validate_char_design(result: dict, expected_characters: list[str]):
        """Validate the character design JSON structure."""
        if not isinstance(result, dict):
            raise ValueError("Character design JSON must be a dict")
        if "characters" not in result:
            raise ValueError("Character design JSON missing 'characters'")
        if not isinstance(result["characters"], list):
            raise ValueError("'characters' must be a list")
        if len(result["characters"]) == 0:
            raise ValueError("'characters' list is empty")
        for char in result["characters"]:
            if not char.get("design_prompt", ""):
                raise ValueError(
                    f"Character '{char.get('name', '?')}' missing 'design_prompt'"
                )
```

Delete the `_build_appearance_json` static method entirely (lines 256-279).

- [ ] **Step 4: Add `generate_outfit_variant()` method**

Add a public method that generates a design_prompt for a new outfit by swapping clothing descriptions:

```python
    def generate_outfit_variant(
        self, tag: str, clothing_desc: str, activation_condition: str,
        character_name: str, era_background: str, base_info: dict,
        db: Database,
    ) -> int | None:
        """Generate a design_prompt for a new outfit variant.

        Called by OutfitManager when a "new" outfit change is detected.
        Uses LLM to swap clothing descriptions while keeping face/body/props.

        Args:
            tag: Outfit tag name (e.g., "宗门道袍")
            clothing_desc: New clothing description
            activation_condition: When this outfit activates
            character_name: Character name
            era_background: Era tag (e.g. "中国古代·仙侠")
            base_info: Dict with keys: gender, age, aliases, is_human
            db: Database instance

        Returns:
            outfit_id if successful, None on failure
        """
        try:
            user_prompt = (
                f"为角色生成新的换装设定图提示词。\n\n"
                f"角色：{character_name}\n"
                f"时代：{era_background}\n"
                f"原基础信息：性别={base_info.get('gender', '')}, "
                f"年龄={base_info.get('age', '')}岁\n"
                f"新服饰标签：{tag}\n"
                f"新衣着描述：{clothing_desc}\n"
                f"激活条件：{activation_condition}\n\n"
                f"请生成完整的人物设定图提示词（design_prompt），保留角色的"
                f"面部特征、发型、体型、法宝装备等不变，只更换衣着描述。"
                f"在底部法宝区域添加一行标注：[{tag}]。"
                f"返回 JSON：{{\"design_prompt\": \"...\"}}"
            )

            result = self.llm.generate_json(
                system_prompt=CHAR_DESIGNER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            design_prompt = result.get("design_prompt", "")
            if not design_prompt:
                return None

            # Get character_id
            char_id, _ = db.get_or_create_character(character_name)

            # Create outfit record
            outfit_id = db.create_character_outfit(
                character_id=char_id,
                tag=tag,
                prompt=design_prompt,
                image_path="",  # ImageGenerator fills this
                is_default=0,
                activation_condition=activation_condition,
            )
            return outfit_id
        except Exception:
            return None
```

- [ ] **Step 5: Update `validate_input()`**

The `validate_input` method (lines 115-122) no longer needs `character_variants`. Keep it the same — it checks `chapter_id`, `raw_text`, `characters` which are still valid. No change needed.

- [ ] **Step 7: Update `__init__` docstring**

Update the class docstring (lines 102-108):

```python
    """Generates character design sheet prompts for image generation.

    Input:  {"chapter_id": int, "raw_text": str, "characters": list[str]}
    Output: {"outfits_created": int, "character_names": list[str]}

    Also exposes generate_outfit_variant() for the OutfitManager to create
    new outfit design prompts when outfit changes are detected mid-pipeline.
    """
```

- [ ] **Step 8: Verify the agent runs (LLM call)**

```bash
# Skip full pipeline — just validate the module loads correctly
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
import sys; sys.path.insert(0, 'src')
from aicomic.agents.char_designer import CharacterDesignerAgent, CHAR_DESIGNER_SYSTEM_PROMPT
print(f'System prompt length: {len(CHAR_DESIGNER_SYSTEM_PROMPT)}')
print(f'design_prompt check: {\"design_prompt\" in CHAR_DESIGNER_SYSTEM_PROMPT}')
print(f'No variant check: {\"variant\" not in CHAR_DESIGNER_SYSTEM_PROMPT}')
print('Module loaded successfully')
"
```

Expected: `design_prompt check: True`, `No variant check: True`

- [ ] **Step 9: Commit**

```bash
git add src/aicomic/agents/char_designer.py
git commit -m "feat(char-designer): rebuild for single design_prompt output — drop variants"
```

---

### Task 4: ImageGenerator — simplify to single-call design image generation

**Files:**
- Modify: `src/aicomic/agents/image_generator.py` — replace `execute()` to scan `character_outfit` instead of `appearance_variant`

**Interfaces:**
- Consumes: `Database` methods for `character_outfit` (Task 2)
- Produces: Generated design sheet images saved to `character_outfit.image_path`

- [ ] **Step 1: Rewrite `execute()` — scan character_outfit, generate one image per outfit**

Replace the entire `execute` method (lines 161-312). Keep the method signature, idempotency, and helper methods (`_process_entity`, `_user_select_image`). Only change what `execute` does:

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
                        prompt=prompt, aspect_ratio="16:9",
                    )
                    if result.success and result.file_paths:
                        chosen = result.file_paths[0]
                        if len(result.file_paths) > 1:
                            chosen = self._user_select_image(
                                result.file_paths, "角色设定图", outfit["id"],
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

            # ── Generate scene multi-view images (unchanged) ──
            scenes_processed = 0
            for si, scene in enumerate(scenes):
                label = f"场景多景别 {si+1}/{len(scenes)}"
                print(f"    [{label}]")
                if self._process_entity(
                    db, chapter_id, scene, "multi_view_prompt",
                    db.update_scene_card_multi_view, "场景",
                ):
                    scenes_processed += 1

            images_generated = outfits_processed + scenes_processed
            had_pending = bool(outfits) or bool(scenes)

            if images_generated > 0:
                db.set_agent_status(self.agent_name, chapter_id, "done")
                db.log(self.agent_name, chapter_id, "completed", {
                    "images_generated": images_generated,
                    "outfits_processed": outfits_processed,
                    "scenes_processed": scenes_processed,
                })
                return AgentResult(success=True, data={
                    "images_generated": images_generated,
                    "outfits_processed": outfits_processed,
                    "scenes_processed": scenes_processed,
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
```

- [ ] **Step 2: Update class docstring**

Replace line 20-28 docstring:

```python
    """Generates design sheet images for character outfits and scene multi-views.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"images_generated": int, "outfits_processed": int, "scenes_processed": int}

    Pipeline position: after CharDesigner + SceneDesigner, before ShotVisualizer.
    Only runs when --with-images is passed.
    """
```

- [ ] **Step 3: Remove unused `_process_entity` reference_images parameter**

The `_process_entity` method still accepts `reference_images` parameter — that's fine, we just never pass it now (used only for scenes which don't need references). No change needed — keep backward compat.

- [ ] **Step 4: Verify module loads**

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
import sys; sys.path.insert(0, 'src')
from aicomic.agents.image_generator import ImageGeneratorAgent
print('ImageGeneratorAgent loaded successfully')
print(f'agent_name: {ImageGeneratorAgent.agent_name}')
"
```

- [ ] **Step 5: Commit**

```bash
git add src/aicomic/agents/image_generator.py
git commit -m "feat(image-generator): simplify to single-call outfit design image generation"
```

---

### Task 5: New OutfitManager agent

**Files:**
- Create: `src/aicomic/agents/outfit_manager.py`

**Interfaces:**
- Consumes: `Database.get_character_outfit()`, `Database.get_character_outfits()`, `Database.create_character_outfit()`, `Database.update_shot_outfit_tag()`
- Produces: `OutfitManager.detect_outfit_change()` → `OutfitDecision | None`, `OutfitManager.get_active_outfit()` → `dict | None`

- [ ] **Step 1: Write `outfit_manager.py`**

```python
"""Outfit Manager Agent — detects outfit changes and manages outfit lookups.

v0.9: Replaces the old variant system. Each character has one default outfit
(design sheet image) and zero or more tagged alternate outfits. This agent
detects long-term outfit changes during scene transitions and triggers new
design sheet generation on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database


# ── Keywords that signal possible outfit changes ──
_OUTFIT_CHANGE_KEYWORDS = [
    "换上", "换了", "穿上", "换了一身", "换装", "更衣",
    "道袍", "校服", "战甲", "新衣", "换上了", "披上",
    "着装", "打扮", "装束", "服饰", "衣袍", "长袍",
    "宗门", "学院", "制服", "铠甲", "戎装",
]

# ── LLM prompt for detecting long-term outfit changes ──
OUTFIT_DETECTOR_SYSTEM_PROMPT = """You are a script analyst. Your task: detect whether a shot describes a LONG-TERM outfit change for a character.

## Long-term outfit changes (signal "new" or "existing"):
- Joining a sect/school and wearing their uniform (宗门道袍, 学院制服)
- Donning armor before battle (战甲)
- Time skip with new appearance
- Permanent costume change (disguise, transformation)

## Temporary changes (signal None — do NOT trigger):
- Getting wet, dirty, or bloody (temporary state)
- Throwing on a cloak for a moment
- Removing an outer layer briefly
- Minor accessory changes (taking off a ring)

## Input
You will receive:
- The shot text (narration + dialogue)
- The character name
- A list of existing outfit tags for this character

## Output
Return ONLY valid JSON:
- If no outfit change: {"has_change": false}
- If an EXISTING outfit matches: {"has_change": true, "tag": "宗门道袍"}
- If a NEW outfit is needed: {"has_change": true, "tag": "宗门道袍", "clothing_desc": "白底蓝边道袍，左胸绣苍风玄府徽记...", "activation_condition": "萧澈正式加入苍风玄府后"}
"""


# ── LLM prompt for generating new outfit design prompts ──
OUTFIT_PROMPT_GENERATOR_SYSTEM_PROMPT = """You are a professional character designer. Generate a complete character design sheet prompt (人物设定图提示词) for a character with a new outfit.

Follow this format exactly:
【时代背景】角色名（代称），性别 年龄岁，8k 类 3D 游戏 cg 电影风格，
包括左侧人物全身设计图含衣着细节，右侧画面三视图，同时左侧上方为人物名称，
带一些人物简介：[角色简介]。
画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），
中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。
三视图间距均匀，同一水平线对齐。
[角色外貌与新衣着细节]
所有画面底下可以给一套法宝细节图，[法宝描述]。
底部标注：[outfit_tag]

IMPORTANT: Keep the character's face, hairstyle, body type, and equipment/artifacts UNCHANGED. Only replace the clothing description.

Return ONLY valid JSON:
{"design_prompt": "..."}"""


@dataclass
class OutfitDecision:
    """Result of outfit change detection."""
    tag: str
    change_type: str          # "existing" or "new"
    clothing_desc: str = ""   # Only for "new"
    activation_condition: str = ""  # Only for "new"


class OutfitManagerAgent(AgentInterface):
    """Detects outfit changes and manages outfit lookups per shot.

    This agent is called inline during shot processing (not as a standalone
    pipeline step). Its main entry points are detect_outfit_change() and
    get_active_outfit() — both are called by the Orchestrator.

    Input (for execute):  {"chapter_id": int, "script_id": int}
    Output: {"outfits_generated": int, "shots_tagged": int}
    """

    agent_name = "outfit-manager"

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

    # ── Detection ──

    def _has_outfit_keywords(self, text: str) -> bool:
        """Check if text contains any outfit-change keywords."""
        for kw in _OUTFIT_CHANGE_KEYWORDS:
            if kw in text:
                return True
        return False

    def _llm_detect_outfit(
        self, shot_text: str, character_name: str, existing_tags: list[str]
    ) -> dict | None:
        """Call LLM to determine if an outfit change is happening."""
        try:
            tag_list = "、".join(existing_tags) if existing_tags else "无"
            user_prompt = (
                f"角色：{character_name}\n"
                f"已有服饰标签：{tag_list}\n\n"
                f"镜头内容：\n{shot_text[:800]}"
            )
            result = self.llm.generate_json(
                system_prompt=OUTFIT_DETECTOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return result
        except Exception:
            return None

    def _generate_outfit_prompt(
        self, character_name: str, tag: str, clothing_desc: str,
        activation_condition: str,
    ) -> str:
        """Generate a design_prompt for a new outfit via LLM.

        Swaps clothing descriptions while keeping face/body/props from the
        known character. The prompt is used by ImageGenerator to create the
        outfit's design sheet image.
        """
        try:
            user_prompt = (
                f"为角色生成新的换装设定图提示词。\n\n"
                f"角色：{character_name}\n"
                f"新服饰标签：{tag}\n"
                f"新衣着描述：{clothing_desc}\n"
                f"激活条件：{activation_condition}\n\n"
                f"请生成完整的人物设定图提示词（design_prompt），格式遵循：\n"
                f"【时代背景】角色名，性别 年龄岁，8k 类 3D 游戏 cg 电影风格，\n"
                f"包括左侧人物全身设计图含衣着细节，右侧画面三视图...\n"
                f"保留角色的面部特征、发型、体型、法宝装备等不变，只更换衣着描述。\n"
                f"在底部标注：[{tag}]。\n"
                f"返回 JSON：{{\"design_prompt\": \"...\"}}"
            )
            result = self.llm.generate_json(
                system_prompt=OUTFIT_PROMPT_GENERATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return result.get("design_prompt", "")
        except Exception:
            return ""

    def detect_outfit_change(
        self, shot_text: str, character_id: int, character_name: str,
        current_tag: str | None, db: Database,
    ) -> OutfitDecision | None:
        """Detect if this shot triggers an outfit change.

        Returns OutfitDecision or None (no change detected).
        Only runs LLM when keyword pre-filter passes.
        """
        # Step 1: Keyword pre-filter
        if not self._has_outfit_keywords(shot_text):
            return None

        # Step 2: Check existing outfits' activation_conditions
        existing_outfits = db.get_character_outfits(character_id)
        existing_tags = [o["tag"] for o in existing_outfits if o["tag"] != "默认"]

        for outfit in existing_outfits:
            cond = outfit.get("activation_condition", "")
            if cond and cond in shot_text:
                return OutfitDecision(
                    tag=outfit["tag"],
                    change_type="existing",
                )

        # Step 3: LLM detection
        result = self._llm_detect_outfit(shot_text, character_name, existing_tags)
        if not result or not result.get("has_change"):
            return None

        tag = result.get("tag", "")
        if not tag:
            return None

        if tag in existing_tags:
            return OutfitDecision(tag=tag, change_type="existing")

        return OutfitDecision(
            tag=tag,
            change_type="new",
            clothing_desc=result.get("clothing_desc", ""),
            activation_condition=result.get("activation_condition", ""),
        )

    # ── Lookup ──

    def get_active_outfit(
        self, character_id: int, outfit_tag: str | None, db: Database,
    ) -> dict | None:
        """Get the active outfit for a character in a shot.

        Args:
            character_id: character_card.id
            outfit_tag: shot's outfit_tag (None → use default)
            db: Database instance

        Returns:
            character_outfit row dict, or None
        """
        if outfit_tag:
            outfit = db.get_character_outfit(character_id, outfit_tag)
            if outfit:
                return outfit
            # Fallback to default if tag not found
        return db.get_character_outfit(character_id, None)  # default

    # ── Standalone execute (runs per-chapter, pre-processes all shots) ──

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        """Pre-process all shots for outfit changes. Called as pipeline step.

        Scans shots at scene transitions, detects outfit changes, and creates
        outfit records for new outfits (images generated later by ImageGenerator).
        """
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]

        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"script_id": script_id})

        try:
            shots = db.get_storyboard_shots(script_id)
            if not shots:
                db.set_agent_status(self.agent_name, chapter_id, "done")
                return AgentResult(success=True, data={"outfits_generated": 0, "shots_tagged": 0})

            # Group shots by scene_id for scene-transition detection
            shots_by_scene: dict[int, list[dict]] = {}
            for s in shots:
                sd = dict(s)
                sid = sd.get("scene_id", 0)
                shots_by_scene.setdefault(sid, []).append(sd)

            outfits_generated = 0
            shots_tagged = 0

            # Track current outfit tag per character across scenes
            char_current_tags: dict[int, str | None] = {}

            prev_scene_id = None
            for shot in shots:
                sd = dict(shot)
                scene_id = sd.get("scene_id")
                shot_num = sd["shot_num"]
                shot_id = sd["id"]
                shot_text = f"{sd.get('narration', '')} {sd.get('dialogue', '')}"

                # Resolve characters in this shot
                char_ids_raw = sd.get("char_ids", "[]")
                import json
                try:
                    char_ids = json.loads(char_ids_raw) if isinstance(char_ids_raw, str) else char_ids_raw
                except (json.JSONDecodeError, TypeError):
                    char_ids = []

                is_scene_transition = (prev_scene_id is not None and scene_id != prev_scene_id)
                prev_scene_id = scene_id

                for char_id in char_ids:
                    # Get character name
                    char_row = db.conn.execute(
                        "SELECT name FROM character_card WHERE id = ?", (char_id,)
                    ).fetchone()
                    char_name = char_row["name"] if char_row else "未知"

                    current_tag = char_current_tags.get(char_id)

                    # Only detect on scene transitions (节流策略1)
                    if not is_scene_transition and current_tag is not None:
                        # Inherit existing tag
                        db.update_shot_outfit_tag(shot_id, current_tag)
                        shots_tagged += 1
                        continue

                    # Detect
                    decision = self.detect_outfit_change(
                        shot_text, char_id, char_name, current_tag, db,
                    )

                    if decision is None:
                        # No change — inherit current tag
                        db.update_shot_outfit_tag(shot_id, current_tag)
                        if current_tag:
                            shots_tagged += 1
                    elif decision.change_type == "existing":
                        char_current_tags[char_id] = decision.tag
                        db.update_shot_outfit_tag(shot_id, decision.tag)
                        shots_tagged += 1
                    elif decision.change_type == "new":
                        # Generate design prompt + create outfit record
                        design_prompt = self._generate_outfit_prompt(
                            char_name, decision.tag,
                            decision.clothing_desc,
                            decision.activation_condition,
                        )
                        db.create_character_outfit(
                            character_id=char_id,
                            tag=decision.tag,
                            prompt=design_prompt,  # Ready for ImageGenerator
                            image_path="",
                            is_default=0,
                            activation_condition=decision.activation_condition,
                        )
                        char_current_tags[char_id] = decision.tag
                        db.update_shot_outfit_tag(shot_id, decision.tag)
                        outfits_generated += 1
                        shots_tagged += 1

            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(self.agent_name, chapter_id, "completed", {
                "outfits_generated": outfits_generated,
                "shots_tagged": shots_tagged,
            })

            return AgentResult(success=True, data={
                "outfits_generated": outfits_generated,
                "shots_tagged": shots_tagged,
            })

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
```

- [ ] **Step 2: Verify module loads**

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
import sys; sys.path.insert(0, 'src')
from aicomic.agents.outfit_manager import OutfitManagerAgent, OutfitDecision, _OUTFIT_CHANGE_KEYWORDS
print(f'OutfitManagerAgent loaded: {OutfitManagerAgent.agent_name}')
print(f'Keywords: {len(_OUTFIT_CHANGE_KEYWORDS)}')
d = OutfitDecision(tag='测试', change_type='new', clothing_desc='test')
print(f'OutfitDecision: {d}')
print('Module OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add src/aicomic/agents/outfit_manager.py
git commit -m "feat(outfit-manager): new agent for outfit change detection and matching"
```

---

### Task 6: ShotVideoGenerator — adapt to single design image + outfit_tag

**Files:**
- Modify: `src/aicomic/agents/shot_video_generator.py` — `_resolve_reference_images()` and `_build_video_prompt()`

**Interfaces:**
- Consumes: `Database.get_character_outfit()` (Task 2), `shot.outfit_tag` (Task 1)
- Produces: Updated reference image list (single design image per character) + updated video prompt text

- [ ] **Step 1: Rewrite `_resolve_reference_images()`**

Replace lines 54-129:

```python
    def _resolve_reference_images(
        self, db: Database, shot: dict, script_id: int
    ) -> list[str]:
        """Find reference images for a shot: character design sheets + scene multi-view.

        v0.9: Each character contributes ONE design sheet image (from character_outfit),
        resolved by shot.outfit_tag. No more face closeup + three-view.
        """
        images: list[str] = []

        # ── Character design sheet images ──
        char_ids_raw = shot.get("char_ids", "[]")
        try:
            char_ids = json.loads(char_ids_raw) if isinstance(char_ids_raw, str) else char_ids_raw
        except (json.JSONDecodeError, TypeError):
            char_ids = []

        outfit_tag = shot.get("outfit_tag")  # None → default

        for char_id in char_ids:
            outfit = db.get_character_outfit(char_id, outfit_tag)
            if not outfit:
                # Fallback: default outfit
                outfit = db.get_character_outfit(char_id, None)
            if outfit:
                img_path = outfit.get("image_path", "")
                if img_path and Path(img_path).exists():
                    images.append(img_path)

        # ── Scene multi-view image (unchanged) ──
        scene_id = shot.get("scene_id")
        if scene_id:
            row = db.conn.execute(
                "SELECT multi_view_image FROM scene_card WHERE id = ? AND multi_view_image != ''",
                (scene_id,),
            ).fetchone()
            if row and row["multi_view_image"]:
                path = row["multi_view_image"]
                if Path(path).exists():
                    images.append(path)

        return images
```

- [ ] **Step 2: Update `_build_video_prompt()` — simplify reference image description**

Replace lines 171-176 (the `parts.append(...)` call for reference image description):

```python
        parts.append(
            "高质量AI视频，流畅运镜，电影级画面。"
            "参考图说明：人物参考图为角色设定图（含全身设计+三视图+人物简介+装备细节）；"
            "场景参考图为多景别设定。"
        )
```

- [ ] **Step 3: Update class docstring**

Replace lines 24-31:

```python
    """Generates video clips per storyboard shot via image-to-video on Doubao.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"clips_created": int, "total_shots": int}

    Pipeline position: after ShotVisualizer, before VideoComposer.
    Only runs when --with-video is passed and video_backend is "doubao".
    v0.9: Uses single character design sheet images (not face closeup + three-view).
    """
```

- [ ] **Step 4: Verify module loads**

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
import sys; sys.path.insert(0, 'src')
from aicomic.agents.shot_video_generator import ShotVideoGeneratorAgent
print(f'ShotVideoGeneratorAgent loaded: {ShotVideoGeneratorAgent.agent_name}')
# Check _build_video_prompt doesn't reference old text
import inspect
src = inspect.getsource(ShotVideoGeneratorAgent._build_video_prompt)
assert '第1张为角色面部特写' not in src, 'Old reference description still present'
assert '三视图（左侧面-中正面-右背面' not in src, 'Old three-view description still present'
print('Prompt text updated ✓')
"
```

- [ ] **Step 5: Commit**

```bash
git add src/aicomic/agents/shot_video_generator.py
git commit -m "feat(shot-video): adapt to single design image + outfit_tag references"
```

---

### Task 7: Orchestrator — integrate OutfitManager + remove variant logic

**Files:**
- Modify: `src/aicomic/orchestrator.py` — add OutfitManager step, remove `_extract_character_variants()`

**Interfaces:**
- Consumes: `OutfitManagerAgent` (Task 5), updated `CharacterDesignerAgent` (Task 3)
- Produces: Updated pipeline with OutfitManager step after CharDesigner

- [ ] **Step 1: Add import for OutfitManagerAgent**

Add at top with other agent imports:

```python
from .agents.outfit_manager import OutfitManagerAgent
```

- [ ] **Step 2: Update `run_chapter()` — remove variant extraction, add OutfitManager step, update prints**

Changes to `run_chapter()`:

a) Remove the `char_variants` extraction block (lines 119-122):
```python
        # ── Step 2: Character Designer ──
        char_result = self.bus.run(
            "char-designer",
            {
                "chapter_id": chapter_id,
                "raw_text": raw_text,
                "characters": characters,
                "script_id": script_id,
            },
            self.db,
        )
```
Note: `script_id` is still passed for logging but `character_variants` key is removed.

b) Update the CharDesigner success print (lines 144-146):
```python
        outfits_created = char_result.data.get("outfits_created", 0) if char_result.data else 0
        char_names = char_result.data.get("character_names", []) if char_result.data else []
        print(f"  ✓ Character Designer: {outfits_created} 角色设定图提示词 ({', '.join(char_names) if char_names else 'N/A'})")
```

c) After SceneDesigner, add OutfitManager step (insert before ImageGenerator):
```python
        # ── Step 3.2: Outfit Manager (detect outfit changes, tag shots) ──
        outfit_result = self.bus.run(
            "outfit-manager",
            {"chapter_id": chapter_id, "script_id": script_id},
            self.db,
        )
        if outfit_result.success:
            outfits_gen = outfit_result.data.get("outfits_generated", 0) if outfit_result.data else 0
            shots_tagged = outfit_result.data.get("shots_tagged", 0) if outfit_result.data else 0
            if outfits_gen > 0:
                print(f"  ✓ Outfit Manager: {outfits_gen} 新服饰标签, {shots_tagged} 镜头已标记")
            else:
                print(f"  ⏭ Outfit Manager: 无换装检测, {shots_tagged} 镜头已标记")
        else:
            print(f"  ⚠ Outfit Manager: {outfit_result.error}")
```

d) Update the pipeline_completed log entry — replace `"char_designer"` value:
```python
            "char_designer": "ok" if char_result.success else "failed",
```
(Stay the same, just verifying)

- [ ] **Step 3: Remove `_extract_character_variants()` method**

Delete the entire `_extract_character_variants` method (lines 35-57).

- [ ] **Step 4: Update `run_chapter()` docstring**

Update the pipeline steps in the docstring (lines 64-73):

```python
        """Run the full pipeline for a single chapter.

        Pipeline steps (v0.9):
            1. Screenwriter — generate script from raw text
            2. Character Designer — generate design sheet prompts
            3. Scene Designer — generate scene environment descriptions
            4. Outfit Manager — detect outfit changes, tag shots
            5. Image Generator — generate design sheet + scene images (optional)
            6. Shot Visualizer — generate per-shot composite image prompts
            7. Shot Video Generator — image-to-video per shot (optional)
            8. Video Composer — stitch clips into final video (optional)
        """
```

- [ ] **Step 5: Verify orchestrator loads**

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
import sys; sys.path.insert(0, 'src')
from aicomic.orchestrator import Orchestrator
print(f'Orchestrator loaded')
# Verify _extract_character_variants is gone
import inspect
methods = [m for m in dir(Orchestrator) if not m.startswith('_') or m.startswith('_extract')]
has_extract = hasattr(Orchestrator, '_extract_character_variants')
print(f'_extract_character_variants present: {has_extract} (should be False)')
"
```

Expected: `_extract_character_variants present: False`

- [ ] **Step 6: Commit**

```bash
git add src/aicomic/orchestrator.py
git commit -m "feat(orchestrator): integrate OutfitManager, drop variant extraction"
```

---

### Task 8: main.py — register OutfitManager, update pipeline wiring

**Files:**
- Modify: `src/aicomic/main.py` — register OutfitManager, fix data keys

**Interfaces:**
- Consumes: `OutfitManagerAgent` (Task 5)
- Produces: Correctly wired pipeline

- [ ] **Step 1: Add OutfitManager import and registration**

In `cmd_run()`, add the import (after other agent imports around line 104):

```python
    from .agents.outfit_manager import OutfitManagerAgent
```

After registering `shot_visualizer` (line 149), add:

```python
        # v0.9: Outfit Manager (runs after SceneDesigner, before ImageGenerator)
        outfit_manager = OutfitManagerAgent(llm_client=llm)
        bus.register(outfit_manager)
```

- [ ] **Step 2: Update the pipeline label and step display**

Change `pipeline_label` from `"v0.8"` to `"v0.9"` (line 214).

Update the `steps` string (lines 215-222):

```python
        steps = "Screenwriter → CharDesigner → SceneDesigner → OutfitManager"
        steps += " → ImageGenerator" if with_images else ""
        steps += " → ShotVisualizer"
```

- [ ] **Step 3: Update result data keys to match new agent outputs**

In the final print block (lines 231-245), update:

```python
                print(f"  Characters: {result.data.get('characters')}")
                print(f"  Scenes: {result.data.get('scenes_list')}")
                print(f"  Outfits created: {result.data.get('outfits_created', 0)}")
```

(Essentially replace `char_variants_created` with `outfits_created`.)

- [ ] **Step 4: Verify main module imports**

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
import sys; sys.path.insert(0, 'src')
# Just verify all imports resolve
from aicomic.agents.outfit_manager import OutfitManagerAgent
from aicomic.agents.char_designer import CharacterDesignerAgent
from aicomic.agents.image_generator import ImageGeneratorAgent
from aicomic.agents.shot_video_generator import ShotVideoGeneratorAgent
from aicomic.orchestrator import Orchestrator
from aicomic.bus import AgentBus
from aicomic.db.repository import Database
print('All imports OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add src/aicomic/main.py
git commit -m "feat(main): register OutfitManager, bump pipeline to v0.9"
```

---

### Task 9: Cleanup — update orchestrator data keys + test fixes

**Files:**
- Modify: `src/aicomic/orchestrator.py:296-319` — update `run_chapter()` return data keys
- Modify: `tests/test_char_designer.py` — update expected outputs
- Modify: `tests/test_orchestrator.py` — if variant-dependent

**Interfaces:**
- Consumes: All previous tasks
- Produces: Consistent data keys across the pipeline

- [ ] **Step 1: Update orchestrator return data keys**

In `run_chapter()`, update the final `AgentResult` data dict (lines 301-318):

```python
        return AgentResult(
            success=True,
            data={
                "chapter_id": chapter_id,
                "script_id": script_id,
                "characters": characters,
                "scenes_list": scenes_list,
                "outfits_created": char_result.data.get("outfits_created", 0) if char_result.data else 0,
                "scenes_updated": scene_result.data.get("scenes_updated", 0) if scene_result.data else 0,
                "outfits_detected": outfit_result.data.get("outfits_generated", 0) if (outfit_result and outfit_result.data) else 0,
                "images_generated": img_result.data.get("images_generated", 0) if (img_result and img_result.data) else 0,
                "outfits_processed": img_result.data.get("outfits_processed", 0) if (img_result and img_result.data) else 0,
                "scenes_processed": img_result.data.get("scenes_processed", 0) if (img_result and img_result.data) else 0,
                "shots_visualized": shot_vis_result.data.get("shots_processed", 0) if shot_vis_result.data else 0,
                "shot_video_clips": shot_video_result.data.get("clips_created", 0) if (shot_video_result and shot_video_result.data) else 0,
                "clips_created": video_result.data.get("clips_created", 0) if (video_result and video_result.data) else 0,
                "final_video_path": composer_result.data.get("final_video_path") if (composer_result and composer_result.data) else None,
                "clip_count": composer_result.data.get("clip_count", 0) if (composer_result and composer_result.data) else 0,
            },
        )
```

Key changes: `char_variants_created` → `outfits_created`, `variants_processed` → `outfits_processed`, added `outfits_detected`.

- [ ] **Step 2: Run existing tests to find breakage**

```bash
cd D:/first_agent && C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -x --tb=short 2>&1 | head -80
```

- [ ] **Step 3: Fix test_char_designer.py**

Check what the char_designer tests expect. The key changes:
- Output now has `outfits_created` instead of `variants_created`
- LLM output format has `design_prompt` instead of `variants`
- No more `appearance_variant` table writes

Read the test file first, then apply targeted fixes.

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_char_designer.py -x --tb=long
```

Expected failures about `variants_created` → update to `outfits_created`.

- [ ] **Step 4: Fix test_orchestrator.py if needed**

```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_orchestrator.py -x --tb=long
```

- [ ] **Step 5: Run full test suite**

```bash
cd D:/first_agent && C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/ -v --tb=short
```

Target: all tests pass or are skipped (E2E tests require real API keys).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix: update data keys and tests for v0.9 outfit system"
```

---

## Post-Implementation Verification

After all tasks are complete, run the full pipeline test:

```bash
# Clean start
del D:\first_agent\data\aicomic.db
rd /s /q D:\first_agent\data\images
rd /s /q D:\first_agent\data\videos

# Full image pipeline (no video)
C:\Users\w\AppData\Local\Programs\Python\Python312\python.exe -m aicomic run "D:\first_agent\逆天邪神第1章 云澈、萧澈.txt" --with-images --no-headless
```

Expected: CharDesigner generates design_prompt per character → ImageGenerator generates one image per outfit → OutfitManager runs and tags shots → ShotVisualizer generates per-shot prompts → Pipeline completes successfully.
