from decimal import Decimal

from django.db import migrations, models


def backfill_tax_rate(apps, schema_editor):
    Invoice = apps.get_model("fincore", "Invoice")
    for invoice in Invoice.objects.all().only("id", "subtotal", "tax_total"):
        subtotal = invoice.subtotal or Decimal("0.00")
        tax_total = invoice.tax_total or Decimal("0.00")
        if subtotal > 0 and tax_total > 0:
            rate = (tax_total / subtotal * Decimal("100")).quantize(Decimal("0.01"))
        else:
            rate = Decimal("0.00")
        Invoice.objects.filter(pk=invoice.pk).update(tax_rate=rate)


class Migration(migrations.Migration):
    dependencies = [
        ("fincore", "0016_uncategorized_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="tax_rate",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name="invoice",
            name="tax_exclude",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="invoice",
            name="is_locked",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_tax_rate, migrations.RunPython.noop),
    ]
