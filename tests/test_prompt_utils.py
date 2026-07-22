"""Tests for shared prompt utilities (content filter term normalization)."""

import pytest
from aicomic.agents.prompt_utils import normalize_prompt_terms, TERM_NORMALIZATIONS


def test_normalize_no_bad_terms():
    """Text without any problematic terms passes through unchanged."""
    text = "萧澈缓缓睁开眼睛，环顾四周，发现自己躺在陌生的床上。"
    assert normalize_prompt_terms(text) == text


def test_normalize_manlian_term():
    """'曼联' (brand match) is replaced with '幔帐' (correct ancient term)."""
    text = "红色曼联在微风中轻轻飘动"
    result = normalize_prompt_terms(text)
    assert "曼联" not in result
    assert "幔帐" in result
    assert result == "红色幔帐在微风中轻轻飘动"


def test_normalize_multiple_occurrences():
    """All occurrences of a bad term are replaced."""
    text = "透过曼联可以看到外面的景色，曼联的流苏垂落下来"
    result = normalize_prompt_terms(text)
    assert result.count("幔帐") == 2
    assert "曼联" not in result


def test_normalize_empty_string():
    """Empty string should return empty string."""
    assert normalize_prompt_terms("") == ""


def test_normalize_no_change_when_clean():
    """A long prompt with no brand collisions stays identical."""
    text = (
        "【中国古代·仙侠】清晨暖光透过雕花窗棂洒入婚房，"
        "红色帷帐在微风中轻轻飘动，远处隐约传来鸟鸣。"
    )
    assert normalize_prompt_terms(text) == text


def test_term_normalizations_dict_is_nonempty():
    """The normalization map should have entries."""
    assert isinstance(TERM_NORMALIZATIONS, dict)
    assert len(TERM_NORMALIZATIONS) > 0
    for k, v in TERM_NORMALIZATIONS.items():
        assert isinstance(k, str) and isinstance(v, str)
        assert k != v, f"Key '{k}' should differ from value — otherwise it's a no-op"
