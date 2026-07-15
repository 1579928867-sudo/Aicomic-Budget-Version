"""Tests for AgentBus registration and dispatch."""

from aicomic.interface import AgentInterface, AgentResult
from aicomic.bus import AgentBus


class _FakeAgent(AgentInterface):
    agent_name = "fake"

    def validate_input(self, input_data: dict) -> bool:
        return "name" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        return AgentResult(
            success=True,
            data={"greeting": f"hello {input_data['name']}"},
        )


class _FailingAgent(AgentInterface):
    agent_name = "failer"

    def validate_input(self, input_data: dict) -> bool:
        return True

    def execute(self, input_data: dict, db) -> AgentResult:
        return AgentResult(success=False, error="something broke")


class _StrictValidator(AgentInterface):
    agent_name = "strict"

    def validate_input(self, input_data: dict) -> bool:
        return False

    def execute(self, input_data: dict, db) -> AgentResult:
        return AgentResult(success=True)


def test_bus_register_and_run():
    bus = AgentBus()
    bus.register(_FakeAgent())

    result = bus.run("fake", {"name": "world"}, db=None)
    assert result.success is True
    assert result.data == {"greeting": "hello world"}


def test_bus_run_unregistered_agent():
    bus = AgentBus()
    result = bus.run("nobody", {}, db=None)
    assert result.success is False
    assert "not registered" in result.error


def test_bus_run_failing_agent():
    bus = AgentBus()
    bus.register(_FailingAgent())

    result = bus.run("failer", {}, db=None)
    assert result.success is False
    assert result.error == "something broke"


def test_bus_run_validation_fails():
    bus = AgentBus()
    bus.register(_FakeAgent())

    result = bus.run("fake", {}, db=None)  # No 'name' key
    assert result.success is False
    assert "Invalid input" in result.error


def test_bus_run_strict_validator():
    bus = AgentBus()
    bus.register(_StrictValidator())

    result = bus.run("strict", {}, db=None)
    assert result.success is False
    assert "Invalid input" in result.error
