import json

import httpx
import pytest

from task_parser import TaskParserError, TaskSpec, parse_task


def completion_response(content: dict[str, object] | str) -> httpx.Response:
    if not isinstance(content, str):
        content = json.dumps(content)
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ]
        },
    )


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
        assert payload["temperature"] == 0
        system_prompt = payload["messages"][0]["content"]
        assert "every explicit" in system_prompt
        assert "any language" in system_prompt
        assert "concise English" in system_prompt
        assert payload["messages"][1]["content"].startswith(
            "找一个适合无人机语义分割比赛的项目"
        )
        return completion_response(expected)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = parse_task(
        "找一个适合无人机语义分割比赛的项目，使用PyTorch，支持自定义数据集，精度优先",
        client=client,
    )

    assert result.model_dump() == expected


def test_parse_task_repairs_a_suspiciously_incomplete_result(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    query = (
        "Find an image-classification project for medical scans using PyTorch and "
        "CUDA, with custom datasets and high accuracy."
    )
    incomplete = {
        "task": None,
        "domain": [],
        "framework": ["PyTorch"],
        "hardware": [],
        "must_have": [],
        "preferences": [],
    }
    repaired = {
        "task": "image classification",
        "domain": ["medical imaging"],
        "framework": ["PyTorch"],
        "hardware": ["CUDA"],
        "must_have": ["custom dataset"],
        "preferences": ["high accuracy"],
    }
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return completion_response(incomplete if len(payloads) == 1 else repaired)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = parse_task(query, client=client)

    assert result.model_dump() == repaired
    assert len(payloads) == 2
    assert all(payload["temperature"] == 0 for payload in payloads)
    assert all(
        payload["response_format"] == {"type": "json_object"}
        for payload in payloads
    )
    repair_instruction = payloads[1]["messages"][1]["content"]
    assert query in repair_instruction
    assert json.dumps(incomplete) in repair_instruction


def test_parse_task_repairs_whitespace_task_for_long_sparse_query(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    query = "Find a PyTorch project for image classification."
    incomplete = {
        "task": "   ",
        "domain": [],
        "framework": ["PyTorch"],
        "hardware": [],
        "must_have": [],
        "preferences": [],
    }
    repaired = {**incomplete, "task": "image classification"}
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return completion_response(incomplete if attempts == 1 else repaired)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = parse_task(query, client=client)

    assert result.model_dump() == repaired
    assert attempts == 2


def test_parse_task_fails_after_one_incomplete_repair(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    query = "Find a PyTorch computer-vision project that runs on CUDA hardware."
    incomplete = {
        "task": None,
        "domain": [],
        "framework": ["PyTorch"],
        "hardware": [],
        "must_have": [],
        "preferences": [],
    }
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return completion_response(incomplete)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(
        TaskParserError, match="^LLM returned incomplete task requirements$"
    ):
        parse_task(query, client=client)

    assert attempts == 2


def test_parse_task_accepts_short_framework_only_result_without_repair(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    expected = {
        "task": None,
        "domain": [],
        "framework": ["PyTorch"],
        "hardware": [],
        "must_have": [],
        "preferences": [],
    }
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        payload = json.loads(request.content)
        assert payload["temperature"] == 0
        return completion_response(expected)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = parse_task("PyTorch", client=client)

    assert result.model_dump() == expected
    assert attempts == 1


def test_parse_task_raises_clear_error_for_invalid_json(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        return completion_response("not json")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(TaskParserError, match="invalid task JSON"):
        parse_task("semantic segmentation", client=client)
