# GitHub Repository Environment Fetcher Design

## Scope

Create `backend/compatibility/repository_environment_fetcher.py` to read a fixed
set of environment, dependency, and deployment files from a public GitHub
repository through the GitHub Contents API. The fetcher treats every response as
plain text. It does not clone the repository, execute files, parse requirements,
call an LLM, or perform compatibility analysis.

## Existing Code Reuse

The implementation follows the existing `repo_reader.py` conventions:

- GitHub API root: `https://api.github.com`
- token source: `GITHUB_TOKEN`, loaded through `python-dotenv`
- authentication: `Authorization: Bearer <token>`
- media type: `application/vnd.github+json`
- GitHub API version: `2022-11-28`
- HTTP library: synchronous `httpx.Client`
- injectable client for fully mocked unit tests
- finite request timeout when the fetcher owns the client

The fetcher will reuse the existing GitHub URL and header helpers instead of
creating another authentication implementation. It will define its own
result-oriented error handling because `repo_reader.py` intentionally fails the
whole operation, while this fetcher must isolate failures per file.

## Candidate Files

The fetcher requests only these fixed root paths and does not recursively scan
the repository:

- README candidates: `README.md`, `README`, `README.rst`
- `requirements.txt`
- `pyproject.toml`
- `setup.py`
- `setup.cfg`
- environment candidates: `environment.yml`, `environment.yaml`
- `Dockerfile`
- docker-compose candidates: `docker-compose.yml`, `docker-compose.yaml`
- `Pipfile`
- `runtime.txt`
- `.python-version`

README, environment, and docker-compose candidates are ordered groups. Once one
candidate in a group is found successfully, later candidates in that group are
not requested. A non-404 error does not stop the group: the fetcher records the
error and tries the next candidate.

## Data Flow

`fetch_repository_environment_files(full_name, client=None)` validates the
`owner/repository` format, loads the token, creates or reuses an `httpx.Client`,
and requests each candidate with the GitHub Contents API.

For a successful response, the fetcher validates the JSON payload, checks the
declared decoded file size, decodes Base64 content as UTF-8 with replacement for
invalid bytes, and stores plain text only. The single-file limit is 512 KiB. A
file over that limit is skipped and its reason is recorded; its content is not
returned.

## Result Structure

The function returns a dictionary with:

- `full_name`: normalized `owner/repository`
- `files`: mapping from path to `{content, size, truncated}`
- `found_files`: successfully decoded file paths
- `missing_files`: paths for which GitHub returned 404
- `skipped_files`: entries containing `path` and `reason`
- `errors`: entries containing `path`, `status`, and a sanitized `reason`

No returned field contains the token, Authorization header, environment file
contents from the host, or raw exception/request representations that could
include headers.

## Error Handling

- 404 is normal and is added to `missing_files`.
- 401, 403, 429, 500, 502, 503, and 504 are recorded for that file only.
- Other non-success HTTP responses are also recorded per file.
- connect timeout, read timeout, and connection failures are recorded per file.
- invalid JSON, malformed payloads, unsupported encoding, and decode failures are
  recorded per file.
- There are no retries in this version.
- Missing `GITHUB_TOKEN` and invalid `full_name` are request-level errors because
  no safe GitHub file request can begin.

## Testing

All network calls use `httpx.MockTransport`. Tests cover:

- `README.md` found
- `requirements.txt` found
- 404 handling
- fallback from `README.md` to `README`
- fallback from `environment.yml` to `environment.yaml`
- `Dockerfile` found
- a 500 response without interrupting later files
- timeout handling
- oversized-file handling
- absence of token data from the returned result

After targeted tests pass, the complete backend test suite is run with no real
network access.
