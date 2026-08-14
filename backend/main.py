import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from batch_analyzer import analyze_repositories
from github_client import (
    GitHubSearchError,
    search_multiple_queries,
    search_repositories,
)
from query_planner import generate_queries
from ranking.final_ranking import rank_repositories
from runtime.validation_gateway import (
    COORDINATOR,
    get_validation_status,
    require_worker_token,
    validate_requested_repository,
)
from runtime.validation_jobs import (
    InvalidValidationJob,
    ValidationBusy,
    ValidationJob,
    ValidationJobResult,
    ValidationTimedOut,
    ValidationUnavailable,
)
from runtime_report import RuntimeReport
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
MAX_VALIDATION_RESULT_BYTES = 256 * 1024


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

    @api.post("/recommend-search")
    def recommend_repository_search(request: SearchRequest) -> dict[str, Any]:
        try:
            task_spec = parse_task(request.query)
            generated_queries = generate_queries(task_spec)
            repositories = search_multiple_queries(generated_queries)
        except (TaskParserError, GitHubSearchError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        candidates = repositories[:10]
        analysis_results = analyze_repositories(candidates, task_spec)
        analyzed_count = sum(
            result.get("profile") is not None and result.get("error") is None
            for result in analysis_results
        )
        recommendations = rank_repositories(
            task_spec,
            candidates,
            analysis_results,
        )
        return {
            "task_spec": task_spec.model_dump(),
            "generated_queries": generated_queries,
            "candidate_count": len(repositories),
            "analyzed_count": analyzed_count,
            "recommendations": recommendations,
        }

    @api.post("/validate-repository", response_model=RuntimeReport)
    def validate_public_repository(
        request: ValidateRepositoryRequest,
    ) -> RuntimeReport:
        try:
            return validate_requested_repository(request.full_name)
        except ValidationBusy as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except ValidationUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValidationTimedOut as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc

    @api.get("/validation-status")
    def validation_status() -> dict[str, str | bool]:
        return get_validation_status()

    @api.post(
        "/internal/validation/jobs/next",
        include_in_schema=False,
        response_model=ValidationJob | None,
    )
    def next_validation_job(
        response: Response,
        authorization: str | None = Header(default=None),
    ) -> ValidationJob | None:
        try:
            require_worker_token(authorization)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail="invalid worker credentials") from exc
        COORDINATOR.touch_worker()
        job = COORDINATOR.claim_next(wait_seconds=10)
        if job is None:
            response.status_code = status.HTTP_204_NO_CONTENT
        return job

    @api.post(
        "/internal/validation/jobs/{job_id}/result",
        include_in_schema=False,
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def submit_validation_result(
        job_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Response:
        try:
            require_worker_token(authorization)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail="invalid worker credentials") from exc

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_VALIDATION_RESULT_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="validation result body is too large",
                    )
            except ValueError:
                pass

        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_VALIDATION_RESULT_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="validation result body is too large",
                )

        try:
            result = ValidationJobResult.model_validate_json(body)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid validation result",
            ) from exc

        try:
            COORDINATOR.complete(job_id, result.report)
        except InvalidValidationJob as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str


class ValidateRepositoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


register_routes(app)
register_routes(vercel_api)
app.mount("/api/backend", vercel_api)
