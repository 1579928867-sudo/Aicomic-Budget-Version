# Image Generation Optimization Design

**Date**: 2026-07-19
**Status**: approved
**Context**: AI 漫剧项目 — 图片生成流水线优化

## Problem

当前 image_generator 为每个角色变体生成 front/side/back 三张独立图片（3 次轮询），每个场景生成 wide/mid/close 三张独立图片（3 次轮询）。豆包每次返回 4 张图但仅取第一张。核心问题：

1. **轮询次数过多**：3 角色变体 + 2 场景 = 15 次轮询，每次 30-90 秒，总耗时 ~15 分钟
2. **图片浪费**：豆包每次返回 4 张，只取 1 张，其余 3 张丢弃
3. **无人工筛选**：自动取第一张，质量不可控

## Solution

三视图/多景别合并为单张图片，一次对话生成；利用豆包每次 4 张的特性，**用户交互式选择最佳的一张**，其余删除。

**轮询次数**：15 次 → 5 次（降低 67%），总耗时 ~5 分钟。

## Architecture

```
┌─ Prompt 层 ─────────────────────────────────────────┐
│ char_designer.py  →  新增 three_view_prompt 输出     │
│ scene_designer.py →  新增 multi_view_prompt 输出     │
└─────────────────────────────────────────────────────┘
                          ↓
┌─ Browser 层 ────────────────────────────────────────┐
│ browser.py → generate_image() 返回全部 4 张路径      │
└─────────────────────────────────────────────────────┘
                          ↓
┌─ Agent 层 ──────────────────────────────────────────┐
│ image_generator.py → 每实体1次调用 → 用户选择 → 存DB │
└─────────────────────────────────────────────────────┘
                          ↓
┌─ DB 层 ─────────────────────────────────────────────┐
│ appearance_variant: +three_view_prompt, +three_view_image │
│ scene_card:         +multi_view_prompt, +multi_view_image │
└─────────────────────────────────────────────────────┘
```

### Strategy: 增量扩展（不改旧逻辑）

旧字段（front/side/back_view_prompt, wide/mid/close_view_prompt 及对应的 _image 字段）**保留不动**，用于后续 shot_visualizer 分镜合成。新增 `three_view_*` 和 `multi_view_*` 列专门服务于图片生成。

## DB Schema Changes

### appearance_variant

```sql
ALTER TABLE appearance_variant ADD COLUMN three_view_prompt TEXT DEFAULT '';
ALTER TABLE appearance_variant ADD COLUMN three_view_image TEXT DEFAULT '';
```

### scene_card

```sql
ALTER TABLE scene_card ADD COLUMN multi_view_prompt TEXT DEFAULT '';
ALTER TABLE scene_card ADD COLUMN multi_view_image TEXT DEFAULT '';
```

### Repository 新增方法

```python
def update_appearance_variant_three_view(self, variant_id: int, file_path: str):
    self.conn.execute(
        "UPDATE appearance_variant SET three_view_image = ? WHERE id = ?",
        (file_path, variant_id),
    )
    self.conn.commit()

def update_scene_card_multi_view(self, scene_id: int, file_path: str):
    self.conn.execute(
        "UPDATE scene_card SET multi_view_image = ? WHERE id = ?",
        (file_path, scene_id),
    )
    self.conn.commit()
```

## LLM Prompt Changes

### char_designer — three_view_prompt

每个 variant 新增字段。排版规则：**左中右排列**（侧面 | 正面 | 背面），同一水平线对齐，纯白背景。

```json
"three_view_prompt": "古代仙侠风格，【中国古代·仙侠】萧澈（云澈），男 16岁，写实电影感风格，三视图角色设定图，纯白色背景。画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。三视图间距均匀，同一水平线对齐。黑色长发束髻，白玉发冠；剑眉星目..."
```

格式模板：
```
[风格前缀] [时代背景] [角色名]，[性别] [年龄]，写实电影感风格，三视图角色设定图，纯白色背景。画面从左到右排列三个视角：左侧为侧面全身站立（...），中间为正面全身站立（...），右侧为背面全身站立（...）。三视图间距均匀，同一水平线对齐。[外观细节...]
```

### scene_designer — multi_view_prompt

每个 scene 新增字段。排版规则：**上中下排列**（全景 | 中景 | 特写），16:9 横向。

```json
"multi_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，场景多景别设定图，横向16:9，从上到下排列三个景别：上方为全景广角（展示完整空间关系），中间为中景（展示核心活动区域），下方为特写（展示材质纹理与关键道具细节）。萧澈卧室｜中式古典卧室..."
```

