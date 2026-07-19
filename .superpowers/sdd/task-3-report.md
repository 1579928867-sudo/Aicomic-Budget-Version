# Task 3 Report: Char Designer — three_view_prompt Output

## Status: DONE

### Commit
```
feat(char-designer): add three_view_prompt output for composite character views
```

### Files Modified
- `src/aicomic/agents/char_designer.py` — 265 lines (was 251). 4 changes:

| # | Change | Lines |
|---|--------|-------|
| 1 | Added item 11 (Composite three-view prompt) to `CHAR_DESIGNER_SYSTEM_PROMPT` | 43-47 |
| 2 | Added `three_view_prompt` field to example JSON variant | 79 |
| 3 | Added `three_view_prompt` to `_build_appearance_json` output dict | 261 |
| 4 | Added `db.update_appearance_variant_three_view_prompt(...)` call in `execute()` | 195-199 |

### Verification

```
> py -c "from src.aicomic.agents.char_designer import CharacterDesignerAgent, CHAR_DESIGNER_SYSTEM_PROMPT; print('OK:', len(CHAR_DESIGNER_SYSTEM_PROMPT))"
OK: 6328
```

- Module loads without errors
- AST parse confirms valid Python syntax
- `update_appearance_variant_three_view_prompt` method confirmed present in `repository.py` (line 404)

### Implementation Details

**Step 1 — System prompt item 11:** Appended after item 10's closing line. Instructs LLM to generate a `three_view_prompt`: a single composite prompt describing a left-to-right layout (side, front, back views) on pure white background, with explicit layout description in Chinese, followed by collective appearance details.

**Step 2 — Example JSON:** Added `"three_view_prompt"` after `"back_view_prompt"` in the example variant, following the same indentation and quoting style. The example value demonstrates the composite format with the layout description and collective details.

**Step 3 — `_build_appearance_json`:** Added `"three_view_prompt": variant.get("three_view_prompt", "")` to the appearance dict, after `"back_view_prompt"` and before `"era_background"`. Uses the same `variant.get()` pattern as all other fields.

**Step 4 — DB save:** Added the `db.update_appearance_variant_three_view_prompt()` call after the existing `db.update_appearance_variant_views()` call (v0.5), preserving the chronological ordering of version comments in the code.

### Self-Review

- All existing code and comments remain intact
- The `three_view_prompt` field follows the exact same patterns as `front_view_prompt` / `side_view_prompt` / `back_view_prompt`
- The example prompt text accurately implements the format described in item 11
- No new dependencies or imports introduced
- Method signature matches existing `repository.py` interface

### Concerns / Open Questions

None.
