"""Orchestrator — coordinates the multi-agent pipeline."""

from .interface import AgentResult
from .bus import AgentBus
from .db.repository import Database


class Orchestrator:
    """Coordinates Agent execution through the pipeline.

    For v0.1, the pipeline has only one step: screenwriter.
    Future versions add character, scene, visual, and composer steps.

    Usage:
        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, raw_text)
    """

    def __init__(self, bus: AgentBus, db: Database):
        self.bus = bus
        self.db = db

    def run_chapter(self, chapter_id: int, raw_text: str) -> AgentResult:
        """Run the full pipeline for a single chapter.

        Pipeline steps (v0.1):
            1. Screenwriter — generate script from raw text

        Args:
            chapter_id: ID of the chapter to process.
            raw_text: The raw chapter text.

        Returns:
            AgentResult with the final status.
        """
        self.db.log("orchestrator", chapter_id, "pipeline_started")

        # ── Step 1: Screenwriter ──
        result = self.bus.run(
            "screenwriter",
            {"chapter_id": chapter_id, "raw_text": raw_text},
            self.db,
        )

        if not result.success:
            self.db.log(
                "orchestrator", chapter_id, "pipeline_failed",
                {"failed_at": "screenwriter", "error": result.error},
                level="ERROR",
            )
            return result

        self.db.log(
            "orchestrator", chapter_id, "pipeline_completed",
            {"script_id": result.data.get("script_id") if result.data else None},
        )

        return AgentResult(
            success=True,
            data={"chapter_id": chapter_id, **result.data} if result.data else {"chapter_id": chapter_id},
        )
