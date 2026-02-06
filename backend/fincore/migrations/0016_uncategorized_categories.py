from django.db import migrations


def create_uncategorized_categories(apps, schema_editor):
    Category = apps.get_model("fincore", "Category")
    Category.objects.get_or_create(
        name="Uncategorized Income",
        kind="income",
        defaults={"is_protected": True, "is_active": True},
    )
    Category.objects.get_or_create(
        name="Uncategorized Expense",
        kind="expense",
        defaults={"is_protected": True, "is_active": True},
    )


def remove_uncategorized_categories(apps, schema_editor):
    Category = apps.get_model("fincore", "Category")
    Category.objects.filter(
        name__in=["Uncategorized Income", "Uncategorized Expense"],
        is_protected=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("fincore", "0015_importbatch_amount_strategy"),
    ]

    operations = [
        migrations.RunPython(
            create_uncategorized_categories,
            remove_uncategorized_categories,
        ),
    ]
