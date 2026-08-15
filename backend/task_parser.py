import json
import os

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError


TASK_PARSER_SYSTEM_PROMPT = """\
Convert the user's GitHub project requirements into a JSON object.
Extract every explicit task, domain, framework, hardware constraint, must-have
capability, and preference. The request may be in any language; translate and
normalize every extracted requirement into concise English. If multiple tasks are
explicit, combine them into one concise task phrase without dropping any of them.
Return JSON only, without Markdown or explanation, using exactly these fields:
{
  "task": "string or null",
  "domain": ["string"],
  "framework": ["string"],
  "hardware": ["string"],
  "must_have": ["string"],
  "preferences": ["string"]
}
Use null for an unknown task and empty arrays for categories that are not mentioned.

Example JSON output:
{
  "task": "semantic segmentation",
  "domain": ["drone", "aerial imagery"],
  "framework": ["PyTorch"],
  "hardware": [],
  "must_have": ["custom dataset"],
  "preferences": ["high accuracy"]
}
"""
MIN_DETAILED_QUERY_LENGTH = 20


class TaskParserError(RuntimeError):
    """Raised when a user request cannot be converted into a TaskSpec."""


class TaskSpec(BaseModel):
    """Structured requirements extracted from a user's project request."""

    task: str | None = None
    domain: list[str] = Field(default_factory=list)
    framework: list[str] = Field(default_factory=list)
    hardware: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)


def _is_suspiciously_incomplete(user_query: str, spec: TaskSpec) -> bool:
    extracted_items = sum(
        len(items)
        for items in (
            spec.domain,
            spec.framework,
            spec.hardware,
            spec.must_have,
            spec.preferences,
        )
    )
    return (
        len(user_query.strip()) >= MIN_DETAILED_QUERY_LENGTH
        and (spec.task is None or not spec.task.strip())
        and extracted_items <= 1
    )


def parse_task(
    user_query: str,
    *,
    client: httpx.Client | None = None,
) -> TaskSpec:
    load_dotenv()
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    missing = [
        name
        for name, value in (
            ("LLM_API_KEY", api_key),
            ("LLM_BASE_URL", base_url),
            ("LLM_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise TaskParserError(
            f"LLM configuration is incomplete: missing {', '.join(missing)}"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": TASK_PARSER_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 800,
    }
    should_close_client = client is None
    http_client = client or httpx.Client(timeout=30.0)

    try:
        for attempt in range(2):
            response = http_client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError("message content must be a non-empty string")
            spec = TaskSpec.model_validate(json.loads(content))
            if not _is_suspiciously_incomplete(user_query, spec):
                return spec
            if attempt == 1:
                raise TaskParserError("LLM returned incomplete task requirements")
            payload["messages"] = [
                {"role": "system", "content": TASK_PARSER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Repair the previous JSON because it omitted explicit task "
                        "requirements. Re-extract every explicit requirement from "
                        "the original query into the required schema and return JSON "
                        "only.\n\n"
                        f"Original query:\n{user_query}\n\n"
                        f"Prior JSON:\n{json.dumps(spec.model_dump())}"
                    ),
                },
            ]
    except httpx.HTTPError as exc:
        raise TaskParserError("LLM task parsing request failed") from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise TaskParserError("LLM returned invalid task JSON") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise TaskParserError("LLM returned an invalid response") from exc
    finally:
        if should_close_client:
            http_client.close()
