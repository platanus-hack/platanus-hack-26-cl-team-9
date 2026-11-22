"""Bedrock Converse tool-chat adapter against a fake bedrock-runtime client."""

import pytest

from cascadasen.domain.ports import ToolChatError, ToolSpec
from cascadasen.infrastructure.llm_tools import ConverseToolChat, to_converse, tool_chat
from cascadasen.infrastructure.settings import Settings

SPEC = ToolSpec("cut_lines", "Open lines.", {"type": "object", "properties": {"lines": {"type": "array"}}})


class ValidationException(Exception):
    pass


class FakeConverse:
    def __init__(self, content=None, error=None):
        self.content = content if content is not None else [{"text": "hola"}]
        self.error, self.calls = error, []

    def converse(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return {"output": {"message": {"content": self.content}}}


def test_the_request_carries_the_tool_specs_system_and_model_id_as_is():
    client = FakeConverse()
    chat = ConverseToolChat("amazon.nova-pro-v1:0", client)
    out = chat.turn("sistema", [{"role": "user", "text": "hola"}], [SPEC])
    assert out.text == "hola" and out.tool_calls == ()
    call = client.calls[0]
    assert call["modelId"] == "amazon.nova-pro-v1:0" and call["system"] == [{"text": "sistema"}]
    spec = call["toolConfig"]["tools"][0]["toolSpec"]
    assert spec["name"] == "cut_lines" and spec["inputSchema"]["json"]["type"] == "object"


def test_tool_use_blocks_become_tool_calls():
    client = FakeConverse(
        [{"text": "voy"}, {"toolUse": {"toolUseId": "t1", "name": "cut_lines", "input": {"lines": ["R1"]}}}]
    )
    out = ConverseToolChat("m", client).turn("s", [{"role": "user", "text": "corta"}], [SPEC])
    assert out.text == "voy"
    assert [(c.id, c.name, c.arguments) for c in out.tool_calls] == [("t1", "cut_lines", {"lines": ["R1"]})]


def test_history_converts_tool_results_into_one_user_message_with_status():
    history = [
        {"role": "user", "text": "hazlo"},
        {
            "role": "assistant",
            "text": "",
            "tool_calls": [
                {"id": "a", "name": "cut_lines", "arguments": {}},
                {"id": "b", "name": "get_grid_state", "arguments": {}},
            ],
        },
        {"role": "tool", "tool_call_id": "a", "ok": True, "result": {"open_lines": ["R1"]}},
        {"role": "tool", "tool_call_id": "b", "ok": False, "result": "falló"},
        {"role": "assistant", "text": "listo"},
    ]
    msgs = to_converse(history)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [b["toolUse"]["toolUseId"] for b in msgs[1]["content"]] == ["a", "b"]  # no empty text block
    results = [b["toolResult"] for b in msgs[2]["content"]]
    assert [r["status"] for r in results] == ["success", "error"]
    assert results[1]["content"] == [{"json": {"result": "falló"}}]


def test_failures_become_readable_errors_without_internal_detail():
    with pytest.raises(ToolChatError, match="no acepta herramientas"):
        ConverseToolChat("m", FakeConverse(error=ValidationException("secret detail"))).turn("s", [], [SPEC])
    with pytest.raises(ToolChatError, match="no está disponible") as caught:
        ConverseToolChat("m", FakeConverse(error=TimeoutError("host 10.0.0.1"))).turn("s", [], [SPEC])
    assert "10.0.0.1" not in str(caught.value)


def test_tool_chat_needs_the_llm_enabled_with_bedrock_converse():
    client = FakeConverse()
    assert tool_chat(Settings(llm_enabled=False, llm_provider="bedrock-converse"), client) is None
    assert tool_chat(Settings(llm_enabled=True, llm_provider="bedrock"), client) is None
    chat = tool_chat(Settings(llm_enabled=True, llm_provider="bedrock-converse", llm_model="m"), client)
    assert isinstance(chat, ConverseToolChat) and chat.model == "m"


def test_the_log_detail_names_the_aws_error_code_but_the_client_text_stays_generic(caplog):
    class ClientError(Exception):
        def __init__(self, message):
            super().__init__(message)
            self.response = {"Error": {"Code": "AccessDeniedException", "Message": "no access to the model"}}

    with caplog.at_level("WARNING"), pytest.raises(ToolChatError) as caught:
        ConverseToolChat("qwen.x", FakeConverse(error=ClientError("boom"))).turn("s", [], [SPEC])
    assert "AccessDeniedException no access to the model" in caplog.text and "qwen.x" in caplog.text
    assert "AccessDenied" not in str(caught.value)


def test_leaked_tool_call_markup_is_cut_from_the_text():
    leaked = "Ahora cortaré la línea R014:\n\n<｜DSML｜function_calls"
    client = FakeConverse(
        [{"text": leaked}, {"toolUse": {"toolUseId": "t1", "name": "cut_lines", "input": {}}}]
    )
    out = ConverseToolChat("deepseek.v3.2", client).turn("s", [{"role": "user", "text": "corta"}], [SPEC])
    assert out.text == "Ahora cortaré la línea R014:" and len(out.tool_calls) == 1
    assert (
        ConverseToolChat("m", FakeConverse([{"text": "a < b y c > d"}])).turn("s", [], [SPEC]).text
        == "a < b y c > d"
    )
