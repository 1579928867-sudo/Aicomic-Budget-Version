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
