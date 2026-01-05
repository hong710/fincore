from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fincore", "0004_transaction_import_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="account_type",
            field=models.CharField(
                choices=[
                    ("checking", "Checking"),
                    ("savings", "Savings"),
                    ("credit_card", "Credit Card"),
                    ("cash", "Cash"),
                    ("loan", "Loan"),
                ],
                default="checking",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="institution",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
