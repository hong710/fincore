# Profit & Loss Filter Behavior Fix

## Update (Auto-Apply Filters)
The Apply button was removed. Filters now submit immediately on change (server-rendered HTMX), and selected values are persisted via request params → context → selected state. No JS-only state is used.

## Original Problem (Before Auto-Apply)
The Apply button toggled/reset filters on every load, making it impossible to maintain filter state.

## Root Cause Analysis

The issue had three parts:

### 1. Navigation Link (`base.html`)
- The sidebar link was: `href="{% url 'fincore:profit_loss_report' %}?apply=0"`
- This URL parameter `?apply=0` told the backend "don't apply filters"

### 2. Backend Logic (`transaction_views.py`)
```python
def profit_loss_report(request):
    apply_filters = (request.GET.get("apply") or "").strip() == "1"
    # ... extract filter parameters from URL ...
    
    if not apply_filters:
        # Reset all filters to empty
        account_id = ""
        vendor_id = ""
        category_id = ""
        kind = "all"
```

### 3. Template Rendering (`profit_loss.html`)
- The template was **always** rendering form fields with context values
- Even when `apply_filters=False`, it would show the previous filter values in the form
- This created a "toggle" effect:
  - Click Apply → filters applied (apply=1)
  - Return to page → navigation link adds ?apply=0 → backend resets filters but template still shows old values
  - Click Apply again → same old values get applied

## Solution

### Change 1: Update Navigation Link
**File:** `backend/fincore/templates/fincore/base.html` (line 159)

**Before:**
```html
<a href="{% url 'fincore:profit_loss_report' %}?apply=0">
```

**After:**
```html
<a href="{% url 'fincore:profit_loss_report' %}">
```

### Change 2: Conditional Form Field Population
**File:** `backend/fincore/templates/fincore/reports/profit_loss.html`

Only populate form fields with context values **when `apply_filters=True`**:

```django
<!-- Report period select -->
<option value="{{ value }}" {% if apply_filters and date_range == value %}selected{% endif %}>
  {{ label }}
</option>

<!-- Account select -->
<option value="{{ account.id }}" 
  {% if apply_filters and account_id|add:'' == account.id|add:'' %}selected{% endif %}>
  {{ account.name }}
</option>
```

### Change 3: Improved Form Field Initialization
**File:** `backend/fincore/templates/fincore/reports/profit_loss.html`

Changed Alpine.js initialization to respect the apply_filters flag:

```javascript
x-data="{ range: '{% if apply_filters %}{{ date_range }}{% else %}this_year{% endif %}' }"
```

## Behavior After Fix

| Action | Behavior |
|--------|----------|
| Visit page fresh | All filter fields reset to defaults (no query params) |
| Set Account="test" + Vendor="test 9" | Form shows selections |
| Click Apply | URL becomes `?apply=1&account_id=X&vendor_id=Y...` Data filtered correctly |
| Navigate away and back | **Filters NOT preserved** (intentional - page loads fresh) |
| Click Clear Filters | All fields reset, URL cleaned |
| Click Apply again with new selections | Only new selections applied |

## Key Files Modified

1. `backend/fincore/templates/fincore/base.html` - Removed `?apply=0` from navigation link
2. `backend/fincore/templates/fincore/reports/profit_loss.html` - Added conditional form field population based on `apply_filters` flag
3. Backend view (`transaction_views.py`) - No changes needed; existing logic is correct

## Why This Works

- The `apply_filters` flag is **only true** when `apply=1` in URL
- When `apply=1`, form fields are populated with the active filter values
- When `apply != 1`, form fields always show defaults (empty/all)
- User explicitly clicks Apply to add `apply=1` to URL
- Clicking Clear Filters removes all query params
- Result: No more toggle; filters only apply when user explicitly sets and clicks Apply
