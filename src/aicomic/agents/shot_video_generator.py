"""Shot Video Generator Agent — generates video clips per storyboard shot.

Reuses the Doubao text-to-image page: pastes the shot's reference images
(character design sheet + scene multi-view) and sends a prompt starting with
a copyright declaration followed by "生成视频，Xs，...".

The prompt structure (copyright → instruction → visual description → motion →
atmosphere → quality → numbered ref descriptions → 原比例) has been proven
to pass Doubao's content filter.

v0.9: Character images come from character_outfit (single design sheet),
not appearance_variant (face closeup + three-view).

Interactive mode (half-auto): user selects from generated candidates via CLI,
same as ImageGenerator's selection flow.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database
from .prompt_utils import normalize_prompt_terms, parse_char_ids, user_select_candidate


class ShotVideoGeneratorAgent(AgentInterface):
    """Generates video clips per storyboard shot via image-to-video on Doubao.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"clips_created": int, "total_shots": int}

    Pipeline position: after ShotVisualizer, before VideoComposer.
    Only runs when --with-video is passed and video_backend is "doubao".
    v0.9: Uses single character design sheet images (not face closeup + three-view).
    """

    agent_name = "shot-video-generator"

    # 免费用户豆包每日3次视频额度
    DEFAULT_MAX_CLIPS_PER_RUN = 3

    # ── Preflight: video-specific 3-point check (browser+cookie already
    #     verified by image generation — skip to video-only selectors) ──

    def _preflight_browser(self, chapter_id: int, db: Database) -> str | None:
        """Video-phase diagnostic — 12s max. Only checks what image gen doesn't.

        Checkpoints (retried 3x with 1s delays for lazy React rendering):
        A. Video tab     — 「视频」tab exists + clickable?
        B. File input    — hidden <input type=file> accepting images?
        C. Send button   — #flow-end-msg-send or equivalent?

        Returns None if all pass, or error string with [Check X/3 失败] + fix.
        """
        import time as _time

        page = None
        try:
            page = self.browser._context.new_page()
            page.set_default_timeout(15000)
            page.goto("https://www.doubao.com/chat/create-image",
                      wait_until="domcontentloaded", timeout=15000)
            _time.sleep(2.0)

            if "login" in page.url.lower() or "passport" in page.url.lower():
                return ("[Check A/3 失败] 豆包 Cookie 已过期 → "
                        "前往「豆包Cookie」页面重新登录")

            # ── Check A: Video tab (retry 3x — React lazy render) ──
            tab_found = None
            for attempt in range(3):
                tab_found = page.evaluate("""() => {
                    const all = document.querySelectorAll(
                        '[data-slot="tabs-trigger"], [role="tab"], '
                        + 'button, [role="button"], [class*="tab"]');
                    for (const t of all) {
                        const txt = (t.textContent || '').trim();
                        if (txt === '视频' || txt.startsWith('视频')) {
                            const r = t.getBoundingClientRect();
                            return r.width > 0 && r.height > 0 ? 'visible' : 'hidden';
                        }
                    }
                    return 'missing';
                }""")
                if tab_found == 'visible':
                    break
                _time.sleep(1.0)
            if tab_found != 'visible':
                detail = f"状态={tab_found}（重试3次）"
                return (f"[Check A/3 失败] 豆包页面未找到可用的「视频」tab（{detail}）→ "
                        "豆包可能改版。请检查豆包页面是否正常显示视频 tab，"
                        "如有异常请截图发给开发者更新选择器。")

            # ── Check B: File input (the one used by set_input_files) ──
            input_found = page.evaluate("""() => {
                const inputs = document.querySelectorAll('input[type="file"]');
                let target = null;
                for (const i of inputs) {
                    const accept = (i.getAttribute('accept') || '').toLowerCase();
                    // The video tab's image upload input
                    if (accept.includes('.jpg') || accept.includes('image/')) {
                        target = {accept: accept.substring(0, 40),
                                  visible: i.offsetParent !== null};
                        break;
                    }
                }
                if (!target) {
                    // Any file input is better than nothing
                    for (const i of inputs) {
                        target = {accept: (i.getAttribute('accept')||'any').substring(0,40),
                                  visible: i.offsetParent !== null};
                        break;
                    }
                }
                return target || {accept: null, visible: false, total: inputs.length};
            }""")
            if not input_found.get('accept'):
                total = input_found.get('total', 0)
                return (f"[Check B/3 失败] 页面无图片上传 input（共 {total} 个 file input 但都不接受图片）→ "
                        "豆包可能改版。请截图发给开发者。")

            # ── Check C: Send button (match _click_send_button's 3 strategies) ──
            send_found = page.evaluate("""() => {
                // Strategy 0: known ID
                let btn = document.querySelector('#flow-end-msg-send');
                if (btn && btn.offsetParent !== null) return 'flow-end-msg-send';
                // Strategy 1: CSS selectors
                const css = ['button[class*="send-msg"]', 'button[class*="send-btn"]',
                             'button[class*="bg-g-send-msg"]',
                             'button[aria-label*="发送" i]', 'div[role="button"][aria-label*="发送" i]'];
                for (const sel of css) {
                    btn = document.querySelector(sel);
                    if (btn && btn.offsetParent !== null) return sel.replace(/[\\[\\]"'*]/g,'');
                }
                // Strategy 2: any button near bottom (y>200, small width)
                for (const b of document.querySelectorAll('button, div[role="button"]')) {
                    const r = b.getBoundingClientRect();
                    if (r.width > 10 && r.width < 100 && r.y > 200 && b.offsetParent !== null)
                        return (b.id || b.className || 'button').substring(0, 30);
                }
                return null;
            }""")
            if not send_found:
                return ("[Check C/3 失败] 未找到发送按钮 → "
                        "豆包可能改版。请截图发给开发者。")

            # All passed
            return None

        except Exception as e:
            err = str(e)
            if "timeout" in err.lower():
                return "[Preflight] 豆包页面加载超时 → 网络慢或豆包服务器繁忙"
            return f"[Preflight] 异常: {err[:200]}"
        finally:
            if page:
                try: page.close()
                except Exception: pass

    def __init__(
        self, browser_client: Any, duration_sec: float = 5.0,
        interactive: bool = False,
        max_clips_per_run: int = 3,
    ) -> None:
        """Args:
            browser_client: DoubaoBrowserClient instance (shared across agents).
            duration_sec: Default video duration for each shot (test phase: 5s).
            interactive: If True, open candidates with system player and prompt
                         user to pick one. Default False — auto-selects first.
            max_clips_per_run: Stop after this many new clips per run.
                               0 = no limit. Default 3 (free doubao quota).
        """
        self.browser = browser_client
        self.duration_sec = duration_sec
        self.interactive = interactive
        self.max_clips_per_run = max_clips_per_run

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

    # ── Reference image resolution ──

    def _resolve_reference_images(
        self, db: Database, shot: dict
    ) -> list[dict]:
        """Find reference images for a shot: character design sheets + scene multi-view.

        v0.12: Each character's outfit is resolved independently via the
        shot_character_outfit junction table — no more single-outfit_tag last-wins.

        v0.13: Scans segments text for ALL mentioned character names (not just
        char_ids) to avoid random character generation for off-screen/mentioned
        characters (e.g. "听到门外的少女声音" needs 小姑妈's reference).
        """
        import json as _json

        images: list[dict] = []
        seen_char_ids: set[int] = set()

        # ── Step 1: collect all character names mentioned anywhere in the shot ──
        mentioned_names: set[str] = set()

        # From char_ids
        char_ids = parse_char_ids(shot.get("char_ids"))
        for cid in char_ids:
            char_row = db.conn.execute(
                "SELECT name FROM character_card WHERE id = ?", (cid,)
            ).fetchone()
            if char_row:
                mentioned_names.add(char_row["name"])

        # From segments text (dialogue + action may reference off-screen chars)
        segments_raw = shot.get("segments_json", "[]")
        try:
            segments = _json.loads(segments_raw) if isinstance(segments_raw, str) else segments_raw
        except (_json.JSONDecodeError, TypeError):
            segments = []
        for seg in segments:
            combined = (seg.get("action", "") or "") + " " + (seg.get("dialogue", "") or "")
            # Check all known character names against this segment text
            all_chars = db.conn.execute(
                "SELECT id, name FROM character_card"
            ).fetchall()
            for cr in all_chars:
                if cr["name"] in combined:
                    mentioned_names.add(cr["name"])

        # ── Step 2: resolve ALL mentioned characters to their outfit images ──
        char_outfits = db.get_shot_character_outfits(shot["id"])
        # Build name→id map from all character cards
        name_to_id: dict[str, int] = {}
        all_chars = db.conn.execute(
            "SELECT id, name FROM character_card"
        ).fetchall()
        for cr in all_chars:
            name_to_id[cr["name"]] = cr["id"]

        for name in mentioned_names:
            cid = name_to_id.get(name)
            if cid is None or cid in seen_char_ids:
                continue
            seen_char_ids.add(cid)
            outfit_tag = char_outfits.get(cid)
            outfit = db.get_character_outfit(cid, outfit_tag)
            if not outfit:
                outfit = db.get_character_outfit(cid, None)
            if outfit:
                img_path = outfit.get("image_path", "")
                if img_path and Path(img_path).exists():
                    tag_text = outfit.get("tag", "默认")
                    images.append({
                        "path": img_path,
                        "kind": "role",
                        "label": f"角色：{name}，{tag_text}",
                    })

        # ── Step 3: Scene multi-view image (with real scene name from DB) ──
        scene_id = shot.get("scene_id")
        if scene_id:
            row = db.conn.execute(
                "SELECT name, multi_view_image FROM scene_card WHERE id = ? AND multi_view_image != ''",
                (scene_id,),
            ).fetchone()
            if row and row["multi_view_image"]:
                path = row["multi_view_image"]
                if Path(path).exists():
                    images.append({
                        "path": path,
                        "kind": "scene",
                        "label": f"场景多景别：{row['name']}",
                    })

        # ── Step 4: Apply face grid overlay to role images to bypass
        #     Doubao's "real face detection" filter. Scene images are
        #     left untouched — only character faces need the grid. ──
        from .face_overlay import apply_face_grid
        for ri in images:
            if ri.get("kind") == "role":
                try:
                    grid_path = apply_face_grid(ri["path"])
                    ri["path"] = grid_path
                    ri["label"] += "（网格遮罩）"
                except Exception as e:
                    print(f"    ⚠ 面部网格叠加失败 ({Path(ri['path']).name}): {e}")
                    # Continue with original image — don't fail pipeline

        return images

    # ── Video prompt builder ──

    @staticmethod
    def _clean_dialogue(dialogue: str) -> str:
        """Strip voice/emotion annotations from dialogue for video prompt.

        Storyboard stores:  萧澈（内心，困惑，音色：清朗少年）: 怎么回事……
        Video prompt needs: 萧澈: 怎么回事……

        The annotations (内心/音色/etc) are storyboard metadata — the video
        model may flag them as "voice actor specification" (唇形匹配审核).
        """
        if not dialogue:
            return ""
        import re
        # Remove parenthesized annotations between speaker name and colon
        # "萧澈（内心，困惑，音色：清朗少年）: 怎么回事…" → "萧澈：怎么回事…"
        # Also handles half-width parens: "萧澈(内心):" → "萧澈:"
        cleaned = re.sub(r'[（(][^）)]*[）)]\s*[:：]\s*', '：', dialogue)
        # Clean up double colons
        cleaned = re.sub(r'：+', '：', cleaned)
        return cleaned

    @staticmethod
    def _clean_transition(transition: str) -> str:
        """Strip cross-shot references from transition text.

        Storyboard writes:  衔接镜头2的0-3秒：萧澈坐在床上神色警觉...
        Video prompt needs: 萧澈坐在床上神色警觉，听到门口传来少女声音

        Each shot is generated independently — cross-shot references like
        "衔接镜头N" are noise that confuses the video model.
        """
        if not transition:
            return ""
        import re
        # Strip "衔接镜头N的X-X秒：" prefix (with optional colon variations)
        cleaned = re.sub(
            r'^衔接镜头\d+的[\d\-]+秒[：:]?\s*',
            '',
            transition.strip(),
        )
        # Also strip bare "衔接镜头N" without time range
        cleaned = re.sub(
            r'^衔接镜头\d+\s*[：:]?\s*',
            '',
            cleaned,
        )
        return cleaned.strip()

    def _build_video_prompt(
        self, shot: dict, ref_images: list[dict], db: Database = None
    ) -> str:
        """Build Doubao-approved video prompt mimicking the user-proven format.

        Proven format that passes moderation:
          虚幻引擎 5，4K-60fps，16:9 宽银幕，3D偏写实国漫质感，<角色描述>，<场景描述>
          X‑Xs：<运镜>，<动作>，<对话>，<音效>
          ...
          禁止背景音乐，只保留环境音效与人声对白，全部画面由AI原创

        Key rules:
        - No parentheses anywhere — they flag moderation
        - No square brackets on time ranges
        - Dialogue as "人物独白：..." (monologue) or inline quotes
        - Sound as "音效为..." / "环境音效为..." (natural sentence)
        - All constraints in the closing line only
        """
        import json

        # ── Read segments from DB ──
        segments_json = shot.get("segments_json", "[]")
        try:
            segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
        except (json.JSONDecodeError, TypeError):
            segments = []

        # ── Extract role names & scene name ──
        role_names: list[str] = []
        scene_name = ""
        for ri in ref_images:
            if ri.get("kind") == "role":
                name = ri["label"].replace("角色：", "").split("，")[0].strip()
                if name:
                    role_names.append(name)
            elif ri.get("kind") == "scene":
                scene_name = ri["label"].replace("场景多景别参考图", "").replace("场景多景别：", "").replace("场景：", "").strip()

        # ── Camera label mapping to natural style ──
        _CAMERA_MAP = {
            "特写": "特写", "大特写": "大特写", "近景": "近景镜头",
            "中景": "中景镜头", "全景": "全景镜头", "远景": "远景镜头",
            "Push": "缓慢推镜", "Pull": "缓慢拉远", "Pan": "水平横移",
            "FT": "跟随镜头", "HA": "高角度俯拍", "LA": "低角度仰拍",
            "OTS": "过肩视角", "CU": "特写", "ECU": "大特写",
            "MS": "中景镜头", "LS": "全景镜头",
        }

        parts: list[str] = []

        # ── 1. Opening header: tech specs + character + scene ──
        header = "虚幻引擎 5，4K-60fps，16:9 宽银幕，3D偏写实国漫质感"
        # Build character description from roles
        if role_names:
            char_desc = "、".join(role_names)
            header += f"，{char_desc}"
        # Scene
        if scene_name:
            header += f"，{scene_name}"
        # Universal character constraints in header
        header += "，全程人物面部清晰干净不存在网格线条，全程不带任何字幕"
        parts.append(header)

        # ── 2. Per-segment instructions ──
        if segments and len(segments) == 3:
            for seg in segments:
                time_range = seg.get("time_range", "?")
                time_range = time_range.replace("[", "").replace("]", "").replace("秒", "s").rstrip()
                camera_raw = seg.get("camera", "中景")
                camera = _CAMERA_MAP.get(camera_raw, camera_raw + "镜头")
                action = seg.get("action", "")
                dialogue = seg.get("dialogue")
                sound = seg.get("sound", "")

                # Build segment line
                line = f"{time_range}：{camera}，{action}"

                # Dialogue — use "，人物独白：..." style
                if dialogue:
                    clean = self._clean_dialogue(dialogue)
                    if clean:
                        line += f"，人物独白：{clean}"

                # Sound — natural language format
                if sound:
                    line += f"，音效为{sound}"

                parts.append(line)
        else:
            # Fallback: flat 10s segment
            image_prompt = normalize_prompt_terms(shot.get("image_prompt", ""))
            narration = normalize_prompt_terms(shot.get("narration", ""))
            camera_raw = shot.get("camera_movement", "MS")
            camera = _CAMERA_MAP.get(camera_raw, "中景镜头")
            parts.append(f"0-10s：{camera}，{image_prompt}。{narration}")

        # ── 3. Single closing line — no parentheses ──
        parts.append("禁止背景音乐，只保留环境音效与人声对白，全部画面由AI原创")
        return "\n".join(parts)

    # ── crowd_density → crowd visual description ──
    _CROWD_DESCRIPTIONS: dict[str, str] = {
        "sparse": "场景中数名路人经过，近处1-2人五官清晰可见（通用亚洲面容，非特定人物），"
                  "脚步自然身姿放松；中距离行人面目逐渐模糊；远处偶尔一人形单影只",
        "moderate": "三五成群的人流自然走动，近处（镜头2-3米内）数人面容清晰可辨，"
                    "均为各不相同的通用面容，有人交谈有人驻足；中景人影密集但面目不清；"
                    "远景人头攒动均为剪影轮廓。整体生机勃勃但不拥挤",
        "busy": "热闹喧哗的人群场景——近处（1-3米）5-8人面容清晰，有摊贩有顾客有路人，"
                "各不相同面庞，自然地交谈、手势、走动；中景数十人影密集，个别可辨面容线条；"
                "远景人潮如织均为剪影。整体兴奋忙碌的氛围",
        "packed": "水泄不通的极端拥挤——近处（1-2米）数人挤在画面边缘，面容清晰各不相同，"
                  "有人侧身挤过有人抬头张望；中景人海密集叠压，最前排面容半可见各有不同；"
                  "远景无边无际的人潮剪影。整个画面被人体密度填满",
    }

    def _build_crowd_context(self, shot: dict, db: Database = None) -> str | None:
        """Build background crowd description from script-level crowd_density metadata.

        Priority:
        1. Beat-level crowd_density from segments_json (per-beat granularity)
        2. Scene-level crowd_density from scene_card table
        3. Keyword-based heuristic from scene name (legacy fallback)

        Returns None for "empty" density or if no data available.
        """
        import json

        # ── Priority 1: beat-level from segments ──
        segments_json = shot.get("segments_json", "[]")
        try:
            segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
        except (json.JSONDecodeError, TypeError):
            segments = []
        for seg in segments:
            density = (seg.get("crowd_density") or "").strip()
            if density and density != "empty":
                desc = self._CROWD_DESCRIPTIONS.get(density)
                if desc:
                    return self._format_crowd_prompt(desc)

        # ── Priority 2: scene_card table ──
        if db:
            scene_id = shot.get("scene_id")
            if scene_id:
                row = db.conn.execute(
                    "SELECT crowd_density FROM scene_card WHERE id=? AND crowd_density!=''",
                    (scene_id,),
                ).fetchone()
                if row:
                    density = row["crowd_density"]
                    if density != "empty":
                        desc = self._CROWD_DESCRIPTIONS.get(density)
                        if desc:
                            return self._format_crowd_prompt(desc)

        # ── Priority 3: scene name keyword fallback ──
        # Extract scene name from shot labels (available at call site)
        return None

    @staticmethod
    def _format_crowd_prompt(desc: str) -> str:
        return (
            f"（场景人群环境：{desc}。"
            f"【人群面部规则】近处（3米内）路人需要有清晰但各不相同的通用面容，"
            f"不能出现明星/名人脸，每人五官随机自然；中距离面容简化；远景剪影。"
            f"【群众反应】如剧情中有围观者议论/惊呼/窃窃私语，近处路人应有相应的"
            f"口型微动和表情变化，但始终作为背景角色不可喧宾夺主。"
            f"【绝对禁止】禁止任何两个路人拥有完全相同的面容或服装；"
            f"禁止复制粘贴同一人物到画面其他位置）"
        )

    @staticmethod
    def _is_redundant(narration: str, image_prompt: str) -> bool:
        """Check if narration is largely redundant with image_prompt.

        If >70% of narration's meaningful characters already appear in
        image_prompt, skip it to avoid redundancy-based filtering.
        """
        if not narration or not image_prompt:
            return False
        narr_chars = set(narration) - {" ", "，", "。", "、", "；", "："}
        ip_chars = set(image_prompt) - {" ", "，", "。", "、", "；", "："}
        if not narr_chars:
            return True
        overlap = len(narr_chars & ip_chars)
        if len(narr_chars) < 10:
            return False
        return overlap / len(narr_chars) > 0.7

    @staticmethod
    def _extract_subtitle_lines(dialogue: str) -> str:
        """Format dialogue for natural Chinese subtitles.

        Input:  "萧澈（内心）（困惑）: 怎么回事……\n小姑妈: 你醒了！"
        Output: "萧澈心想："怎么回事……" | 小姑妈："你醒了！"
        """
        if not dialogue:
            return ""
        lines = []
        for line in dialogue.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Parse "Speaker（emotion）: content" or "Speaker: content"
            sep = "：" if "：" in line else ":"
            if sep in line:
                speaker_part, _, content = line.partition(sep)
                speaker_part = speaker_part.strip()
                content = content.strip().strip('"').strip('"').strip("'")

                # Extract speaker name (before first bracket)
                speaker = speaker_part.split("（")[0].split("(")[0].strip()

                # Detect if internal monologue
                is_inner = "内心" in speaker_part

                if is_inner:
                    lines.append(f'{speaker}心想："{content}"')
                else:
                    lines.append(f'{speaker}："{content}"')
        return " | ".join(lines) if lines else ""

    # ── User selection ──

    # ── Main execution ──

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]
        target_shot_num = input_data.get("shot_num")  # None = all, int = single shot
        max_clips = input_data.get("max_clips_per_run", self.max_clips_per_run)

        # ── Read video model preference from settings ──
        try:
            row = db.conn.execute(
                "SELECT value FROM settings WHERE key = 'video_model'"
            ).fetchone()
            video_model = row["value"] if row else "mini"
        except Exception:
            video_model = "mini"

        # ── Idempotency check ──
        # 单镜头重试时 force=True，绕过已完成的幂等检查
        force_run = target_shot_num is not None
        skip = begin_agent_run(self.agent_name, chapter_id, db, {"script_id": script_id}, force=force_run)
        if skip:
            return skip

        # ── Ensure browser is alive on current thread ──
        self.browser.ensure_browser()

        # ── Quick preflight: detect browser/cookie/network issues NOW ──
        preflight_err = self._preflight_browser(chapter_id, db)
        if preflight_err:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "preflight_failed",
                   {"error": preflight_err}, level="ERROR")
            return AgentResult(success=False, error=preflight_err)

        try:
            # ── Load shots with image_prompts ──
            shots = db.get_storyboard_shots(script_id)
            if not shots:
                raise ValueError(f"No storyboard shots for script_id={script_id}")

            # Filter: need image_prompt, and no existing video_clip
            # (单镜头重试时，无视已有 clip，强制重新生成)
            ignore_existing = target_shot_num is not None
            shots_to_generate = []
            already_done = []
            for s in shots:
                sd = dict(s)
                if not sd.get("image_prompt", ""):
                    continue  # No image prompt → skip
                existing = db.get_video_clips_for_shot(sd["id"])
                if existing:
                    if ignore_existing and sd["shot_num"] == target_shot_num:
                        # Delete old clip so it can be regenerated
                        for clip in existing:
                            try:
                                db.conn.execute("DELETE FROM video_clip WHERE id=?", (clip["id"],))
                                # Also delete the file on disk
                                fp = clip.get("file_path", "")
                                if fp:
                                    try:
                                        Path(fp).unlink(missing_ok=True)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        db.conn.commit()
                        shots_to_generate.append(sd)
                        print(f"    🔄 镜头 {sd['shot_num']} 已有视频，已删除旧文件，重新生成")
                    else:
                        already_done.append(sd["shot_num"])
                else:
                    shots_to_generate.append(sd)

            # ── 单镜头筛选：如果指定了 shot_num，只处理该镜头 ──
            if target_shot_num is not None:
                shots_to_generate = [s for s in shots_to_generate if s["shot_num"] == target_shot_num]
                if not shots_to_generate:
                    # Must exist already (filtered to ignore_existing, so not in already_done)
                    raise ValueError(f"镜头 {target_shot_num} 不存在或尚无 image_prompt（需先运行图片生成阶段）")

            if not shots_to_generate:
                db.log(
                    self.agent_name, chapter_id, "skipped",
                    {"reason": "all valid shots already have video clips",
                     "already_done": already_done},
                )
                db.set_agent_status(self.agent_name, chapter_id, "done")
                total = len([s for s in shots if dict(s).get("image_prompt", "")])
                return AgentResult(
                    success=True,
                    data={"clips_created": 0, "total_shots": total, "skipped_all": True},
                )

            total_with_prompts = len([
                s for s in shots if dict(s).get("image_prompt", "")
            ])
            print(
                f"  Shot Video Generator: {len(shots_to_generate)} 个镜头待生成 "
                f"({len(already_done)} 已跳过, 共 {total_with_prompts} 有效)"
            )

            # ── Generate per shot ──
            clips_created = 0
            attempts_this_batch = 0
            consecutive_browser_errors = 0
            succeeded_shot_nums: list[int] = []
            for si, shot in enumerate(shots_to_generate):
                shot_num = shot["shot_num"]

                # ── 额度检查点（尝试次数制，含失败）：每 N 次尝试就暂停 ──
                if max_clips > 0 and attempts_this_batch >= max_clips:
                    remaining = total_with_prompts - clips_created - len(already_done)
                    db.set_agent_status(self.agent_name, chapter_id, "budget_paused")
                    db.log(
                        self.agent_name, chapter_id, "budget_paused",
                        {
                            "clips_created": clips_created,
                            "total_shots": total_with_prompts,
                            "remaining": remaining,
                            "budget_per_run": max_clips,
                            "succeeded_shot_nums": succeeded_shot_nums,
                            "attempts_this_batch": attempts_this_batch,
                        },
                    )
                    succeeded_list = "、".join(f"镜头{n}" for n in succeeded_shot_nums) if succeeded_shot_nums else "无"
                    print(f"\n  ⏸ 额度检查点: 本批次尝试 {attempts_this_batch} 次，成功 {clips_created} 个（每批上限 {max_clips}）")
                    print(f"  ✅ 成功: {succeeded_list}")
                    if remaining > 0:
                        print(f"  📋 剩余 {remaining} 个镜头待生成，请继续下一批次")
                    return AgentResult(
                        success=True,
                        data={
                            "clips_created": clips_created,
                            "total_shots": total_with_prompts,
                            "already_done": len(already_done),
                            "failed_count": attempts_this_batch - clips_created,
                            "status": "budget_paused",
                            "remaining_shots": remaining,
                            "budget_per_run": max_clips,
                            "succeeded_shot_nums": succeeded_shot_nums,
                            "message": f"本批次尝试 {attempts_this_batch} 次，成功生成 {clips_created} 个分镜视频（每批限额 {max_clips}）。{remaining} 个剩余。",
                        },
                    )

                label = f"镜头 {shot_num} ({si+1}/{len(shots_to_generate)})"
                print(f"\n  [{label}]")

                # ── Reset per-shot retry counter ──
                self._retry_count = 0

                ref_images = self._resolve_reference_images(db, shot)

                if not ref_images:
                    db.log(
                        self.agent_name, chapter_id, "shot_skipped_no_refs",
                        {"shot_num": shot_num, "shot_id": shot["id"]},
                        level="WARNING",
                    )
                    print(f"    ⚠ 无参考图片（需先运行 Image Generator），跳过")
                    continue

                print(f"    📎 参考图片: {len(ref_images)} 张")
                for ri in ref_images:
                    path = ri["path"]
                    # Use kind field for reliable type detection
                    if ri.get("kind") == "role":
                        kind = "角色设定图"
                    elif ri.get("kind") == "scene":
                        kind = "场景多景别"
                    else:
                        kind = "参考图"
                    print(f"       [{kind}] {Path(path).name}")

                # Build video prompt with structured ref info
                video_prompt = self._build_video_prompt(
                    shot, ref_images, db
                )
                print(f"    📝 视频提示词 ({len(video_prompt)} 字)")

                # Extract plain paths for browser call
                ref_paths = [ri["path"] for ri in ref_images]

                # Generate
                result = self.browser.generate_video_from_images(
                    prompt=video_prompt,
                    reference_images=ref_paths,
                    duration_sec=float(shot.get("duration_sec", self.duration_sec)),
                    video_model=video_model,
                )

                if not result.success or not result.file_paths:
                    meta = result.metadata if result.success is False else {}
                    reason = (meta or {}).get("reason", "")
                    wrong_type = (meta or {}).get("wrong_type", "")
                    page_text = (meta or {}).get("page_text", "")
                    paste_failed = (meta or {}).get("paste_failed", False)

                    # ── v0.10+: Wrong type retry (image instead of video) ──
                    if wrong_type == "image" and self._retry_count < 1:
                        self._retry_count += 1
                        print(f"    🔀 豆包生成了图片而非视频，改用强化视频提示词重试...")
                        force_video_prompt = "请生成动态视频（video），不要生成静态图片（image）。" + video_prompt
                        if force_video_prompt != video_prompt:
                            time.sleep(5)
                            result = self.browser.generate_video_from_images(
                                prompt=force_video_prompt,
                                reference_images=ref_paths,
                                duration_sec=float(
                                    shot.get("duration_sec", self.duration_sec)
                                ),
                                video_model=video_model,
                            )
                            if result.success and result.file_paths:
                                print(f"    ✓ 重试成功（强化视频模式）")
                                pass
                            else:
                                db.log(
                                    self.agent_name, chapter_id, "shot_video_failed",
                                    {"shot_num": shot_num, "shot_id": shot["id"],
                                     "error": result.error,
                                     "retried": True,
                                     "retry_reason": "wrong_type_image"},
                                    level="WARNING",
                                )
                                print(f"    ✗ 重试仍失败: {result.error}")
                                attempts_this_batch += 1
                                continue
                        else:
                            db.log(
                                self.agent_name, chapter_id, "shot_video_failed",
                                {"shot_num": shot_num, "shot_id": shot["id"],
                                 "error": "wrong_type_image_cannot_adjust"},
                                level="WARNING",
                            )
                            print(f"    ✗ 无法调整 prompt，跳过")
                            attempts_this_batch += 1
                            continue

                    # ── Paste failure: hard stop — don't waste time ──
                    elif paste_failed:
                        msg = (
                            f"镜头 {shot_num}: 参考图粘贴失败（输入区未检测到附件）。"
                            f"中止全部视频生成，请检查豆包页面状态。"
                        )
                        print(f"\n  🛑 {msg}")
                        db.log(
                            self.agent_name, chapter_id, "pipeline_aborted",
                            {"shot_num": shot_num, "shot_id": shot["id"],
                             "reason": "paste_failed"},
                            level="ERROR",
                        )
                        raise RuntimeError(msg)

                    # ── Moderation block: log what Doubao said, don't guess ──
                    elif reason:
                        print(f"    🚫 审核拦截: {reason}")
                        if page_text:
                            # Print first ~500 chars of what Doubao showed
                            snippet = page_text[:500].replace("\n", " ")
                            print(f"    📄 豆包页面内容: {snippet}...")
                        db.log(
                            self.agent_name, chapter_id, "shot_video_failed",
                            {"shot_num": shot_num, "shot_id": shot["id"],
                             "error": result.error, "reason": reason,
                             "page_text_snippet": (page_text or "")[:1000]},
                            level="WARNING",
                        )
                        print(f"    ✗ 跳过（审核拦截，未修改 prompt）")
                        attempts_this_batch += 1
                        consecutive_browser_errors = 0
                        continue

                    else:
                        error_str = str(result.error or "")
                        # ── 浏览器死亡检测：立即中止，不再浪费额度 ──
                        if any(kw in error_str for kw in ("closed", "detached", "aborted", "Target page")):
                            consecutive_browser_errors += 1
                            attempts_this_batch += 1
                            if consecutive_browser_errors >= 2:
                                msg = (
                                    f"⛔ 浏览器已断开（连续 {consecutive_browser_errors} 次错误）。"
                                    f"已生成 {clips_created} 个，剩余镜头中止。请检查豆包页面后重试。"
                                )
                                print(f"\n  {msg}")
                                db.log(
                                    self.agent_name, chapter_id, "pipeline_aborted",
                                    {"shot_num": shot_num, "reason": "browser_dead",
                                     "consecutive_errors": consecutive_browser_errors,
                                     "clips_created": clips_created},
                                    level="ERROR",
                                )
                                return AgentResult(
                                    success=False,
                                    error=f"浏览器已断开：{error_str[:120]}",
                                    data={
                                        "clips_created": clips_created,
                                        "failed_count": attempts_this_batch - clips_created,
                                        "status": "browser_dead",
                                        "succeeded_shot_nums": succeeded_shot_nums,
                                    },
                                )
                        else:
                            consecutive_browser_errors = 0
                        db.log(
                            self.agent_name, chapter_id, "shot_video_failed",
                            {"shot_num": shot_num, "shot_id": shot["id"],
                             "error": result.error},
                            level="WARNING",
                        )
                        print(f"    ✗ 生成失败: {result.error}")
                        attempts_this_batch += 1
                        continue

                # User selection
                paths = result.file_paths
                if len(paths) == 1:
                    chosen = paths[0]
                    print(f"    ✓ 已保存 (仅1个候选) → {Path(chosen).name}")
                else:
                    chosen = user_select_candidate(
                        paths, self.interactive, f"🎬 镜头 #{shot_num}",
                        allow_skip=True, skip_msg=f"跳过镜头 #{shot_num}",
                    )
                    if chosen is None:
                        # Clean up all
                        for p in paths:
                            try:
                                Path(p).unlink(missing_ok=True)
                            except Exception:
                                pass
                        continue

                    # Delete unchosen
                    for p in paths:
                        if p != chosen:
                            try:
                                Path(p).unlink(missing_ok=True)
                            except Exception:
                                pass

                # Save to DB
                try:
                    db.create_video_clip(
                        shot_id=shot["id"],
                        file_path=chosen,
                        duration_sec=float(shot.get("duration_sec", self.duration_sec)),
                    )
                    clips_created += 1
                    attempts_this_batch += 1
                    consecutive_browser_errors = 0
                    succeeded_shot_nums.append(shot_num)
                    print(f"    💾 已保存到数据库 (shot_id={shot['id']})")

                except Exception as e:
                    db.log(
                        self.agent_name, chapter_id, "shot_video_db_error",
                        {"shot_num": shot_num, "error": str(e)},
                        level="ERROR",
                    )
                    print(f"    ✗ 数据库写入失败: {e}")

            # ── Mark status (partial if some failed, so next run can resume) ──
            # 单镜头重试：不覆盖整章状态，设为 partial 允许后续再跑
            if target_shot_num is not None:
                failed_count = 0 if clips_created > 0 else 1
                final_status = "partial" if clips_created > 0 else "failed"
            else:
                failed_count = total_with_prompts - clips_created - len(already_done)
                if clips_created == 0:
                    final_status = "failed"
                elif failed_count > 0:
                    final_status = "partial"
                else:
                    final_status = "done"
            db.set_agent_status(self.agent_name, chapter_id, final_status)
            db.log(
                self.agent_name, chapter_id,
                "completed" if final_status == "done" else "partial",
                {
                    "clips_created": clips_created,
                    "total_shots": total_with_prompts,
                    "already_done": len(already_done),
                    "failed_count": failed_count,
                    "status": final_status,
                    "target_shot_num": target_shot_num,
                },
            )

            return AgentResult(
                success=final_status != "failed",
                data={
                    "clips_created": clips_created,
                    "total_shots": total_with_prompts,
                    "already_done": len(already_done),
                    "failed_count": failed_count,
                    "status": final_status,
                    "target_shot_num": target_shot_num,
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
