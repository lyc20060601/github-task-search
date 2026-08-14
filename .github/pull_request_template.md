## Summary

Describe the user-visible behavior and why the change is needed.

## Validation

- [ ] Backend tests pass, or this change does not affect the backend.
- [ ] Frontend tests and build pass, or this change does not affect the frontend.
- [ ] Docker Compose configuration remains valid.
- [ ] Documentation was updated when setup or behavior changed.

List the exact commands and results:

```text
command -> result
```

## Security Boundary

- [ ] No `.env`, token, API key, authorization header, private repository data, or local absolute path is included.
- [ ] Unfamiliar repository code is not executed on the host.
- [ ] Runtime Score and Compatibility Score remain separate.
- [ ] Any Docker Sandbox or Validation Worker change preserves least privilege and explicit user initiation.

## Known Limitations

List any failed/skipped checks, migration needs, or remaining risks. Write `None` when there are none.
