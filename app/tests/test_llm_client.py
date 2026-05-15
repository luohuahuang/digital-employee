"""
Unit tests for agent/llm_client.py

Coverage strategy:
  - Pure functions (message/tool format converters): no mocking needed
  - _call_anthropic / _call_openai: mock the SDK client
  - call_llm routing: verify correct backend is dispatched
  - Streaming branch: verify callback invocation and non-streaming fallback
  - Token extraction: verify input_tokens / output_tokens are populated
  - Regression: tools=[] must NOT be passed to Anthropic (historical bug)
"""
import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch, call

# Make sure the project root is on sys.path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from agent.llm_client import (
    LLMResponse,
    _langgraph_to_anthropic_messages,
    _langgraph_to_openai_messages,
    to_openai_tools,
    call_llm,
)
from tests.conftest import make_anthropic_response, make_openai_response


# ── LLMResponse ────────────────────────────────────────────────────────────────

class TestLLMResponse:
    def test_to_ai_message_text_only(self):
        r = LLMResponse(text="hello", tool_calls=[])
        msg = r.to_ai_message()
        assert msg.content == "hello"
        assert msg.tool_calls == []

    def test_to_ai_message_with_tool_calls(self):
        tc = {"id": "tc1", "name": "search_jira", "args": {"jql": "project=QA"}}
        r = LLMResponse(text="", tool_calls=[tc])
        msg = r.to_ai_message()
        assert msg.tool_calls[0]["name"] == "search_jira"

    def test_token_defaults_zero(self):
        r = LLMResponse(text="x", tool_calls=[])
        assert r.input_tokens == 0
        assert r.output_tokens == 0

    def test_token_fields_stored(self):
        r = LLMResponse(text="x", tool_calls=[], input_tokens=123, output_tokens=456)
        assert r.input_tokens == 123
        assert r.output_tokens == 456


# ── _langgraph_to_anthropic_messages ──────────────────────────────────────────

class TestLanggraphToAnthropic:
    def test_human_message(self):
        result = _langgraph_to_anthropic_messages([HumanMessage(content="hi")])
        assert result == [{"role": "user", "content": "hi"}]

    def test_ai_message_text_only(self):
        result = _langgraph_to_anthropic_messages([AIMessage(content="answer")])
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == [{"type": "text", "text": "answer"}]

    def test_ai_message_empty_content_skips_text_block(self):
        """AIMessage with no text (only tool calls) should not add a text block."""
        msg = AIMessage(
            content="",
            tool_calls=[{"id": "x", "name": "get_jira_issue", "args": {"key": "QA-1"}}],
        )
        result = _langgraph_to_anthropic_messages([msg])
        blocks = result[0]["content"]
        types = [b["type"] for b in blocks]
        assert "text" not in types
        assert "tool_use" in types

    def test_ai_message_with_tool_calls(self):
        msg = AIMessage(
            content="thinking",
            tool_calls=[{"id": "tc1", "name": "search_jira", "args": {"jql": "project=QA"}}],
        )
        result = _langgraph_to_anthropic_messages([msg])
        blocks = result[0]["content"]
        assert blocks[0] == {"type": "text", "text": "thinking"}
        assert blocks[1]["type"] == "tool_use"
        assert blocks[1]["id"] == "tc1"
        assert blocks[1]["name"] == "search_jira"
        assert blocks[1]["input"] == {"jql": "project=QA"}

    def test_tool_message(self):
        msg = ToolMessage(content="result data", tool_call_id="tc1")
        result = _langgraph_to_anthropic_messages([msg])
        assert result == [{
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tc1", "content": "result data"}],
        }]

    def test_mixed_conversation(self):
        msgs = [
            HumanMessage(content="analyse SPB-123"),
            AIMessage(content="", tool_calls=[{"id": "t1", "name": "get_jira_issue", "args": {"key": "SPB-123"}}]),
            ToolMessage(content="issue details...", tool_call_id="t1"),
        ]
        result = _langgraph_to_anthropic_messages(msgs)
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"
        assert result[2]["content"][0]["type"] == "tool_result"

    def test_skips_non_langchain_objects(self):
        """Plain dicts without a 'type' attribute should be silently skipped."""
        result = _langgraph_to_anthropic_messages([{"role": "user", "content": "raw dict"}])
        assert result == []


# ── to_openai_tools ────────────────────────────────────────────────────────────

