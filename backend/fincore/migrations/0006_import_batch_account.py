from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("fincore", "0005_account_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="importbatch",
            name="account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="import_batches",
                to="fincore.account",
            ),
        ),
    ]
