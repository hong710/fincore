from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("fincore", "0008_category_is_active"),
    ]

    operations = [
        migrations.CreateModel(
            name="Vendor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("kind", models.CharField(choices=[("payer", "Payer"), ("payee", "Payee")], max_length=8)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["kind", "name"],
                "unique_together": {("name", "kind")},
            },
        ),
        migrations.AddField(
            model_name="transaction",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="transactions",
                to="fincore.vendor",
            ),
        ),
    ]
