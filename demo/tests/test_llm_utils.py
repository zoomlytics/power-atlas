"""Tests for demo.llm_utils – capability-aware OpenAILLM construction."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from demo.llm_utils import _model_supports_temperature, build_openai_llm  # noqa: E402


# ---------------------------------------------------------------------------
# _model_supports_temperature
# ---------------------------------------------------------------------------

class TestModelSupportsTemperature:
    """Tests for the capability-detection helper."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo",
            "gpt-4",
            "gpt-4-turbo",
        ],
    )
    def test_standard_models_support_temperature(self, model_name: str) -> None:
        assert _model_supports_temperature(model_name) is True

    @pytest.mark.parametrize(
        "model_name",
        [
            "o1",
            "o1-mini",
            "o1-preview",
            "o1-pro",
            "o3",
            "o3-mini",
            "o3-small",
        ],
    )
    def test_reasoning_models_do_not_support_temperature(self, model_name: str) -> None:
        assert _model_supports_temperature(model_name) is False


# ---------------------------------------------------------------------------
# build_openai_llm
# ---------------------------------------------------------------------------

class TestBuildOpenAILLM:
    """Tests for the OpenAILLM factory."""

    def _make_fake_llm_class(self, captured: dict):
        class _FakeLLM:
            def __init__(self, model_name, model_params=None):
                captured["model_name"] = model_name
                captured["model_params"] = model_params

        return _FakeLLM

    def test_standard_model_receives_temperature_zero(self) -> None:
        captured: dict = {}
        with mock.patch("demo.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("gpt-4o-mini")

        assert captured["model_name"] == "gpt-4o-mini"
        assert captured["model_params"] == {"temperature": 0}

    def test_reasoning_model_omits_temperature(self) -> None:
        captured: dict = {}
        with mock.patch("demo.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("o1-mini")

        assert captured["model_name"] == "o1-mini"
        assert captured["model_params"] == {}

    def test_o3_mini_omits_temperature(self) -> None:
        captured: dict = {}
        with mock.patch("demo.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("o3-mini")

        assert captured["model_name"] == "o3-mini"
        assert captured["model_params"] == {}

    def test_gpt4_retains_temperature_zero(self) -> None:
        captured: dict = {}
        with mock.patch("demo.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("gpt-4")

        assert captured["model_params"] == {"temperature": 0}
