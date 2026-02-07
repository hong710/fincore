from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fincore", "0020_category_parent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="category",
            name="kind",
            field=models.CharField(
                choices=[
                    ("income", "Income"),
                    ("expense", "Expense"),
                    ("payroll", "Payroll"),
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
    ]

