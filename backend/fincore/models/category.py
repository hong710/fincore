from django.db import models


class Category(models.Model):
    """
    Categories apply only to income/expense. Transfers never reference categories.
    """

    KIND_CHOICES = [
        ("income", "Income"),
        ("expense", "Expense"),
    ]

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=7, choices=KIND_CHOICES)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "kind")
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.kind})"
