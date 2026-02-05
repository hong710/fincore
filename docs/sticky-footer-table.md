# Sticky Footer Table Pattern

## Problem
When displaying tabular reports with a total row:
- Total row appears directly after last data row
- With few rows (1-3), total floats near the top instead of anchoring to bottom
- With many rows, total scrolls away and becomes invisible
- Bad UX for accounting/financial reports

## Solution
Use **semantic HTML + Tailwind flexbox** to create a professional sticky-footer table pattern.

### Structure (HTML)

```html
<div class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm flex flex-col flex-1 min-h-[calc(100vh-260px)]">
  <table class="w-full h-full flex flex-col">
    
    <!-- Fixed header -->
    <thead class="flex-shrink-0 sticky top-0 z-20 bg-slate-50 text-xs font-medium text-slate-700 border-b border-slate-200">
      <tr class="flex w-full">
        <th class="py-2 px-4 text-left flex-1">Column 1</th>
        <th class="py-2 px-4 text-left flex-1">Column 2</th>
        <!-- more columns -->
      </tr>
    </thead>

    <!-- Scrollable body -->
    <tbody class="flex-1 overflow-y-auto divide-y divide-slate-200 min-h-0">
      {% for row in rows %}
        <tr class="flex w-full hover:bg-slate-50">
          <td class="px-4 py-2 flex-1">{{ row.col1 }}</td>
          <td class="px-4 py-2 flex-1">{{ row.col2 }}</td>
        </tr>
      {% endfor %}
    </tbody>

    <!-- Fixed footer (total row) -->
    <tfoot class="flex-shrink-0 sticky bottom-0 z-10 bg-slate-50 font-semibold border-t-2 border-slate-300">
      <tr class="flex w-full">
        <td class="px-4 py-2 flex-1">Total</td>
        <td class="px-4 py-2 text-right flex-1">{{ total_amount|floatformat:2 }}</td>
      </tr>
    </tfoot>

  </table>
</div>
```

### Key Classes Explained

| Class | Purpose |
|-------|---------|
| `flex flex-col` | Makes table/container flexbox with column direction |
| `flex-1` | Column/cell takes equal share of width; tbody takes all vertical space |
| `flex-shrink-0` | Header & footer don't shrink; maintain fixed height |
| `sticky top-0 / bottom-0` | Stays fixed relative to scroll viewport |
| `z-20 / z-10` | Stack order: header on top, footer below data |
| `overflow-y-auto` | Body scrolls vertically; header/footer stay fixed |
| `min-h-0` | Critical for flex children to shrink below content size |
| `h-full` | Table fills container height |
| `w-full` | 100% width for table |

### How It Works

1. **Container** (`flex flex-col flex-1`): Occupies full available space
2. **Table** (`h-full flex flex-col`): Fills container height using flexbox
3. **Header** (`flex-shrink-0 sticky top-0`): 
   - Won't shrink, maintains natural height
   - Stays at top when scrolling
4. **Body** (`flex-1 overflow-y-auto min-h-0`):
   - Takes all remaining space (`flex-1`)
   - Scrolls when content overflows (`overflow-y-auto`)
   - `min-h-0` allows flex to shrink below content size
5. **Footer** (`flex-shrink-0 sticky bottom-0`):
   - Won't shrink, maintains natural height
   - Stays at bottom of table viewport
   - Always visible

### Result

- **1 row**: Empty space above data → total at bottom ✓
- **3 rows**: Data rows visible → total at bottom ✓
- **1000 rows**: Data scrolls, header/footer pinned → total always visible ✓
- No overlap, no layout jumps, professional appearance

### Server Integration (Django + HTMX)

**Backend** calculates total and passes to context:
```python
total_amount = qs.aggregate(total=Sum("amount"))["total"] or 0
return render(request, "template.html", {"total_amount": total_amount})
```

**HTMX responses** re-render tbody + tfoot to reflect filtered data:
```html
<!-- Apply button triggers partial update -->
<button hx-get="/api/endpoint/" hx-target="tbody" hx-swap="innerHTML">Apply</button>
```

### Do's ✓
- Use semantic `<thead>`, `<tbody>`, `<tfoot>`
- Calculate totals server-side
- Re-render tbody + tfoot on filter changes
- Use flexbox + sticky positioning
- Ensure rows use `flex` + `flex-1` for consistent column widths

### Don'ts ✗
- Don't put total row in tbody
- Don't calculate totals client-side
- Don't use absolute positioning hacks
- Don't add JavaScript scroll listeners
- Don't let footer float/reposition on fewer rows

### When to Use
- Accounting reports (P&L, categories, transactions)
- Any report with summary/total rows
- Professional financial dashboards
- Any paginated table needing visible totals

### Testing
1. Filter to show 1 row → total should anchor to bottom ✓
2. Show 3 rows → total at bottom ✓
3. Show 50+ rows → scroll and verify total stays visible ✓
4. Apply filter → total updates correctly ✓
