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
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
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
            "o4-mini",
            "o4-mini-high",
        ],
    )
    def test_reasoning_models_do_not_support_temperature(self, model_name: str) -> None:
        assert _model_supports_temperature(model_name) is False

    @pytest.mark.parametrize(
        "model_name",
        [
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-5-pro",
            "gpt-5.4-pro",
        ],
    )
    def test_gpt5_base_variants_do_not_support_temperature(self, model_name: str) -> None:
        assert _model_supports_temperature(model_name) is False

    @pytest.mark.parametrize("model_name", ["gpt-5.1", "gpt-5.2", "gpt-5.4"])
    def test_gpt5_versioned_supports_temperature_when_effort_is_none(
        self, model_name: str
    ) -> None:
        assert _model_supports_temperature(model_name, reasoning_effort="none") is True

    @pytest.mark.parametrize("model_name", ["gpt-5.1", "gpt-5.2", "gpt-5.4"])
    @pytest.mark.parametrize("reasoning_effort", [None, "low", "medium", "high"])
    def test_gpt5_versioned_does_not_support_temperature_without_effort_none(
        self, model_name: str, reasoning_effort: str | None
    ) -> None:
        assert (
            _model_supports_temperature(model_name, reasoning_effort=reasoning_effort) is False
        )


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
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("gpt-4o-mini")

        assert captured["model_name"] == "gpt-4o-mini"
        assert captured["model_params"] == {"temperature": 0}

    def test_reasoning_model_omits_temperature(self) -> None:
        captured: dict = {}
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("o1-mini")

        assert captured["model_name"] == "o1-mini"
        assert captured["model_params"] == {}

    def test_o3_mini_omits_temperature(self) -> None:
        captured: dict = {}
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("o3-mini")

        assert captured["model_name"] == "o3-mini"
        assert captured["model_params"] == {}

    def test_o4_mini_omits_temperature(self) -> None:
        captured: dict = {}
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("o4-mini")

        assert captured["model_name"] == "o4-mini"
        assert captured["model_params"] == {}

    def test_gpt4_retains_temperature_zero(self) -> None:
        captured: dict = {}
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("gpt-4")

        assert captured["model_params"] == {"temperature": 0}

    def test_gpt41_retains_temperature_zero(self) -> None:
        captured: dict = {}
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm("gpt-4.1")

        assert captured["model_params"] == {"temperature": 0}

    @pytest.mark.parametrize(
        "model_name",
        ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-pro", "gpt-5.4-pro"],
    )
    def test_gpt5_base_variants_omit_temperature(self, model_name: str) -> None:
        captured: dict = {}
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm(model_name)

        assert "temperature" not in (captured["model_params"] or {})

    @pytest.mark.parametrize("model_name", ["gpt-5.1", "gpt-5.2", "gpt-5.4"])
    def test_gpt5_versioned_with_effort_none_includes_temperature(
        self, model_name: str
    ) -> None:
        captured: dict = {}
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm(model_name, reasoning_effort="none")

        assert captured["model_params"].get("temperature") == 0
        assert captured["model_params"].get("reasoning_effort") == "none"

    @pytest.mark.parametrize("model_name", ["gpt-5.1", "gpt-5.2", "gpt-5.4"])
    @pytest.mark.parametrize("reasoning_effort", [None, "low", "high"])
    def test_gpt5_versioned_without_effort_none_omits_temperature(
        self, model_name: str, reasoning_effort: str | None
    ) -> None:
        captured: dict = {}
        with mock.patch("power_atlas.llm_utils.OpenAILLM", self._make_fake_llm_class(captured)):
            build_openai_llm(model_name, reasoning_effort=reasoning_effort)

        params = captured["model_params"] or {}
        assert "temperature" not in params
        if reasoning_effort is not None:
            assert params.get("reasoning_effort") == reasoning_effort
        else:
            assert "reasoning_effort" not in params
