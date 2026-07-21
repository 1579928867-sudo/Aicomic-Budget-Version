# 角色设定图 + 换装锚点系统 设计文档

**日期**: 2026-07-21  
**状态**: 设计完成  
**上下文**: AI漫剧 v0.8 → v0.9 — 三视图重构为人物设定图，取消变体系统，引入换装锚点

---

## 1. 动机

### 问题
1. 当前角色图片生成是二段式流程（脸部特写 → 三视图），步骤多、耗时长
2. 三视图存在"大头娃娃"问题（头部比例失调）
3. 变体系统（character_variants）的"一个角色多套外观"语义不清晰 — Screenwriter 理解的变体（同一章内不同形态）和实际需要的（跨章节换装）不一致

### 目标
- 用**单张人物设定图**替代三视图，一张图包含全身设计 + 右侧三视 + 名字简介 + 法宝细节
- 去掉变体系统，改为**标签化换装**：默认服饰 + 长期换装锚点
- 简化图片生成流程：单次调用 = 一张设定图

---

## 2. 数据模型变更

### 新增表: `character_outfits`

```sql
CREATE TABLE character_outfits (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id  TEXT NOT NULL,          -- 角色名，如 "萧澈(云澈)"
    tag           TEXT NOT NULL,          -- 唯一标签，如 "宗门道袍"、"默认"
    prompt        TEXT NOT NULL,          -- 生成设定图用的完整提示词
    image_path    TEXT,                   -- 设定图文件路径（生成前可为空）
    is_default    INTEGER DEFAULT 0,     -- 1 = 默认服饰，每个角色只有一个
    activation_condition TEXT,           -- LLM 用于判断何时启用此 outfit
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(character_id, tag)
);
```

### `shots` 表加列

```sql
ALTER TABLE shots ADD COLUMN outfit_tag TEXT DEFAULT NULL;
```
- `NULL` = 使用默认服饰（`is_default=1`）
- 非空 = 精确匹配 `character_outfits.tag`

### 删除内容
- `character_variants` 表及所有变体相关逻辑
- `shots` 表中的 variant 相关列（如有）

---

## 3. 角色设定图 Prompt 模板

用户测试过的仙侠风格模板（作为默认基准，后续可按题材扩展）：

```
【中国古代・仙侠】{角色名}，{性别} {年龄}岁，8k 类 3D 游戏 cg 电影风格，
包括左侧人物全身设计图含衣着细节，右侧画面三视图，同时左侧上方为人物名称，
带一些人物简介：{角色简介}。
画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），
中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型
与服装背面设计）。三视图间距均匀，同一水平线对齐。
{角色外貌与衣着细节}
所有画面底下可以给一套法宝细节图，{法宝描述}。
```

---

## 4. CharDesigner 重构

### 砍掉的
- `_generate_face_closeup()` — 不再需要独立脸部特写
- `_generate_three_view()` — 不再需要独立三视图
- `_iterate_variants()` — 不再需要变体循环
- 所有变体相关属性和方法

### 留下的
- 角色基本属性提取（名字、年龄、外貌描述、气质）
- 这些都编织进设定图 prompt

### 新方法

#### `generate_default_design(character: Character) -> CharacterOutfit`
1. 从 Screenwriter 输出的角色设定中提取字段
2. 用设定图 prompt 模板组装完整提示词
3. 调用 ImageGenerator 生成单张图
4. 写入 `character_outfits`（`is_default=1`, `tag="默认"`）
5. 返回 outfit 记录

#### `generate_outfit_variant(tag: str, clothing_desc: str, activation_condition: str, base_character: Character) -> CharacterOutfit`
1. 复用设定图 prompt 模板
2. 用 `clothing_desc` 替换衣着相关描述
3. 底部法宝可保留或按需更新
4. 调用 ImageGenerator 生成单张图
5. 写入 `character_outfits`（`is_default=0`, `tag` 由调用方传入）
6. 返回 outfit 记录

---

## 5. ImageGenerator 简化

### 变更
- **之前**: 二段式 — `generate_face_closeup() + generate_three_view()`，牵涉参考图互引
- **之后**: 单次调用 — `generate_image(prompt)` → 等生成 → 下载 → 返回路径

### 保留
- 豆包页面的基础交互（输入 prompt、点击生成、下载图片）
- 这与 ShotVideoGenerator 的视频生成流程无关，不受影响

### 删除
- `_paste_reference_image()` — 图片生成阶段不再需要上传参考图
- `_composite_generation()` 等多步骤编排逻辑

---

## 6. OutfitManager（新 Agent）

### 职责
检测、生成、匹配角色服饰。是换装系统的中枢。

### 方法

#### `detect_outfit_change(shot_text: str, character_id: str, current_tag: str | None) -> OutfitDecision | None`

**节流策略**（避免每 shot 都调 LLM）:
1. **场景切换预筛** — 只在 `scene_id` 变化后的第一个 shot 执行检测
2. **关键词预筛** — shot 文本匹配换装关键词（"换上""换了""穿上""换了一身""道袍""校服""战甲""新衣"等）才进入 LLM 检测
3. 两项都不满足 → 直接返回 `None`，`outfit_tag` 继承上一个 shot 的值

