# Testing strategy

- **Unit tests (Django TestCase/pytest).** Live in `backend/fincore/tests/`. Cover models (`clean`, permissions), views (HTMX responses, headers), and permission helpers.
- **HTMX behavior.** Assert `HX-Trigger` headers and partial rendering (`HX-Request` header in tests). Keep endpoints small to simplify assertions.
- **Forms/validation.** Prefer `form.full_clean()` tests plus view tests that return 400 with the rendered form partial.
- **Permissions.** Centralize checks in domain apps (e.g., `tasks/permissions.py`) and test them directly. Model methods (e.g., `Task.complete`) also enforce permissions.
- **Storybook/manual QA.** Use `cd frontend && npm run storybook` to inspect visual regressions. Pair with Tailwind classes to keep snapshots readable.
- **CI suggestion.** Run `cd frontend && npm run build` and `pytest` in CI before building the Docker image; fail fast on linting/formatting issues if added later.
