from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("fincore", "0003_account_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="import_batch",
            field=models.ForeignKey(
                blank=True,
                help_text="Nullable link to the import batch that created these rows.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="transactions",
                to="fincore.importbatch",
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="is_imported",
            field=models.BooleanField(default=False, help_text="True when created from CSV import; manual/system otherwise."),
        ),
    ]