**检测逻辑**（触发时）:
1. 查 `character_outfits` 表，看已有 outfit 的 `activation_condition` 是否被 shot 文本满足
2. 有匹配 → 返回 `{tag, change_type: "existing"}`
3. 无匹配 → 调 LLM 判断：是否有长期换装？
   - 是 → 返回 `{tag, change_type: "new", clothing_desc, activation_condition}`
   - 否 → 返回 `None`

**LLM 判断标准**（区分长期换装 vs 临时变化）:
- 长期换装：入宗门、换校服、战甲变身、时间跳跃后新造型 — 需生成新设定图
- 临时变化：受伤染血、淋湿、披了件外衣 — 不生成设定图，只改视频 prompt

#### `get_active_outfit(character_id: str, outfit_tag: str | None) -> CharacterOutfit`
- `outfit_tag` 有值 → 精确匹配 `character_outfits` 查询
- `outfit_tag` 为 `None` → 返回 `is_default=1` 那条

#### `list_outfits(character_id: str) -> list[CharacterOutfit]`
- 列出某角色所有服饰，供调试/查看

---

## 7. 管线集成

### Screenwriter 阶段（预定义出口）
- 剧本可标注角色服饰规划：
  ```
  萧澈.outfits = [
    {tag: "默认", is_default: true},
    {tag: "宗门道袍", activation: "入苍风玄府后"},
    {tag: "战损", activation: "大决战受伤后"}
  ]
  ```
- 预定义的 outfit 写入 `character_outfits`，`image_path` 和 `prompt` 先为空
- 实际生成在管线跑到时候按需触发

### CharDesigner 阶段
- 只生成默认服饰设定图（`is_default=1`）
- 预定义的其他 outfit 不在此阶段生成

### Shot 处理阶段（LLM 检测出口）
```
对每个 shot 的每个出场角色:
  1. 检查是否为场景切换后第一个 shot → 否 → 继承上一 shot 的 outfit_tag，跳过
  2. 关键词预筛 → 不命中 → 继承上一 shot 的 outfit_tag，跳过
  3. OutfitManager.detect_outfit_change(shot_text, character) → LLM 判断
  4. change_type == "existing" → shot.outfit_tag = tag
  5. change_type == "new" → CharDesigner.generate_outfit_variant(tag, desc, condition)
     → 写入 character_outfits → shot.outfit_tag = tag
  6. change_type == None → shot.outfit_tag = 继承当前值（保持默认）
```

### 视频生成阶段
- `ShotVideoGenerator`:
  1. 根据 `shot.outfit_tag` 查 `OutfitManager.get_active_outfit()` 获取设定图路径
  2. **参考图**: 单张人物设定图（替代之前的脸部特写 + 三视图）
  3. **视频提示词**: 
     - 默认服饰 → "参考图人物着装"
     - 有换装 → "参考图人物着装已更换为{tag}：{clothing_desc}"
  4. 场景参考图不变

---

## 8. 待办项覆盖

| 待办 (v0.8) | 本次 | 说明 |
|-------------|------|------|
| 🔧 大头娃娃 | 自然解决 | 新设定图格式不再独立生成三视图，单图整体比例可控 |
| 🔧 视频首尾帧一致性 | 未覆盖 | 留待后续 |
| 🔧 豆包日额度排队 | 未覆盖 | 留待后续 |
| 🔧 完整跑通评估 | 验证目标 | 改完后跑通第1章 |

---

## 9. 关键文件

| 文件 | 改动 |
|------|------|
| `src/aicomic/agents/char_designer.py` | 重构：删除变体/二段式，新增 `generate_default_design()` 和 `generate_outfit_variant()` |
| `src/aicomic/agents/image_generator.py` | 简化：删除多步骤图片生成逻辑，保留单次调用 |
| `src/aicomic/agents/outfit_manager.py` | **新建**：换装检测、匹配、触发生成 |
| `src/aicomic/agents/shot_video_generator.py` | 适配：单张设定图作为参考，outfit_tag 感知的 prompt 构建 |
| `src/aicomic/agents/screenwriter.py` | 微调：支持 outfit 预定义标注（可选） |
| `src/aicomic/db/repository.py` | 新增 `character_outfits` 表操作，`shots` 表加 `outfit_tag` 列 |
| `src/aicomic/orchestrator.py` | 集成 OutfitManager 到管线 |

---

## 10. 风险与后续

| 风险 | 应对 |
|------|------|
| 单张设定图包含信息密度高，豆包可能画不全 | 测试时先跑一个角色看效果，不行就拆成两张（全身设计 + 三视图，但一次调用生成） |
| LLM 换装检测误判 | 关键词预筛大幅降低误判面；出问题时可人工 review 修正 |
| 换装设定图与默认图人脸不一致 | 生成换装设定图时把默认图作为豆包参考图上传，保持人脸一致 |
