# State management rules

- **Server first.** Django models/forms enforce business rules and validation. Client-side checks are for UX only.
- **HTMX scope.** Use HTMX strictly for transporting HTML fragments and triggering partial swaps (`hx-get`, `hx-post`). Keep responses small and cache-friendly.
- **Alpine.js scope.** Use Alpine for transient UI state (field validation, toggles, tab visibility). Never read or mutate business data that is not already rendered by Django.
- **Preline behavior.** Prefer Preline data attributes (`data-hs-overlay`, tabs, dropdowns) to custom JavaScript. Re-initialize via `HSStaticMethods.autoInit()` after HTMX swaps (already wired in `frontend/src/main.js`).
- **Events instead of coupling.** Trigger `HX-Trigger` events from views to let the client decide what to refresh. Example: `task-added` refreshes the table via a declarative `hx-get`.
- **Permissions live on the server.** Use helpers from domain apps (e.g., `tasks/permissions.py`) and model methods (e.g., `Task.complete`) so UI layers never guess who can do what.
