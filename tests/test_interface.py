"""Tests for core Agent interface types."""

from aicomic.interface import AgentResult


def test_agent_result_success_minimal():
    result = AgentResult(success=True)
    assert result.success is True
    assert result.data is None
    assert result.error is None
    assert result.artifacts == []


def test_agent_result_success_with_data():
    result = AgentResult(
        success=True,
        data={"script_id": 1},
        artifacts=["data/clips/shot_1.mp4"],
    )
    assert result.data == {"script_id": 1}
    assert result.artifacts == ["data/clips/shot_1.mp4"]


def test_agent_result_failure_with_error():
    result = AgentResult(success=False, error="Claude API timeout")
    assert result.success is False
    assert result.error == "Claude API timeout"


def test_agent_result_defaults():
    result = AgentResult(success=True)
    assert result.data is None
    assert result.error is None
    assert isinstance(result.artifacts, list)
    assert len(result.artifacts) == 0
