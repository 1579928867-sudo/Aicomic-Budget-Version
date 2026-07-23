"""Core Agent interface types for the multi-agent framework."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Unified return type for all Agent executions.

    Attributes:
        success: Whether the execution succeeded.
        data: Output data dict (e.g. {'script_id': 1}).
        error: Error message if success is False.
        artifacts: List of file paths produced by this Agent run.
    """

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)


def begin_agent_run(
    agent_name: str,
    chapter_id: int,
    db: Any,
    extra_log: dict[str, Any] | None = None,
) -> AgentResult | None:
    """Shared idempotency guard for all agents.

    Called at the top of every agent's execute() method to:
    - Skip if already done (returns AgentResult for early return)
    - Log resuming if previous run was partial
    - Mark running and log started otherwise

    Args:
        agent_name: The agent's self.agent_name value.
        chapter_id: Chapter being processed.
        db: Database instance.
        extra_log: Additional keys for the "started" log entry (e.g. {"script_id": 1}).

    Returns:
        AgentResult(status="skipped") if already done, None if should proceed.
    """
    status = db.get_agent_status(agent_name, chapter_id)
    if status == "done":
        db.log(agent_name, chapter_id, "skipped", {"reason": "already done"})
        return AgentResult(success=True, data={"status": "skipped"})
    if status == "partial":
        db.log(agent_name, chapter_id, "resuming",
               {"reason": "partial completion, retrying failed"})

    db.set_agent_status(agent_name, chapter_id, "running")
    db.log(agent_name, chapter_id, "started", extra_log or {})
    return None


class AgentInterface(ABC):
    """Every Agent must implement this interface.

    Subclasses set `agent_name` as a class-level string.
    """

    agent_name: str

    @abstractmethod
    def validate_input(self, input_data: dict[str, Any]) -> bool:
        """Validate input_data before execution.

        Args:
            input_data: The input dict passed by the orchestrator.

        Returns:
            True if input is valid for this Agent.
        """
        ...

    @abstractmethod
    def execute(self, input_data: dict[str, Any], db: Any) -> AgentResult:
        """Execute the Agent's core logic.

        Args:
            input_data: Validated input data.
            db: Database instance for reading/writing state.

        Returns:
            AgentResult indicating success or failure.
        """
        ...
