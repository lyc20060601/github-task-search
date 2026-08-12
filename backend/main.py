import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel

from github_client import (
    GitHubSearchError,
    search_multiple_queries,
    search_repositories,
)
from query_planner import generate_queries
from task_parser import TaskParserError, parse_task


load_dotenv()
github_token = os.getenv("GITHUB_TOKEN")
llm_api_key = os.getenv("LLM_API_KEY")
llm_base_url = os.getenv("LLM_BASE_URL")
llm_model = os.getenv("LLM_MODEL")

LOCAL_FRONTEND_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def get_allowed_origins() -> list[str]:
    origins = list(LOCAL_FRONTEND_ORIGINS)
    production_origin = os.getenv("FRONTEND_ORIGIN", "").strip().rstrip("/")
    if production_origin and production_origin not in origins:
        origins.append(production_origin)
    return origins

app = FastAPI()

# Vercel's multi-service rewrite forwards the service prefix to FastAPI.
vercel_api = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


def register_routes(api: FastAPI) -> None:
    @api.get("/")
    def root() -> dict[str, str]:
        return {"message": "GitHub Task Search API"}

    @api.post("/search")
    def repository_search(request: SearchRequest) -> list[dict[str, Any]]:
        try:
            return search_repositories(request.query)
        except GitHubSearchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.post("/smart-search")
    def smart_repository_search(request: SearchRequest) -> dict[str, Any]:
        try:
            task_spec = parse_task(request.query)
            generated_queries = generate_queries(task_spec)
            repositories = search_multiple_queries(generated_queries)
        except (TaskParserError, GitHubSearchError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return {
            "task_spec": task_spec.model_dump(),
            "generated_queries": generated_queries,
            "repositories": repositories,
        }


class SearchRequest(BaseModel):
    query: str


register_routes(app)
register_routes(vercel_api)
app.mount("/api/backend", vercel_api)
