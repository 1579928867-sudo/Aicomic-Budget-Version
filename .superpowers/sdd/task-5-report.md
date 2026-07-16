# Task 5 Report: Orchestrator + CLI — integrate ImageGenerator into pipeline

## Summary

Implemented Task 5 as specified in the task brief. Integrates ImageGeneratorAgent into the orchestrator pipeline as Step 3.5 (between SceneDesigner and ShotVisualizer), adds `--with-images` CLI flag, introduces shared `DoubaoBrowserClient`, and updates DoubaoVideoGenerator to use nested selectors and the shared browser client.

## Changes

### Files Modified

- **`src/aicomic/orchestrator.py`** — Added `with_images: bool = False` parameter to `run_chapter()`. Inserted Step 3.5 (Image Generator) between Scene Designer and Shot Visualizer. Updated `pipeline_completed` log data and return `AgentResult.data` to include image generator status/results.

- **`src/aicomic/main.py`** — Added `--with-images` CLI argument. Resolved `video_backend` early for shared browser_client decision. Created shared `DoubaoBrowserClient` when `with_images or (with_video and video_backend == "doubao")`. Registered `ImageGeneratorAgent` with that client. Updated `DoubaoVideoGenerator` to use nested selectors (`selectors.get("video", {})`) and shared `browser_client`. Updated pipeline label to `v0.6` and steps print. Added `browser_client.close()` in the `finally` block.

- **`tests/test_orchestrator.py`** — Added `_FakeImageGenerator` class and `test_orchestrator_run_chapter_with_images` test. Updated `_register_all_agents` to accept `with_image_generator: bool = False`.

### Plan Ambiguity Resolution

The plan had `video_backend` referenced in the browser_client creation block before it was defined (it was resolved inside the `if with_video:` block). **Resolution:** `video_backend` is now resolved before the browser_client creation block, as documented in the task brief.

Also, the plan's Step 7 for DoubaoVideoGenerator selectors now uses `doubao_cfg.get("selectors", {}).get("video", {})` instead of `doubao_cfg.get("selectors", {})` to match the nested config structure introduced in Task 2.

## Test Results

- 81 passed, 3 skipped (E2E browser tests)
- All 7 orchestrator tests pass (6 existing + 1 new `test_orchestrator_run_chapter_with_images`)
- RED/GREEN workflow followed: test failed initially, passed after orchestrator change

## Commit

```
ebff44a feat: integrate ImageGenerator into pipeline (step 3.5) with --with-images flag
```
