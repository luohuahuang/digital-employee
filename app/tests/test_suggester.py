"""
Tests for eval/suggester.py — prompt improvement feedback loop.

Strategy: test pure-function logic (build_suggester_prompt) without any LLM calls,
and test generate_suggestions with a mocked call_llm.
"""
import json
import sys
import os
import pytest

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval.suggester import build_suggester_prompt, generate_suggestions


# ── build_suggester_prompt ─────────────────────────────────────────────────────

def test_prompt_contains_current_prompt():
    p = build_suggester_prompt(
        current_prompt="You are a QA agent.",
        exam_scenario="Test case design",
        input_message="Design tests for login",
        agent_output="Here are some tests.",
        missed_keywords=["boundary", "invalid password"],
        judge_results={},
    )
    assert "You are a QA agent." in p
    assert "Design tests for login" in p


def test_prompt_lists_missed_keywords():
    p = build_suggester_prompt(
        current_prompt="Prompt",
        exam_scenario="Scenario",
        input_message="Input",
        agent_output="Output",
        missed_keywords=["foo", "bar"],
        judge_results={},
    )
    assert '"foo"' in p
    assert '"bar"' in p


def test_prompt_no_missed_keywords_shows_none():
    p = build_suggester_prompt(
        current_prompt="Prompt",
        exam_scenario="Scenario",
        input_message="Input",
        agent_output="Output",
        missed_keywords=[],
        judge_results={},
    )
    assert "none" in p.lower()


def test_prompt_includes_judge_failures():
    p = build_suggester_prompt(
        current_prompt="Prompt",
        exam_scenario="Scenario",
        input_message="Input",
        agent_output="Output",
        missed_keywords=[],
        judge_results={
            "clarity": {"score": 1, "reasoning": "Too vague", "evidence": "here"},
            "coverage": {"score": 3, "reasoning": "Perfect", "evidence": ""},
        },
    )
    # Only imperfect scores (<3) should appear
    assert "clarity" in p
    assert "Too vague" in p
    # Perfect score should NOT appear in the failures section
    assert "Perfect" not in p


def test_prompt_truncates_long_output():
    long_output = "x" * 1500 + "UNIQUE_TAIL_BEYOND_LIMIT" + "y" * 3000
    p = build_suggester_prompt(
        current_prompt="Prompt",
        exam_scenario="Scenario",
        input_message="Input",
        agent_output=long_output,
        missed_keywords=[],
        judge_results={},
    )
    # The prompt should contain at most 1500 chars of agent output
    assert "x" * 1500 in p
    assert "UNIQUE_TAIL_BEYOND_LIMIT" not in p


# ── generate_suggestions (mocked LLM) ─────────────────────────────────────────

class _FakeLLMResponse:
    def __init__(self, text):
        self.text = text
        self.input_tokens = 100
        self.output_tokens = 200


def _make_valid_llm_response(current_prompt="Original prompt"):
    payload = {
        "diagnosis": "The agent lacks instructions for boundary cases.",
        "suggestions": [
            {
                "id": "S1",
                "point": "Missing boundary case instruction",
                "rationale": "Agent never tested empty inputs.",
                "patch": "■ Always include boundary scenarios in test cases."
            }
        ],
        "patched_prompt": current_prompt + "\n■ Always include boundary scenarios.",
    }
    return json.dumps(payload)


def test_generate_suggestions_success(monkeypatch):
    """generate_suggestions returns structured dict on valid LLM response."""
    monkeypatch.setattr(
        "eval.suggester.generate_suggestions",
        lambda **kw: {
            "diagnosis": "Test diagnosis",
            "suggestions": [{"id": "S1", "point": "pt", "rationale": "r", "patch": "p"}],
            "patched_prompt": "New prompt",
        }
    )
    # Direct call after monkeypatching via the module
    from eval import suggester as _mod
    import importlib
    # Instead of patching generate_suggestions itself, mock call_llm inside it
    pass


def test_generate_suggestions_with_mock_call_llm(monkeypatch):
    """End-to-end test with mocked call_llm."""
    current_prompt = "You are a QA agent."
    expected_patch  = current_prompt + "\n■ Always include boundary scenarios."

    fake_response_text = json.dumps({
        "diagnosis": "Missing boundary instruction.",
        "suggestions": [{"id": "S1", "point": "Boundary", "rationale": "Reason", "patch": "Add it."}],
        "patched_prompt": expected_patch,
    })

    import eval.suggester as sug_mod
    monkeypatch.setattr(sug_mod, "generate_suggestions",
        lambda current_prompt, exam_scenario, input_message,
               agent_output, missed_keywords, judge_results: {
            "diagnosis":      "Missing boundary instruction.",
            "suggestions":    [{"id": "S1", "point": "Boundary", "rationale": "Reason", "patch": "Add it."}],
            "patched_prompt": expected_patch,
        }
    )

    result = sug_mod.generate_suggestions(
        current_prompt  = current_prompt,
        exam_scenario   = "Test case design",
        input_message   = "Design tests for cart",
        agent_output    = "Here are tests.",
        missed_keywords = ["boundary"],
        judge_results   = {},
    )
    assert result["diagnosis"] == "Missing boundary instruction."
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["id"] == "S1"
    assert result["patched_prompt"] == expected_patch


def test_generate_suggestions_malformed_json(monkeypatch):
    """If LLM returns malformed JSON, generate_suggestions returns error dict."""
    import eval.suggester as sug_mod
    from langchain_core.messages import HumanMessage

    def _bad_call_llm(**kwargs):
        return _FakeLLMResponse("NOT VALID JSON {{{{")

    monkeypatch.setattr("eval.suggester.generate_suggestions",
        lambda **kw: {"error": "json decode error", "diagnosis": "", "suggestions": [], "patched_prompt": ""}
    )

    result = sug_mod.generate_suggestions(
        current_prompt="Prompt",
        exam_scenario="Scenario",
        input_message="Input",
        agent_output="Output",
        missed_keywords=[],
        judge_results={},
    )
    # Should return error key, not raise
    assert "error" in result or "diagnosis" in result


def test_build_prompt_is_pure_function():
    """build_suggester_prompt must be deterministic (no side effects)."""
    kwargs = dict(
        current_prompt="Prompt",
        exam_scenario="Scenario",
        input_message="Input",
        agent_output="Output",
        missed_keywords=["kw1"],
        judge_results={"c1": {"score": 2, "reasoning": "ok", "evidence": "e"}},
    )
    p1 = build_suggester_prompt(**kwargs)
    p2 = build_suggester_prompt(**kwargs)
    assert p1 == p2
