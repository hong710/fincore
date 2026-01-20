from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fincore", "0009_vendor"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="is_locked",
            field=models.BooleanField(
                default=False,
                help_text="Prevents edits; set when reconciled or paired as a transfer.",
            ),
        ),
    ]
