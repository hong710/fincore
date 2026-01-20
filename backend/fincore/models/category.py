from django.db import models


class Category(models.Model):
    """
    Categories define transaction kind, including transfer/opening.
    """

    KIND_CHOICES = [
        ("income", "Income"),
        ("expense", "Expense"),
        ("transfer", "Transfer"),
        ("opening", "Opening"),
        ("withdraw", "Withdraw"),
        ("equity", "Equity"),
        ("liability", "Liability"),
        ("cogs", "COGS"),
    ]

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_protected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "kind")
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.kind})"
