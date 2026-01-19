from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fincore", "0007_category_kind_and_backfill"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
