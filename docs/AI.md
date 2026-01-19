# AI Notes

## Accounts: Create modal not closing

Symptoms
- Clicking "Create Account" creates the account but modal stays open.

Root cause
- The create modal relied only on `accounts:createClose` (from `HX-Trigger`) to close.
- HTMX does not emit the `HX-Trigger` header on a `204` response, so the close event never fires.

Fix
- Close the modal on successful HTMX request as well.
- Add a direct handler on the create form:
  - `@htmx:after-request.camel="if ($event.detail.xhr.status === 204) createOpen = false"`

Location
- `backend/fincore/templates/fincore/accounts/index.html`
