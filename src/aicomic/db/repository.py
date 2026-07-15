"""Database abstraction layer over SQLite."""

import json
from pathlib import Path
from typing import Any

import sqlite3


class Database:
    """SQLite-backed knowledge base for the multi-agent framework."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

    def connect(self):
        """Open connection with WAL mode and foreign keys enabled."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_schema(self):
        """Create all tables if they do not exist."""
        if not self.conn:
            raise RuntimeError("Database not connected. Call connect() first.")

        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS novel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chapter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id INTEGER NOT NULL REFERENCES novel(id),
                chapter_num INTEGER NOT NULL,
                raw_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'idle',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS script (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL REFERENCES chapter(id),
                raw_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS storyboard_shot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_id INTEGER NOT NULL REFERENCES script(id),
                shot_num INTEGER NOT NULL,
                narration TEXT DEFAULT '',
                dialogue TEXT DEFAULT '',
                camera_movement TEXT DEFAULT 'static',
                duration_sec REAL NOT NULL DEFAULT 8.0,
                char_ids TEXT DEFAULT '[]',
                scene_id INTEGER,
                image_prompt TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS character_card (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                default_look_id INTEGER REFERENCES appearance_variant(id),
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS appearance_variant (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL REFERENCES character_card(id),
                variant_name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'default',
                applies_to TEXT DEFAULT '{}',
                appearance_json TEXT NOT NULL DEFAULT '{}',
                front_view TEXT DEFAULT '',
                side_view TEXT DEFAULT '',
                back_view TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scene_card (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                lighting TEXT DEFAULT '',
                style TEXT DEFAULT '',
                wide_view TEXT DEFAULT '',
                mid_view TEXT DEFAULT '',
                close_view TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS video_clip (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shot_id INTEGER NOT NULL REFERENCES storyboard_shot(id),
                file_path TEXT NOT NULL DEFAULT '',
                duration_sec REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS final_video (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL REFERENCES chapter(id),
                file_path TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                chapter_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                detail TEXT DEFAULT '{}',
                level TEXT NOT NULL DEFAULT 'INFO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    def migrate_schema(self):
        """Run idempotent migrations for schema upgrades (v0.2 → v0.3, etc.)."""
        if not self.conn:
            raise RuntimeError("Database not connected. Call connect() first.")

        migrations = [
            # v0.3: add image_prompt column to storyboard_shot
            "ALTER TABLE storyboard_shot ADD COLUMN image_prompt TEXT DEFAULT ''",
            # v0.4: add duration_sec column to video_clip
            "ALTER TABLE video_clip ADD COLUMN duration_sec REAL NOT NULL DEFAULT 0.0",
        ]
        for sql in migrations:
            try:
                self.conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists
        self.conn.commit()

    # ── Novel ──

    def create_novel(self, title: str, author: str = "") -> int:
        cursor = self.conn.execute(
            "INSERT INTO novel (title, author) VALUES (?, ?)",
            (title, author),
        )
        self.conn.commit()
        return cursor.lastrowid

    # ── Chapter ──

    def create_chapter(
        self, novel_id: int, chapter_num: int, raw_text: str
    ) -> int:
        cursor = self.conn.execute(
            "INSERT INTO chapter (novel_id, chapter_num, raw_text) VALUES (?, ?, ?)",
            (novel_id, chapter_num, raw_text),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_chapter(self, chapter_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM chapter WHERE id = ?", (chapter_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    # ── Script ──

    def save_script(self, chapter_id: int, raw_json: dict) -> int:
        cursor = self.conn.execute(
            "INSERT INTO script (chapter_id, raw_json, status) VALUES (?, ?, 'done')",
            (chapter_id, json.dumps(raw_json, ensure_ascii=False)),
        )
        self.conn.commit()
        return cursor.lastrowid

    # ── Storyboard Shots ──

    def save_storyboard_shots(
        self, script_id: int, shots: list[dict]
    ) -> list[int]:
        ids = []
        for shot in shots:
            cursor = self.conn.execute(
                """INSERT INTO storyboard_shot
                   (script_id, shot_num, narration, dialogue,
                    camera_movement, duration_sec, char_ids, scene_id, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'done')""",
                (
                    script_id,
                    shot["shot_num"],
                    shot.get("narration", ""),
                    shot.get("dialogue", ""),
                    shot.get("camera_movement", "static"),
                    shot.get("duration_sec", 8.0),
                    json.dumps(shot.get("char_ids", []), ensure_ascii=False),
                    shot.get("scene_id"),
                ),
            )
            ids.append(cursor.lastrowid)
        self.conn.commit()
        return ids

    def get_storyboard_shots(self, script_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM storyboard_shot WHERE script_id = ? ORDER BY shot_num",
            (script_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_shot_image_prompt(self, shot_id: int, image_prompt: str):
        """Update the image_prompt field on a storyboard shot."""
        self.conn.execute(
            "UPDATE storyboard_shot SET image_prompt = ? WHERE id = ?",
            (image_prompt, shot_id),
        )
        self.conn.commit()

    # ── Video Clips ──

    def create_video_clip(self, shot_id: int, file_path: str, duration_sec: float) -> int:
        """Create a video_clip row. Returns the new clip id."""
        cursor = self.conn.execute(
            """INSERT INTO video_clip (shot_id, file_path, duration_sec, status)
               VALUES (?, ?, ?, 'done')""",
            (shot_id, file_path, duration_sec),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_video_clips_for_shot(self, shot_id: int) -> list[dict]:
        """Get all video_clip rows for a given shot (used for idempotency)."""
        rows = self.conn.execute(
            "SELECT * FROM video_clip WHERE shot_id = ? ORDER BY id",
            (shot_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_video_clips(self, script_id: int) -> list[dict]:
        """Get all video_clip rows for a script, joined via storyboard_shot."""
        rows = self.conn.execute(
            """SELECT vc.* FROM video_clip vc
               JOIN storyboard_shot ss ON vc.shot_id = ss.id
               WHERE ss.script_id = ?
               ORDER BY ss.shot_num""",
            (script_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ── Character ──

    def get_or_create_character(self, name: str) -> tuple[int, bool]:
        row = self.conn.execute(
            "SELECT id FROM character_card WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["id"], False
        cursor = self.conn.execute(
            "INSERT INTO character_card (name, status) VALUES (?, 'pending')",
            (name,),
        )
        self.conn.commit()
        return cursor.lastrowid, True

    # ── Scene ──

    def get_or_create_scene(self, name: str) -> int:
        row = self.conn.execute(
            "SELECT id FROM scene_card WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["id"]
        cursor = self.conn.execute(
            "INSERT INTO scene_card (name, status) VALUES (?, 'pending')",
            (name,),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_scene_card(
        self,
        scene_id: int,
        description: str,
        lighting: str,
        style: str,
        wide_view: str = "",
        mid_view: str = "",
        close_view: str = "",
    ):
        """Update scene_card with generated descriptions and multi-angle view prompts."""
        self.conn.execute(
            """UPDATE scene_card
               SET description = ?, lighting = ?, style = ?,
                   wide_view = ?, mid_view = ?, close_view = ?,
                   status = 'done'
               WHERE id = ?""",
            (description, lighting, style, wide_view, mid_view, close_view, scene_id),
        )
        self.conn.commit()

    def get_scene_by_name(self, chapter_id: int, name: str) -> dict | None:
        """Get scene_card row by name (scenes are global, not chapter-scoped)."""
        row = self.conn.execute(
            "SELECT * FROM scene_card WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    # ── Appearance Variants ──

    def get_character_variants(self, character_id: int) -> list[dict]:
        """Get all existing appearance variants for a character."""
        rows = self.conn.execute(
            """SELECT * FROM appearance_variant
               WHERE character_id = ? ORDER BY id""",
            (character_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_appearance_variant(
        self,
        character_id: int,
        variant_name: str,
        variant_type: str,
        appearance_json: str,
    ) -> int:
        """Create an appearance_variant row. Returns the new variant id."""
        cursor = self.conn.execute(
            """INSERT INTO appearance_variant
               (character_id, variant_name, type, appearance_json, status)
               VALUES (?, ?, ?, ?, 'done')""",
            (character_id, variant_name, variant_type, appearance_json),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_appearance_variant_views(
        self, variant_id: int, front: str, side: str, back: str
    ):
        """Update front/side/back view prompts on an appearance variant."""
        self.conn.execute(
            """UPDATE appearance_variant
               SET front_view = ?, side_view = ?, back_view = ?
               WHERE id = ?""",
            (front, side, back, variant_id),
        )
        self.conn.commit()

    def set_character_default_look(self, character_id: int, variant_id: int):
        """Set the default_look_id on a character_card."""
        self.conn.execute(
            "UPDATE character_card SET default_look_id = ? WHERE id = ?",
            (variant_id, character_id),
        )
        self.conn.commit()

    # ── Agent Status (幂等性基础) ──

    def get_agent_status(self, agent_name: str, chapter_id: int) -> str | None:
        row = self.conn.execute(
            """SELECT detail FROM task_log
               WHERE agent_name = ? AND chapter_id = ? AND event = 'status'
               ORDER BY id DESC LIMIT 1""",
            (agent_name, chapter_id),
        ).fetchone()
        if row is None:
            return None
        detail = json.loads(row["detail"])
        return detail.get("status")

    def set_agent_status(
        self, agent_name: str, chapter_id: int, status: str
    ):
        self.conn.execute(
            """INSERT INTO task_log (agent_name, chapter_id, event, detail, level)
               VALUES (?, ?, 'status', ?, 'INFO')""",
            (
                agent_name,
                chapter_id,
                json.dumps({"status": status}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    # ── Logging ──

    def log(
        self,
        agent_name: str,
        chapter_id: int,
        event: str,
        detail: dict | None = None,
        level: str = "INFO",
    ):
        self.conn.execute(
            """INSERT INTO task_log (agent_name, chapter_id, event, detail, level)
               VALUES (?, ?, ?, ?, ?)""",
            (
                agent_name,
                chapter_id,
                event,
                json.dumps(detail or {}, ensure_ascii=False),
                level,
            ),
        )
        self.conn.commit()
