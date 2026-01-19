from django.db import migrations, models


def backfill_category_kinds(apps, schema_editor):
    Category = apps.get_model("fincore", "Category")
    Transaction = apps.get_model("fincore", "Transaction")

    defaults = {
        "transfer": "Transfer",
        "opening": "Opening",
    }
    categories = {}
    for kind, name in defaults.items():
        category, _created = Category.objects.get_or_create(name=name, kind=kind)
        categories[kind] = category

    for kind, category in categories.items():
        Transaction.objects.filter(
            kind=kind, category__isnull=True, is_imported=False
        ).update(category=category)

    for category in Category.objects.all():
        Transaction.objects.filter(category_id=category.id).exclude(
            kind=category.kind
        ).update(kind=category.kind)


class Migration(migrations.Migration):
    dependencies = [
        ("fincore", "0006_import_batch_account"),
    ]

    operations = [
        migrations.AlterField(
            model_name="category",
            name="kind",
            field=models.CharField(
                choices=[
                    ("income", "Income"),
                    ("expense", "Expense"),
                    ("transfer", "Transfer"),
                    ("opening", "Opening"),
                ],
                max_length=8,
            ),
        ),
        migrations.RunPython(backfill_category_kinds, migrations.RunPython.noop),
    ]
