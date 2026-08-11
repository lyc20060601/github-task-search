import importlib

import main


def test_github_token_is_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    reloaded_main = importlib.reload(main)

    assert reloaded_main.github_token == "test-token"


def test_llm_config_is_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    reloaded_main = importlib.reload(main)

    assert reloaded_main.llm_api_key == "test-api-key"
    assert reloaded_main.llm_base_url == "https://llm.example.com/v1"
    assert reloaded_main.llm_model == "test-model"
