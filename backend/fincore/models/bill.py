from decimal import Decimal

from django.db import models
from django.db.models import Sum
from .account import Account
from .vendor import Vendor


class Bill(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("received", "Received"),
        ("partially_paid", "Partially paid"),
        ("paid", "Paid"),
        ("void", "Void"),
    ]

    number = models.CharField(max_length=32, unique=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="bills")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="bills")
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.number} {self.total}"

    @property
    def paid_amount(self):
        value = self.payments.aggregate(total=Sum("amount"))["total"]
        return value or Decimal("0.00")

    @property
    def remaining_balance(self):
        return (self.total or Decimal("0.00")) - self.paid_amount

    def update_status_from_payments(self):
        remaining = self.remaining_balance
        if remaining <= Decimal("0.00") and self.total > Decimal("0.00"):
            self.status = "paid"
        elif remaining < self.total:
            self.status = "partially_paid"
