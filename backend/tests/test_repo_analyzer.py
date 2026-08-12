import json

import httpx
import pytest

import repo_analyzer
from task_parser import TaskSpec


def _repository_details() -> dict:
    return {
        "full_name": "open-mmlab/mmsegmentation",
        "readme": "# MMSegmentation\nTraining and model zoo documentation.",
        "root_files": ["README.md", "requirements.txt", "configs", "tools"],
        "common_paths": {
            "requirements.txt": True,
            "environment.yml": False,
            "Dockerfile": False,
            "train.py": False,
            "tools/train.py": True,
            "configs/": True,
            "config/": False,
            "datasets/": False,
            "dataset/": False,
            "data/": False,
            "checkpoints/": False,
            "weights/": False,
        },
    }


def test_analyze_repository_returns_validated_profile_and_preserves_file_facts(
    monkeypatch,
):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    model_result = {
        "full_name": "wrong/repository",
        "framework": ["PyTorch"],
        "tasks": ["semantic segmentation"],
        "domains": ["computer vision"],
        "has_training_code": False,
        "training_entry": None,
        "has_custom_dataset_support": True,
        "has_pretrained_weights": True,
        "has_training_code_evidence": {
            "source": "tools/train.py",
            "reason": "The repository contains an explicit training entry point.",
        },
        "has_custom_dataset_support_evidence": {
            "source": "README.md",
            "reason": "README documents custom dataset support.",
        },
        "has_pretrained_weights_evidence": {
            "source": "README.md",
            "reason": "README describes pretrained model weights.",
        },
        "framework_evidence": {
            "source": "README.md",
            "reason": "README identifies PyTorch as the framework.",
        },
        "has_requirements": False,
        "has_environment_file": False,
        "has_docker": False,
        "has_configs": False,
        "has_dataset_code": False,
        "documentation_quality": "good",
        "hardware_notes": "GPU recommended; exact requirement unknown",
        "hardware_notes_evidence": {
            "source": "README.md",
            "reason": "README mentions GPU usage but does not specify a model.",
        },
        "maintenance_notes": "unknown",
        "task_match": "high",
        "strengths": ["complete training documentation"],
        "weaknesses": ["hardware requirements are not explicit"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://llm.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["thinking"] == {"type": "disabled"}
        user_content = payload["messages"][1]["content"]
        assert "semantic segmentation" in user_content
        assert "MMSegmentation" in user_content
        assert "requirements.txt" in user_content
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(model_result)}}
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    task_spec = TaskSpec(task="semantic segmentation", framework=["PyTorch"])

    profile = repo_analyzer.analyze_repository(
        task_spec, _repository_details(), client=client
    )

    assert profile.full_name == "open-mmlab/mmsegmentation"
    assert profile.framework == ["PyTorch"]
    assert profile.task_match == "high"
    assert profile.has_custom_dataset_support is True
    assert profile.has_pretrained_weights is True
    assert profile.has_requirements is True
    assert profile.has_configs is True
    assert profile.has_training_code is True
    assert profile.training_entry == "tools/train.py"
    assert profile.has_training_code_evidence.source == "tools/train.py"
    assert profile.has_custom_dataset_support_evidence.source == "README.md"
    assert profile.has_pretrained_weights_evidence.source == "README.md"
    assert profile.framework_evidence.source == "README.md"
    assert profile.hardware_notes_evidence.source == "README.md"


def test_analyze_repository_requires_llm_configuration(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr(repo_analyzer, "load_dotenv", lambda: None)

    with pytest.raises(repo_analyzer.RepositoryAnalysisError, match="LLM configuration"):
        repo_analyzer.analyze_repository(TaskSpec(), _repository_details())


def test_analyze_repository_rejects_invalid_model_json(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(repo_analyzer.RepositoryAnalysisError, match="invalid JSON"):
        repo_analyzer.analyze_repository(
            TaskSpec(), _repository_details(), client=client
        )


def test_analyze_repository_marks_unsupported_conclusions_unknown_without_evidence(
    monkeypatch,
):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    model_result = {
        "framework": ["PyTorch"],
        "has_training_code": False,
        "has_custom_dataset_support": True,
        "has_pretrained_weights": True,
        "hardware_notes": "RTX 4090 required",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(model_result)}}]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    profile = repo_analyzer.analyze_repository(
        TaskSpec(), _repository_details(), client=client
    )

    assert profile.has_training_code is True
    assert profile.has_training_code_evidence.source == "tools/train.py"
    assert profile.has_custom_dataset_support is None
    assert profile.has_custom_dataset_support_evidence.source == "unknown"
    assert profile.has_pretrained_weights is None
    assert profile.has_pretrained_weights_evidence.source == "unknown"
    assert profile.framework == []
    assert profile.framework_evidence.source == "unknown"
    assert profile.hardware_notes == "unknown"
    assert profile.hardware_notes_evidence.source == "unknown"
