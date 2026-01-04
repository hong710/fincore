# Components and UI patterns

## Adding a new server-rendered component
1. Model/validation first: add fields and validation to your Django model/form.
2. Create a template partial under `backend/fincore/templates/fincore/components/` (or partials) and keep it data-focused.
3. Add a view that returns the partial for HTMX (e.g., `hx-get` to refresh a table or `hx-post` for form submissions).
4. Wire HTMX in the template via `hx-get`/`hx-post`, set `hx-target` and `hx-swap`, and emit `HX-Trigger` events from the view to keep clients decoupled.
5. If the component needs interactive UI (modal, tabs), add the correct Preline data attributes. Avoid writing bespoke JS.
6. For client-side polish (e.g., inline validation), add minimal Alpine state inside the template. Never bypass server validation.

## Storybook
- Add stories in `frontend/storybook/` as HTML functions. Import the same Tailwind/Preline/Alpine setup (already loaded in `preview.js`). Use `pages/` for full-page mocks, `layout/` (if added later) for shared frames, and component stories elsewhere.
- Keep story states explicit: empty/loading/error/valid to document server-driven flows.

## Styling
- Tailwind utilities are available via Vite. Purge content covers Django templates, frontend sources, and Storybook.
- Shared styles live in `frontend/src/css/styles.css`. Add small component classes in `@layer components` if repeated often.

## HTMX patterns
- Use `hx-get` with `hx-trigger="load, event from:body"` to refresh regions when the server emits events.
- Always include CSRF headers (base template wires this globally).
- Keep endpoints focused: one view per partial, return 4xx for validation errors, and set `HX-Trigger` to notify other regions.
