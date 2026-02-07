from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("fincore", "0018_invoiceitem_tax_exempt"),
    ]

    operations = [
        migrations.CreateModel(
            name="Bill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=32, unique=True)),
                ("date", models.DateField()),
                ("status", models.CharField(choices=[("draft", "Draft"), ("received", "Received"), ("partially_paid", "Partially paid"), ("paid", "Paid"), ("void", "Void")], default="draft", max_length=20)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bills", to="fincore.account")),
                ("vendor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bills", to="fincore.vendor")),
            ],
            options={
                "ordering": ["-date", "-id"],
            },
        ),
        migrations.CreateModel(
            name="BillItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(blank=True, max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("bill", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="fincore.bill")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bill_items", to="fincore.category")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="BillPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("matched_at", models.DateTimeField(auto_now_add=True)),
                ("bill", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="fincore.bill")),
                ("transaction", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bill_payments", to="fincore.transaction")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("bill", "transaction"), name="uniq_bill_transaction_payment")
                ],
            },
        ),
    ]
