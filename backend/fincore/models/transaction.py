from django.db import models
from .account import Account
from .category import Category
from .transfer_group import TransferGroup


class Transaction(models.Model):
    """
    Core financial event stored as a single entry.
    Kind rules:
    - income: amount > 0, category required
    - expense: amount < 0, category required
    - transfer: category null, transfer_group required, paired to sum zero
    - opening: system initialization; not real income/expense; excluded from P&L
    """

    KIND_CHOICES = [
        ("income", "Income"),
        ("expense", "Expense"),
        ("transfer", "Transfer"),
        ("opening", "Opening"),
    ]

    SOURCE_CHOICES = [
        ("manual", "Manual"),
        ("csv", "CSV Import"),
    ]

    date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    kind = models.CharField(max_length=8, choices=KIND_CHOICES)
    payee = models.CharField(max_length=255, blank=True, help_text="Other party involved; free text; direction determined by kind/amount.")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    transfer_group = models.ForeignKey(TransferGroup, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    description = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=6, choices=SOURCE_CHOICES, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date} {self.kind} {self.amount} {self.account}"
