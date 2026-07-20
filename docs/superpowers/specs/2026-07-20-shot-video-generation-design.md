# Shot Video Generation — 分镜图生视频设计

**日期**: 2026-07-20
**状态**: 设计中
**目标**: 复用文生图页面，通过粘贴参考图 + 视频提示词，实现分镜级别的图生视频

---

## 1. 背景

当前管线：
- 文生图已成熟：Char Designer → 角色三视图，Scene Designer → 场景多景别，Image Generator → 豆包生成实际图片
- 视频管线有框架（VideoGenerator + VideoComposer）但 `generate_video()` 指向独立视频页面，selector 为占位符，从未实际校准
- 用户实测：在文生图页面粘贴图片 + "生成视频，5s，描述" 即可生产 mp4 视频

本次设计聚焦：为每个分镜（storyboard_shot）生成对应视频片段，达到逐镜头可用的视频素材。

---

## 2. 核心思路

复用 `generate_image()` 所在页面（`doubao.com/chat/create-image`）：
1. 把该 shot 的角色三视图 + 场景多景别图片粘贴进输入框
2. 输入提示词：`"生成视频，5s，[详细动态描述]"`
3. 发送 → 轮询等 `<video>` 元素出现 → 下载 mp4 → 用户选择保留 → 创建 video_clip

## 3. 四大改动模块

| 模块 | 改动 | 优先级 |
|------|------|--------|
| **提示词层** | Char Designer 加强制动漫风格；Scene Designer multi_view 加白线分隔+标签 | P0（先跑，保证素材可用） |
| **浏览器层** | `DoubaoBrowserClient` 新增 `generate_video_from_images()` | P0 |
| **新 Agent** | `ShotVideoGeneratorAgent` 逐镜头搜图片→组提示词→生成→下载 | P0 |
| **集成** | `main.py`、`orchestrator.py`、`settings.yaml` 注册新 Agent | P1 |

---

## 4. 提示词层细节

### 4.1 Character Designer — 动漫风格约束

**文件**: `src/aicomic/agents/char_designer.py`

在 `CHAR_DESIGNER_SYSTEM_PROMPT` 中新增一条规则（插在现有规则 `#8` 之后，旧 `#8` 改为 `#9`）：

```
8. **Art style: 3D 动漫/游戏 CG 风格** — 参考国产 3D 动画（如完美世界、斗破苍穹、
   凡人修仙传、眷思量等）。人物面部特征：
   - 轮廓锋利清晰，下颌线明显，颧骨和眉骨结构感强
   - 五官精致但非写实真人比例——眼睛略大，鼻梁高挺，嘴唇线条分明
   - 皮肤带有 CG 渲染质感，非真实皮肤纹理
   - 头发带有细腻的 3D 建模感，发丝清晰但不追求照片级写实
   禁止：照片级写实、真人比例五官、真实皮肤质感、AI 写真风格
```

所有 prompt 中的 `写实电影感风格` → 改为 `3D动漫电影感风格`（保留在 full_prompt, front/back/side_view_prompt, three_view_prompt 的格式模板中）。

### 4.2 Scene Designer — 多视图白线分隔 + 标签

**文件**: `src/aicomic/agents/scene_designer.py`

修改 `SCENE_DESIGNER_SYSTEM_PROMPT` 规则 `#10` 中 `multi_view_prompt` 的格式：

在原有布局描述后追加：
```
- 不同景别区域之间用粗白线（约 3px）水平分隔，白线从上到下贯穿画面。
- 每个景别区域的左上角标注白色文字标签：
  - 上方区域左上角标注「远景」
  - 中间区域左上角标注「中景」  
  - 下方区域左上角标注「特写」
- 标签文字使用白色无衬线字体，字号适中，清晰可读。
```

同时修改 `multi_view_prompt` 示例，体现白线分隔和标签。

---

## 5. 浏览器层细节

### 5.1 新方法 `generate_video_from_images()`

**文件**: `src/aicomic/doubao/browser.py`

```python
def generate_video_from_images(
    self,
    prompt: str,
    reference_images: list[str],
    duration_sec: float = 5.0,
) -> ImageResult:  # 复用一个 Result 类型，但下载的是 mp4
```

流程：
1. 导航到 `self.page_urls["image"]`
2. 检查登录状态
3. **粘贴图片** — 通过 CDP 将图片写入系统剪贴板，然后 `Ctrl+V` 到 contenteditable
4. 输入提示词
5. 点击发送按钮
6. 轮询检测 `<video>` 元素出现 + 状态关键词（"已生成" / "视频生成好了"）
7. 下载 mp4 文件
8. 返回结果（多条候选 → 多条路径）

### 5.2 图片粘贴（CDP 方案）

```
1. 读取所有 reference_images 为 base64
2. 通过 page.evaluate 在页面执行 JS：
   - 用 fetch + ClipboardItem 写入剪贴板
3. 点击输入框后，page.keyboard.press("Control+v")
```

