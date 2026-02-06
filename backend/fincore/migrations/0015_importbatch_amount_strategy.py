from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fincore", "0014_invoice_status_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="importbatch",
            name="amount_strategy",
            field=models.CharField(
                choices=[
                    ("signed", "Signed Amount"),
                    ("indicator", "Amount + Indicator"),
                    ("split_columns", "Debit / Credit Columns"),
                ],
                default="signed",
                max_length=15,
            ),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="indicator_credit_value",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="importbatch",
            name="indicator_debit_value",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
