from django.db import migrations, models


def mark_protected_categories(apps, schema_editor):
    Category = apps.get_model("fincore", "Category")
    Category.objects.filter(kind__in=["transfer", "opening"]).update(is_protected=True)


class Migration(migrations.Migration):

    dependencies = [
        ("fincore", "0010_transaction_is_locked"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="is_protected",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="category",
            name="kind",
            field=models.CharField(
                choices=[
                    ("income", "Income"),
                    ("expense", "Expense"),
                    ("transfer", "Transfer"),
                    ("opening", "Opening"),
                    ("withdraw", "Withdraw"),
                    ("equity", "Equity"),
                    ("liability", "Liability"),
                    ("cogs", "COGS"),
                ],
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="kind",
            field=models.CharField(
                choices=[
                    ("income", "Income"),
                    ("expense", "Expense"),
                    ("transfer", "Transfer"),
                    ("opening", "Opening"),
                    ("withdraw", "Withdraw"),
                    ("equity", "Equity"),
                    ("liability", "Liability"),
                    ("cogs", "COGS"),
                ],
                max_length=12,
            ),
        ),
        migrations.RunPython(mark_protected_categories, migrations.RunPython.noop),
    ]