JS 实现（在页面上下文执行）：
```javascript
async (imageBase64List) => {
  const items = imageBase64List.map(b64 => {
    const byteChars = atob(b64);
    const byteArr = new Uint8Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) byteArr[i] = byteChars.charCodeAt(i);
    return new ClipboardItem({'image/png': new Blob([byteArr], {type: 'image/png'})});
  });
  await navigator.clipboard.write(items);
}
```

注：需要 `BrowserContext.grantPermissions(["clipboard-read", "clipboard-write"])`。

### 5.3 视频完成检测

当前图片检测用 `_has_finished_grid()` → 找 `[class*="image-box-grid"][data-finished="true"]`。

视频生成后，页面出现 `<video>` 元素，而非图片网格。检测策略：

```python
def _has_finished_video(self, page) -> bool:
    """Check if a finished video element exists."""
    return page.evaluate("""() => {
        const video = document.querySelector('video');
        return video !== null && video.readyState >= 2;
    }""")
```

辅助：也检查状态关键词（"已生成"、"视频生成好了"）作为附加信号。

### 5.4 下载

同图片下载逻辑：从 `<video>` 提取 src → HTTP GET（带 cookies）→ 存 `.mp4`。

---

## 6. 新 Agent — ShotVideoGeneratorAgent

**文件**: `src/aicomic/agents/shot_video_generator.py`（新建）

**agent_name**: `"shot-video-generator"`

**输入**: `{"chapter_id": int, "script_id": int}`

**执行流程**:
```
1. 幂等检查
2. 加载所有 storyboard_shot（有 image_prompt）
3. 过滤已生成 video_clip 的 shot
4. 对每个待生成 shot：
   a. 查 char_ids → 找 three_view_image 路径
   b. 查 scene_id → 找 multi_view_image 路径
   c. 组装视频提示词：
      "生成视频，5s，[shot.image_prompt]。
       场景参考多视图：上方为全景（展示完整空间环境），
       中间为中景（展示核心活动区域），下方为特写（展示材质与细节）。
       角色形象参考已附三视图。"
   d. 调用 browser.generate_video_from_images(...)
   e. 用户候选选择（同 ImageGenerator 的 _user_select_image 模式）
   f. db.create_video_clip(shot_id, path, duration)
5. 标记完成
```

**输出**: `{"clips_created": int, "total_shots": int}`

### 6.1 视频提示词格式

```
生成视频，5s，[image_prompt 中的动态描述]。
高质量AI视频，流畅运镜，电影级画面。
场景布局参考：附图为场景多景别设定，白线划分的三个区域分别为
远景（全景）、中景（核心区域）、特写（细节），请结合理解空间结构。
角色形象参考：附图为角色三视图（侧面-正面-背面）。
```

### 6.2 交互模式

半自动（用户选择模式 B）：
- 生成后展示候选视频路径
- 打开系统播放器预览
- CLI 输入选择保留哪一条
- 删除未选中的

---

## 7. 集成

### 7.1 配置文件

`config/settings.yaml`:
```yaml
video:
  shot_video_duration_sec: 5   # 测试阶段固定 5s
```

### 7.2 Pipeline 位置

在 `ShotVisualizer` 之后、`VideoComposer` 之前：

```
Screenwriter → CharDesigner → SceneDesigner → ImageGenerator
→ ShotVisualizer → ShotVideoGenerator → VideoComposer
```

### 7.3 注册

`main.py` 中：
- 导入 `ShotVideoGeneratorAgent`
- 当 `--with-video` + `video_backend == "doubao"` 时，注册到 bus
- 复用共享的 `browser_client`

`orchestrator.py` 中：
- 在 Step 5（Video Generator）之前插入 ShotVideoGenerator
- 旧的 `VideoGeneratorAgent` 暂时保留但不再注册（被替代）

---

## 8. 涉及文件清单

| 文件 | 操作 | 描述 |
|------|------|------|
| `src/aicomic/agents/char_designer.py` | 修改 | 动漫风格约束 + 替换"写实电影感" |
| `src/aicomic/agents/scene_designer.py` | 修改 | multi_view 加白线分隔 + 标签 |
| `src/aicomic/doubao/browser.py` | 修改 | 新增 `generate_video_from_images()` |
| `src/aicomic/agents/shot_video_generator.py` | 新建 | ShotVideoGeneratorAgent |
| `src/aicomic/main.py` | 修改 | 注册新 Agent |
| `src/aicomic/orchestrator.py` | 修改 | 插入 pipeline 步骤 |
| `config/settings.yaml` | 修改 | 新增 `shot_video_duration_sec` |

---

## 9. 未来迭代

- **首尾帧一致性（策略 A）**: 生成 shot N 后截图最后帧，作为 shot N+1 的参考图之一。当前测试阶段暂不实现。
- **10s 上限自动拆分**: 当 shot duration_sec > 10 时自动拆成多个视频片段。当前阶段手动控制。
- **视频提示词 LLM 优化**: 当前的 VideoGeneratorAgent 中的 `_optimize_prompts` 逻辑可复用于生成更丰富的动态描述。