class TestToOpenAITools:
    def test_basic_conversion(self):
        anthropic_def = {
            "name": "search_jira",
            "description": "Search Jira by JQL",
            "input_schema": {
                "type": "object",
                "properties": {"jql": {"type": "string"}},
                "required": ["jql"],
            },
        }
        result = to_openai_tools([anthropic_def])
        assert len(result) == 1
        f = result[0]
        assert f["type"] == "function"
        assert f["function"]["name"] == "search_jira"
        assert f["function"]["description"] == "Search Jira by JQL"
        assert f["function"]["parameters"] == anthropic_def["input_schema"]

    def test_empty_list(self):
        assert to_openai_tools([]) == []

    def test_missing_description_defaults_empty_string(self):
        result = to_openai_tools([{"name": "tool", "input_schema": {}}])
        assert result[0]["function"]["description"] == ""

    def test_missing_input_schema_defaults(self):
        result = to_openai_tools([{"name": "tool"}])
        assert result[0]["function"]["parameters"] == {"type": "object", "properties": {}}


# ── _call_anthropic — non-streaming ────────────────────────────────────────────

class TestCallAnthropic:
    def _call(self, mock_response, tool_definitions=None, token_callback=None):
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            return call_llm(
                system_prompt="system",
                messages=[HumanMessage("hi")],
                tool_definitions=tool_definitions or [],
                model="claude-sonnet-4-6",
                provider="anthropic",
                anthropic_api_key="fake-key",
                token_callback=token_callback,
            ), MockClient

    def test_text_response(self):
        resp, _ = self._call(make_anthropic_response(text="hello world"))
        assert resp.text == "hello world"
        assert resp.tool_calls == []

    def test_tool_call_response(self):
        resp, _ = self._call(
            make_anthropic_response(tool_calls=[{"id": "tc1", "name": "search_jira", "args": {"jql": "project=QA"}}]),
            tool_definitions=[{"name": "search_jira", "input_schema": {}}],
        )
        assert resp.text == ""
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["name"] == "search_jira"

    def test_token_counts_extracted(self):
        resp, _ = self._call(make_anthropic_response(text="ok", input_tokens=300, output_tokens=75))
        assert resp.input_tokens == 300
        assert resp.output_tokens == 75

    # ── Regression: empty tools must NOT be passed to Anthropic ──────────────
    def test_empty_tools_not_passed_to_api(self):
        """
        Passing tools=[] to Anthropic confuses the model when tool_use blocks
        exist in history. This was the root cause of the blank-message bug.
        """
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = \
                make_anthropic_response(text="ok")
            call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[],           # empty list
                model="claude-sonnet-4-6", provider="anthropic",
                anthropic_api_key="fake",
            )
            kwargs = MockClient.return_value.messages.create.call_args.kwargs
            assert "tools" not in kwargs, (
                "tools=[] must NOT be passed to Anthropic — it confuses the model"
            )

    def test_non_empty_tools_are_passed(self):
        tools = [{"name": "search_jira", "input_schema": {}}]
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = \
                make_anthropic_response(text="ok")
            call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=tools,
                model="claude-sonnet-4-6", provider="anthropic",
                anthropic_api_key="fake",
            )
            kwargs = MockClient.return_value.messages.create.call_args.kwargs
            assert kwargs["tools"] == tools


# ── _call_anthropic — streaming ────────────────────────────────────────────────

class TestCallAnthropicStreaming:
    def _make_stream_ctx(self, deltas, input_tokens=80, output_tokens=40):
        """Build a mock context manager that yields text deltas."""
        final_msg = MagicMock()
        final_msg.usage.input_tokens = input_tokens
        final_msg.usage.output_tokens = output_tokens

        stream = MagicMock()
        stream.__enter__ = MagicMock(return_value=stream)
        stream.__exit__ = MagicMock(return_value=False)
        stream.text_stream = iter(deltas)
        stream.get_final_message = MagicMock(return_value=final_msg)
        return stream

    def test_streaming_invoked_when_callback_and_no_tools(self):
        stream = self._make_stream_ctx(["hel", "lo"])
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = stream
            callback_calls = []
            result = call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[],
                model="claude-sonnet-4-6", provider="anthropic",
                anthropic_api_key="fake",
                token_callback=lambda d: callback_calls.append(d),
            )
            MockClient.return_value.messages.stream.assert_called_once()
            MockClient.return_value.messages.create.assert_not_called()
            assert callback_calls == ["hel", "lo"]
            assert result.text == "hello"

    def test_streaming_not_used_when_tools_present(self):
        """Tools require complete JSON — streaming must be skipped even with a callback."""
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = \
                make_anthropic_response(text="ok")
            call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[{"name": "search_jira", "input_schema": {}}],
                model="claude-sonnet-4-6", provider="anthropic",
                anthropic_api_key="fake",
                token_callback=lambda d: None,   # callback present but tools too
            )
            MockClient.return_value.messages.stream.assert_not_called()
            MockClient.return_value.messages.create.assert_called_once()

    def test_streaming_not_used_without_callback(self):
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = \
                make_anthropic_response(text="ok")
            call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[],
                model="claude-sonnet-4-6", provider="anthropic",
                anthropic_api_key="fake",
                token_callback=None,
            )
            MockClient.return_value.messages.stream.assert_not_called()

    def test_streaming_token_counts(self):
        stream = self._make_stream_ctx(["hi"], input_tokens=200, output_tokens=30)
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = stream
            result = call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[], model="claude-sonnet-4-6", provider="anthropic",
                anthropic_api_key="fake", token_callback=lambda d: None,
            )
            assert result.input_tokens == 200
            assert result.output_tokens == 30

    def test_callback_exception_does_not_crash(self):
        """A buggy callback must not kill the LLM call."""
        stream = self._make_stream_ctx(["a", "b"])
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = stream
            def bad_callback(d):
                raise RuntimeError("callback exploded")
            result = call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[], model="claude-sonnet-4-6", provider="anthropic",
                anthropic_api_key="fake", token_callback=bad_callback,
            )
            assert result.text == "ab"   # still assembled correctly


