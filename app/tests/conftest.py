"""
Shared pytest fixtures for llm_client tests.
"""
from unittest.mock import MagicMock


def make_anthropic_response(text="", tool_calls=None, input_tokens=100, output_tokens=50):
    """
    Build a fake anthropic.types.Message object.
    tool_calls: list of {"id", "name", "args"} dicts.
    """
    response = MagicMock()
    content_blocks = []

    if text:
        block = MagicMock()
        block.type = "text"
        block.text = text
        content_blocks.append(block)

    for tc in (tool_calls or []):
        block = MagicMock()
        block.type = "tool_use"
        block.id = tc["id"]
        block.name = tc["name"]
        block.input = tc["args"]
        content_blocks.append(block)

    response.content = content_blocks
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def make_openai_response(text="", tool_calls=None, prompt_tokens=100, completion_tokens=50):
    """
    Build a fake openai ChatCompletion response object.
    tool_calls: list of {"id", "name", "args"} dicts (args already a dict, not JSON string).
    """
    import json

    response = MagicMock()
    msg = MagicMock()
    msg.content = text

    if tool_calls:
        oai_tcs = []
        for tc in tool_calls:
            t = MagicMock()
            t.id = tc["id"]
            t.function.name = tc["name"]
            t.function.arguments = json.dumps(tc["args"])
            oai_tcs.append(t)
        msg.tool_calls = oai_tcs
    else:
        msg.tool_calls = None

    choice = MagicMock()
    choice.message = msg
    response.choices = [choice]
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    return response
