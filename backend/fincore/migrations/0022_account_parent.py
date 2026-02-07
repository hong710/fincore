from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("fincore", "0021_add_category_kind_payroll"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="fincore.account",
            ),
        ),
    ]
