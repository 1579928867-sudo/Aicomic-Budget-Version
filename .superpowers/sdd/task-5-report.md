# Task 5: OutfitManager Agent — Report

## Status

Complete.

## Commits

- `df5e00c` `feat(outfit-manager): new agent for outfit change detection and matching`

## Test Summary

- Module loads correctly via `from aicomic.agents.outfit_manager import OutfitManagerAgent, OutfitDecision, _OUTFIT_CHANGE_KEYWORDS`
- `agent_name` resolves to `"outfit-manager"`
- `_OUTFIT_CHANGE_KEYWORDS` list has 23 entries
- `OutfitDecision` dataclass instantiates and prints correctly
- Import via full module path works (same pattern as existing agents)

## File Created

- `D:/first_agent/src/aicomic/agents/outfit_manager.py` (345 lines)

## Fix report

Commit: `30ba246` `fix(outfit-manager): refactor execute, fix import placement, remove unused param, add error logging`

All five changes applied to `src/aicomic/agents/outfit_manager.py`:

### Fix 1 (Critical) — Refactor execute()
Extracted two helper methods:
- `_resolve_character_name(char_id, db) -> str` — replaces inline `db.conn.execute()` character name lookup
- `_apply_outfit_decision(decision, char_id, shot_id, char_current_tags, db, char_name) -> tuple[int, int]` — handles the three decision branches (None/existing/new), returns (outfits_generated_delta, shots_tagged_delta)

Simplified `execute()` from ~110 lines to ~45 lines of real logic. The loop body now calls `_resolve_character_name()` and delegates branch handling to `_apply_outfit_decision()`.

### Fix 2 (Medium) — Move `import json` to top of file
Removed the inline `import json` inside the `for shot in shots:` loop (was at line 272). Added `import json` at module level with standard library imports (`from dataclasses import dataclass, import json, from typing import Any`).

### Fix 3 (Medium) — Remove unused `current_tag` parameter from `detect_outfit_change()`
The `current_tag` parameter was passed in but never referenced in the method body. Removed it from the signature and updated the single caller in `execute()`.

### Fix 4 (Low) — Add `db.log()` before `except Exception: return None` in `_llm_detect_outfit()`
Added `db.log(self.agent_name, -1, "llm_detect_error", ...)` in the except block. Also added `db` parameter to the method signature.

### Fix 5 (Low) — Add `db.log()` before `except Exception: return ""` in `_generate_outfit_prompt()`
Added `db.log(self.agent_name, -1, "generate_prompt_error", ...)` in the except block. Also added `db` parameter to the method signature.

### Verification
```
import sys; sys.path.insert(0,'src'); from aicomic.agents.outfit_manager import OutfitManagerAgent, OutfitDecision, _OUTFIT_CHANGE_KEYWORDS; print('OK'); print('agent:', OutfitManagerAgent.agent_name)
```
Output: `OK` / `agent: outfit-manager`

## Implementation Details

- **Agent class**: `OutfitManagerAgent(AgentInterface)` with `agent_name = "outfit-manager"`
  - `validate_input()`: checks `chapter_id` and `script_id` are `int`
  - `execute()`: full pipeline that scans all shots per chapter, detects outfit changes at scene transitions, creates new outfit records, and tags shots
  - `detect_outfit_change()`: keyword pre-filter → activation_condition check → LLM fallback
  - `get_active_outfit()`: resolves active outfit by tag or falls back to default
  - `_has_outfit_keywords()`: fast string-in-list check (~23 keywords)
  - `_llm_detect_outfit()`: calls `self.llm.generate_json()` with `OUTFIT_DETECTOR_SYSTEM_PROMPT`
  - `_generate_outfit_prompt()`: generates design prompt for new outfits via `OUTFIT_PROMPT_GENERATOR_SYSTEM_PROMPT`

- **DB interface**: Uses `db.get_character_outfit()`, `db.get_character_outfits()`, `db.create_character_outfit()`, `db.update_shot_outfit_tag()`, `db.conn.execute()` (from Task 2 repository)

- **Key patterns**:
  - Scene-transition throttling: only runs detection when `scene_id` changes (or for first shot of each character)
  - Existing outfit matching: first checks `activation_condition` substring match; then `tag` match post-LLM
  - New outfits: generates `design_prompt` via LLM before creating DB record
  - `char_ids` parsed via `json.loads()` same as `shot_video_generator.py`
  - Full idempotency check via `db.get_agent_status()` at start

## Concerns

- `import json` is placed inside the `for shot in shots:` loop in `execute()` (same pattern as the brief specifies). For style consistency with other agents it could be top-level, but this works and follows the brief.
- No integration test was run (requires a live database with character_outfit + storyboard_shot tables and an LLM client). Unit-level verification confirms the module loads and types are correct.
- The agent assumes `db.conn` is available for direct SQL queries (used for character name lookup). This follows the pattern established in `shot_video_generator.py`.
