# Orchestrator 并行化 — 最低限度方案

**状态**: 📋 已设计，暂不推进  
**日期**: 2026-07-31  
**关联**: [[aicomic-v0.13-state]]

## 目标

在不改动 Agent 接口、Bus、DB schema 的前提下，利用两个天然并行窗口，缩短端到端 pipeline 时间约 **2-3 分钟**（~5-10%）。

## 并行窗口

```
窗口1 (Level 1): CharDesigner ‖ SceneDesigner
  前置: Scriptwriter 完成
  隔离: CharDesigner → character_outfit 表, SceneDesigner → scene_card 表（无冲突）

窗口2 (Level 3): OutfitManager ‖ ImageGenerator  
  前置: StoryboardAgent + CharDesigner + SceneDesigner 均完成
  隔离: OutfitManager → shot_character_outfit 表, ImageGenerator → character_outfit.image_path + scene_card images（无冲突）
```

## 实现

仅修改 `orchestrator.py`，约 25 行：

```python
from concurrent.futures import ThreadPoolExecutor

# 窗口1
with ThreadPoolExecutor(max_workers=2) as pool:
    char_future = pool.submit(self.bus.run, "char-designer", {...}, self.db)
    scene_future = pool.submit(self.bus.run, "scene-designer", {...}, self.db)
    char_result = char_future.result()
    scene_result = scene_future.result()

# 窗口2 (仅在 with_images=True 时)
with ThreadPoolExecutor(max_workers=2) as pool:
    outfit_future = pool.submit(self.bus.run, "outfit-manager", {...}, self.db)
    img_future = pool.submit(self.bus.run, "image-generator", {...}, self.db)
    outfit_result = outfit_future.result()
    img_result = img_future.result()
```

## 线程安全

- SQLite WAL mode 支持并发读、单写
- 两个窗口各自写入不同表，无冲突
- 需在 `Database` 类上加 `threading.Lock` 保护 `execute() + commit()` 原子性，或启用 `check_same_thread=False`

## 兼容性

- 续跑检测：每个 Agent 独立调用 `begin_agent_run()`，互不干扰
- 错误处理：任一线程异常 → 捕获后照常记录 `task_log`，不影响另一线程
- 日志输出：两个 Agent 的 print 会交错，可接受

## 不做的事

- 不改 Agent 接口/Bus/DB schema
- 不引入 DAG 引擎或新依赖（`concurrent.futures` 是标准库）
- 不并行 ImageGenerator/ShotVideoGenerator 内部循环（涉及共享浏览器，改造更大，留待下一轮）
