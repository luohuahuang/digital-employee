"""
LLM adapter layer: unified call interface for Anthropic and OpenAI.

The two APIs differ in three ways:
  1. Tool definition format (input_schema vs parameters, with/without outer function wrapper)
  2. Message format (system as separate parameter vs role=system message; different tool result format)
  3. Response parsing (content blocks vs choices[0].message)

This module abstracts these differences, providing unified call() interface to upper layers (agent.py):
  - Input: system_prompt, messages (LangGraph format), tool_definitions (internal format)
  - Output: AIMessage in LangGraph format
"""
from __future__ import annotations
from typing import Any

from langchain_core.messages import AIMessage


# ── Unified Response Data Class ─────────────────────────────────────────────────────────────

class LLMResponse:
    """Unified LLM response, abstracting provider differences."""
    def __init__(self, text: str, tool_calls: list[dict],
                 input_tokens: int = 0, output_tokens: int = 0):
        self.text = text
        self.tool_calls = tool_calls  # [{"id": ..., "name": ..., "args": {...}}]
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def to_ai_message(self) -> AIMessage:
        return AIMessage(content=self.text, tool_calls=self.tool_calls)


# ── Message Format Conversion Tools ───────────────────────────────────────────────────────────

def _langgraph_to_anthropic_messages(messages: list) -> list[dict]:
    """Convert LangGraph messages to Anthropic API format."""
    result = []
    for msg in messages:
        if not hasattr(msg, "type"):
            continue
        if msg.type == "tool":
            result.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": str(msg.content),
                }]
            })
        elif msg.type == "ai":
            content: list[Any] = []
            if msg.content:
                content.append({"type": "text", "text": str(msg.content)})
            for tc in (msg.tool_calls or []):
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["args"],
                })
            result.append({"role": "assistant", "content": content})
        else:
            role = "user" if msg.type == "human" else "assistant"
            result.append({"role": role, "content": str(msg.content)})
    return result


def _langgraph_to_openai_messages(system_prompt: str, messages: list) -> list[dict]:
    """Convert system prompt + LangGraph messages to OpenAI API format."""
    result = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        if not hasattr(msg, "type"):
            continue
        if msg.type == "tool":
            # OpenAI tool result: role=tool, requires tool_call_id
            result.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": str(msg.content),
            })
        elif msg.type == "ai":
            oai_msg: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            if msg.tool_calls:
                oai_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": __import__("json").dumps(tc["args"], ensure_ascii=False),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            result.append(oai_msg)
        else:
            role = "user" if msg.type == "human" else "assistant"
            result.append({"role": role, "content": str(msg.content)})
    return result


# ── Tool Definition Format Conversion ───────────────────────────────────────────────────────────

def to_openai_tools(anthropic_defs: list[dict]) -> list[dict]:
    """
    Convert internal (Anthropic format) tool definitions to OpenAI function calling format.

    Anthropic:
      {"name": ..., "description": ..., "input_schema": {...}}

    OpenAI:
      {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
    """
    result = []
    for tool in anthropic_defs:
        result.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            }
        })
    return result


# ── Unified Call Entry Point ───────────────────────────────────────────────────────────────

def call_llm(
    system_prompt: str,
    messages: list,
    tool_definitions: list[dict],   # Internal format (Anthropic format, source of truth)
    model: str,
    provider: str,
    anthropic_api_key: str = "",
    openai_api_key: str = "",
    openai_base_url: str = "",
    max_tokens: int = 4096,
    token_callback=None,   # Optional callable(str) — called with each text delta when streaming
) -> LLMResponse:
    """
    Unified call entry point, dispatches to corresponding implementation based on provider.
    token_callback: if provided and no tool_definitions, use streaming mode and call
                    token_callback(delta) for each text chunk as it arrives.
    """
    if provider == "openai":
        return _call_openai(
            system_prompt, messages, tool_definitions,
            model, openai_api_key, openai_base_url, max_tokens,
            token_callback=token_callback,
        )
    else:
        return _call_anthropic(
            system_prompt, messages, tool_definitions,
            model, anthropic_api_key, max_tokens,
            token_callback=token_callback,
        )


def _call_anthropic(
    system_prompt, messages, tool_definitions,
    model, api_key, max_tokens,
    token_callback=None,
) -> LLMResponse:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    anthropic_messages = _langgraph_to_anthropic_messages(messages)

    # System prompt as a cacheable content block.
    # Anthropic caches everything up to and including the block marked with
    # cache_control.  The cache key IS the content — so any edit to the system
    # prompt (e.g. user updates specialization or memory) automatically
    # invalidates the old cache entry and creates a fresh one on the next call.
    # Minimum 1 024 tokens required; the system prompt easily exceeds that.
    system_blocks = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    create_kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=anthropic_messages,
    )
    if tool_definitions:
        # Mark the last tool definition so Anthropic caches the full tool list.
        # Tools rarely change between turns for the same agent, giving a high
        # cache hit rate.  A copy is made to avoid mutating the shared list.
        tools_with_cache = list(tool_definitions)
        last_tool = dict(tools_with_cache[-1])
        last_tool["cache_control"] = {"type": "ephemeral"}
        tools_with_cache[-1] = last_tool
        create_kwargs["tools"] = tools_with_cache

    # Use streaming when a callback is provided AND no tools (tool_use responses
    # cannot be partially streamed in the same way as plain text).
    use_stream = token_callback is not None and not tool_definitions

    if use_stream:
        text = ""
        with client.messages.stream(**create_kwargs) as stream:
            for delta in stream.text_stream:
                text += delta
                try:
                    token_callback(delta)
                except Exception:
                    pass
        final = stream.get_final_message()
        usage = final.usage
        return LLMResponse(
            text=text, tool_calls=[],
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )

    response = client.messages.create(**create_kwargs)
    text = ""
    tool_calls = []
    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "args": block.input,
            })

    usage = response.usage
    return LLMResponse(
        text=text, tool_calls=tool_calls,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


def _call_openai(
    system_prompt, messages, tool_definitions,
    model, api_key, base_url, max_tokens,
    token_callback=None,
) -> LLMResponse:
    import json
    import openai

    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    client = openai.OpenAI(**kwargs)
    oai_messages = _langgraph_to_openai_messages(system_prompt, messages)
    oai_tools = to_openai_tools(tool_definitions)

    use_stream = token_callback is not None and not oai_tools

    if use_stream:
        stream = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=oai_messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        text = ""
        in_tok = out_tok = 0
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                text += delta
                try:
                    token_callback(delta)
                except Exception:
                    pass
            if chunk.usage:
                in_tok  = chunk.usage.prompt_tokens or 0
                out_tok = chunk.usage.completion_tokens or 0
        return LLMResponse(text=text, tool_calls=[], input_tokens=in_tok, output_tokens=out_tok)

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=oai_messages,
        tools=oai_tools if oai_tools else openai.NOT_GIVEN,
        tool_choice="auto" if oai_tools else openai.NOT_GIVEN,
    )

    msg   = response.choices[0].message
    usage = response.usage
    text  = msg.content or ""
    tool_calls = []

    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                # On parse failure, don't silently swallow error—return special args with error explanation,
                # execute_tool will feed error back to Agent to trigger retry or escalation
                args = {
                    "__parse_error__": (
                        f"Tool arguments JSON parse failed: {e}. "
                        f"First 200 chars of original: {tc.function.arguments[:200]}"
                    )
                }
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "args": args,
            })

    return LLMResponse(
        text=text, tool_calls=tool_calls,
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
    )
