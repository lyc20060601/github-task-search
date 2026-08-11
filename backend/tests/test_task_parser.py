import json

import httpx
import pytest

from task_parser import TaskParserError, TaskSpec, parse_task


def test_task_spec_defaults_all_fields_to_empty_values() -> None:
    spec = TaskSpec()

    assert spec.model_dump() == {
        "task": None,
        "domain": [],
        "framework": [],
        "hardware": [],
        "must_have": [],
        "preferences": [],
    }


def test_task_spec_represents_structured_search_requirements() -> None:
    spec = TaskSpec(
        task="semantic segmentation",
        domain=["drone", "aerial imagery"],
        framework=["PyTorch"],
        must_have=["custom dataset"],
        preferences=["high accuracy"],
    )

    assert spec.model_dump() == {
        "task": "semantic segmentation",
        "domain": ["drone", "aerial imagery"],
        "framework": ["PyTorch"],
        "hardware": [],
        "must_have": ["custom dataset"],
        "preferences": ["high accuracy"],
    }


def test_parse_task_returns_structured_task_spec(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    expected = {
        "task": "semantic segmentation",
        "domain": ["drone", "aerial imagery"],
        "framework": ["PyTorch"],
        "hardware": [],
        "must_have": ["custom dataset"],
        "preferences": ["high accuracy"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.method == "POST"
        assert request.url == "https://llm.example.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-api-key"
        assert payload["model"] == "test-model"
        assert payload["response_format"] == {"type": "json_object"}
        assert "JSON" in payload["messages"][0]["content"]
        assert payload["messages"][1]["content"].startswith("找一个适合无人机")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1786435200,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(expected),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = parse_task(
        "找一个适合无人机语义分割比赛的项目，使用PyTorch，支持自定义数据集，精度优先",
        client=client,
    )

    assert result.model_dump() == expected


def test_parse_task_raises_clear_error_for_invalid_json(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1786435200,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "not json"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(TaskParserError, match="invalid task JSON"):
        parse_task("semantic segmentation", client=client)