格式模板：
```
不能出现其他人，无人纯场景，no humans,empty,landscape only，[风格前缀] [时代背景] 写实电影感风格，场景多景别设定图，横向16:9，从上到下排列三个景别：上方为全景广角（展示完整空间关系），中间为中景（展示核心活动区域），下方为特写（展示材质纹理与关键道具细节）。[场景名]｜[场景描述...]
```

## Browser Client Changes

### ImageResult 新增字段

```python
@dataclass
class ImageResult:
    success: bool
    file_path: str          # 保留：第一张路径（向后兼容）
    file_paths: list[str]   # 新增：全部下载成功的图片路径
    url: str = ""
    metadata: dict = field(default_factory=dict)
    error: str | None = None
```

### generate_image() 改动

下载循环改为收集全部路径到 `file_paths`，`file_path` 取第一项兼容旧调用方：

```python
downloaded = []
for i, gimg in enumerate(grid):
    path = self._download_grid_image(page, gimg, img_dir)
    if path:
        downloaded.append(path)

if downloaded:
    return ImageResult(
        success=True, file_path=downloaded[0], file_paths=downloaded,
        metadata={"generator": "doubao", "total_downloaded": len(downloaded)},
    )
```

## Image Generator Agent Changes

### 核心重构：`_process_views` → `_process_entity`

旧逻辑循环 3 个视图各调一次豆包，新逻辑每个实体只调 1 次：

```python
def _process_entity(self, db, chapter_id, entity, prompt_field, update_fn, entity_type):
    """一次调用 → N张图 → CLI交互式选择 → 保留1张删其余 → 更新DB"""
    prompt = entity.get(prompt_field, "")
    if not prompt:
        return False

    result = self.browser.generate_image(prompt=prompt, aspect_ratio="16:9")
    if not result.success or not result.file_paths:
        return False

    paths = result.file_paths
    if len(paths) == 1:
        update_fn(entity["id"], paths[0])
        return True

    chosen = self._user_select_image(paths, entity_type, entity["id"])
    if chosen is None:
        return False

    update_fn(entity["id"], chosen)
    for p in paths:
        if p != chosen:
            Path(p).unlink(missing_ok=True)
    return True
```

### CLI 交互式选择

```python
def _user_select_image(self, paths, entity_type, entity_id):
    """用系统默认查看器打开所有候选图，终端等待用户输入 1-N"""
    print(f"\n  📷 {entity_type} #{entity_id} — 豆包生成了 {len(paths)} 张候选图：")
    for i, p in enumerate(paths):
        print(f"    [{i+1}] {p}")

    # 系统默认打开
    for p in paths:
        os.startfile(p)  # Windows (os.startfile); macOS/Linux: open/xdg-open

    while True:
        choice = input(f"  选择保留哪张？(1-{len(paths)}，回车默认选1): ").strip()
        if choice == "":
            choice = "1"
        idx = int(choice) - 1
        if 0 <= idx < len(paths):
            chosen = paths[idx]
            print(f"  ✓ 保留 [{idx+1}] {Path(chosen).name}，删除其余 {len(paths)-1} 张\n")
            return chosen
        print(f"  ⚠ 请输入 1-{len(paths)}")
```

### execute() 改为查新列

```python
# 角色：查 three_view_prompt 非空且 three_view_image 为空
variants = db.conn.execute(
    """SELECT id, three_view_prompt FROM appearance_variant
       WHERE three_view_prompt != '' AND three_view_image = ''"""
).fetchall()

# 场景：查 multi_view_prompt 非空且 multi_view_image 为空
scenes = db.conn.execute(
    """SELECT id, multi_view_prompt FROM scene_card
       WHERE multi_view_prompt != '' AND multi_view_image = ''"""
).fetchall()
```

## Impact Summary

| 维度 | 旧 | 新 |
|---|---|---|
| 角色轮询次数（3变体） | 9 | 3 |
| 场景轮询次数（2场景） | 6 | 2 |
| 总耗时（估算） | ~15min | ~5min |
| 图片质量 | 自动取第一张 | 用户人工精选 |
| 旧字段 | — | **保留不动**（shot_visualizer 后续用） |
| 向后兼容 | — | `file_path` 字段不变，旧调用方无影响 |

## Files Changed

| File | Change |
|---|---|
| `src/aicomic/db/repository.py` | migrate_schema + 2 个新 update 方法 |
| `src/aicomic/agents/char_designer.py` | 系统提示词新增 three_view_prompt 格式 |
| `src/aicomic/agents/scene_designer.py` | 系统提示词新增 multi_view_prompt 格式 |
| `src/aicomic/doubao/browser.py` | ImageResult.file_paths + generate_image 返回全量 |
| `src/aicomic/agents/image_generator.py` | _process_views → _process_entity + _user_select_image |
