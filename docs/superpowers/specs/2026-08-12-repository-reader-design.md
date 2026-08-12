# Repository Reader Design

## Goal

Add a backend-only `get_repository_details(full_name)` helper that reads a public GitHub repository README and root contents, then reports common project files and directories.

## Design

`repo_reader.py` uses the existing `GITHUB_TOKEN` environment variable and `httpx`. It calls the repository contents endpoint for the root listing and README endpoint for README content, decodes GitHub's Base64 README payload, and checks requested paths against the root/tree listing. The returned dictionary contains `full_name`, `readme`, `root_files`, and `common_paths`.

Network, authentication, malformed-response, and missing-token failures are wrapped in `RepositoryReadError`. The existing GitHub search functions, API routes, and frontend remain unchanged.

## Verification

Unit tests use `httpx.MockTransport` to verify request paths, headers, decoding, path detection, and error handling. A smoke test invokes the function against `open-mmlab/mmsegmentation` with the configured token and reports only summary fields.
