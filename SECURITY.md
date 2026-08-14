# Security Policy

## Reporting a Vulnerability

Please report security issues privately to the project maintainer before opening a public issue. Include a short description, affected component, reproduction steps that do not contain secrets, and the potential impact.

Do not send:

- GitHub tokens
- DeepSeek or other API keys
- Authorization headers
- `.env` files or their contents
- Private repository data
- Unredacted logs or screenshots

## Credential Safety

Credentials belong in a local `.env` file only. The repository and Docker images must contain placeholders, never real values. If a credential is exposed, revoke it immediately at the provider and create a replacement.

The Validation Worker uses a separate random token generated on every project
start. The token is inherited by the backend container and Worker process only.
Do not copy it into `.env`, logs, screenshots, issues, commits, or images.

## Runtime Validation Boundary

The host Validation Worker has the current local user's Docker permissions, but
it accepts only server-issued jobs containing a validated public repository
name. It does not accept arbitrary commands, image names, mount paths, resource
limits, or environment variables. The Worker opens no listening port.

Mounting the host Docker socket into the backend, using privileged containers,
or exposing the internal Worker endpoints without bearer-token authentication
is unsupported. This is a local or trusted-LAN self-hosted tool, not a public
multi-tenant code execution service.

## Scope

The application analyzes public GitHub repository metadata and user-selected repository files. Runtime validation is isolated and resource-limited, but users should still run the application on a machine they control, keep Docker Desktop updated, and trigger validation only for repositories they intentionally selected.
