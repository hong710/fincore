from django.db import models
from .account import Account


class ImportBatch(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("validated", "Validated"),
        ("imported", "Imported"),
        ("failed", "Failed"),
    ]

    AMOUNT_STRATEGY_CHOICES = [
        ("signed", "Signed Amount"),
        ("indicator", "Amount + Indicator"),
        ("split_columns", "Debit / Credit Columns"),
    ]

    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    filename = models.CharField(max_length=255)
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="import_batches",
    )
    amount_strategy = models.CharField(
        max_length=15,
        choices=AMOUNT_STRATEGY_CHOICES,
        default="signed",
    )
    indicator_credit_value = models.CharField(max_length=100, blank=True, default="")
    indicator_debit_value = models.CharField(max_length=100, blank=True, default="")
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.filename} ({self.status})"
