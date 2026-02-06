from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fincore", "0017_invoice_tax_rate_lock"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceitem",
            name="tax_exempt",
            field=models.BooleanField(default=False),
        ),
    ]
