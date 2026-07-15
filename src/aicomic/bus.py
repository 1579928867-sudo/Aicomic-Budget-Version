"""Agent Bus — registration and dispatch."""

from typing import Any

from .interface import AgentInterface, AgentResult


class AgentBus:
    """Central registry for Agents.

    Agents are registered by name and dispatched via run().
    The Bus handles validation and error wrapping, so the
    Orchestrator only needs to check AgentResult.success.
    """

    def __init__(self):
        self._agents: dict[str, AgentInterface] = {}

    def register(self, agent: AgentInterface):
        """Register an Agent instance.

        Args:
            agent: An AgentInterface implementation.
        """
        self._agents[agent.agent_name] = agent

    def run(
        self, agent_name: str, input_data: dict[str, Any], db: Any
    ) -> AgentResult:
        """Dispatch execution to a registered Agent.

        Args:
            agent_name: Name of the registered Agent.
            input_data: Input dict for the Agent.
            db: Database instance for state read/write.

        Returns:
            AgentResult — check .success to determine outcome.
        """
        agent = self._agents.get(agent_name)
        if agent is None:
            return AgentResult(
                success=False,
                error=f"Agent '{agent_name}' not registered",
            )

        if not agent.validate_input(input_data):
            return AgentResult(
                success=False,
                error=f"Invalid input for agent '{agent_name}'",
            )

        return agent.execute(input_data, db)