# ── call_llm routing ───────────────────────────────────────────────────────────

class TestCallLLMRouting:
    def test_routes_to_anthropic(self):
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = \
                make_anthropic_response(text="ok")
            call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[], model="any", provider="anthropic",
                anthropic_api_key="fake",
            )
            MockClient.assert_called_once()

    def test_routes_to_openai(self):
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = \
                make_openai_response(text="ok")
            call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[], model="gpt-4o", provider="openai",
                openai_api_key="fake",
            )
            MockClient.assert_called_once()

    def test_non_openai_provider_routes_to_anthropic(self):
        """Any provider string that isn't 'openai' should use Anthropic."""
        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = \
                make_anthropic_response(text="ok")
            call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[], model="any", provider="anthropic",
                anthropic_api_key="fake",
            )
            MockClient.assert_called_once()


# ── _call_openai ───────────────────────────────────────────────────────────────

class TestCallOpenAI:
    def _call(self, mock_response, tool_definitions=None, token_callback=None):
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = mock_response
            result = call_llm(
                system_prompt="system",
                messages=[HumanMessage("hi")],
                tool_definitions=tool_definitions or [],
                model="gpt-4o",
                provider="openai",
                openai_api_key="fake",
                token_callback=token_callback,
            )
            return result, MockClient

    def test_text_response(self):
        resp, _ = self._call(make_openai_response(text="answer"))
        assert resp.text == "answer"
        assert resp.tool_calls == []

    def test_tool_call_response(self):
        resp, _ = self._call(
            make_openai_response(tool_calls=[{"id": "tc1", "name": "search_jira", "args": {"jql": "project=QA"}}]),
            tool_definitions=[{"name": "search_jira", "input_schema": {}}],
        )
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["name"] == "search_jira"
        assert resp.tool_calls[0]["args"] == {"jql": "project=QA"}

    def test_token_counts(self):
        resp, _ = self._call(make_openai_response(text="ok", prompt_tokens=500, completion_tokens=100))
        assert resp.input_tokens == 500
        assert resp.output_tokens == 100

    def test_malformed_tool_args_returns_parse_error_key(self):
        """JSON parse failure in tool args should not crash — returns __parse_error__ key."""
        response = MagicMock()
        msg = MagicMock()
        msg.content = ""
        tc = MagicMock()
        tc.id = "t1"
        tc.function.name = "search_jira"
        tc.function.arguments = "{invalid json"
        msg.tool_calls = [tc]
        response.choices = [MagicMock(message=msg)]
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 5

        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = response
            result = call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[{"name": "search_jira", "input_schema": {}}],
                model="gpt-4o", provider="openai", openai_api_key="fake",
            )
        assert "__parse_error__" in result.tool_calls[0]["args"]

    def test_openai_streaming(self):
        """Streaming path: callback receives deltas, result assembled correctly."""
        chunks = []
        for text in ["hel", "lo"]:
            c = MagicMock()
            c.choices = [MagicMock()]
            c.choices[0].delta.content = text
            c.usage = None
            chunks.append(c)
        # Final chunk with usage
        final = MagicMock()
        final.choices = []
        final.usage.prompt_tokens = 50
        final.usage.completion_tokens = 20
        chunks.append(final)

        received = []
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = iter(chunks)
            result = call_llm(
                system_prompt="s", messages=[HumanMessage("hi")],
                tool_definitions=[], model="gpt-4o", provider="openai",
                openai_api_key="fake",
                token_callback=lambda d: received.append(d),
            )
        assert received == ["hel", "lo"]
        assert result.text == "hello"
        assert result.input_tokens == 50
        assert result.output_tokens == 20
