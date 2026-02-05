from decimal import Decimal

from django.db import models
from django.db.models import Sum
from .account import Account
from .vendor import Vendor


class Invoice(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("partially_paid", "Partially paid"),
        ("paid", "Paid"),
        ("void", "Void"),
    ]

    number = models.CharField(max_length=32, unique=True)
    customer = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="invoices")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="invoices")
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.number} {self.customer} {self.total}"

    @property
    def paid_amount(self):
        total = self.payments.aggregate(total=Sum("amount"))["total"]
        return total or Decimal("0.00")

    @property
    def remaining_balance(self):
        return (self.total - self.paid_amount).quantize(Decimal("0.01"))

    def update_status_from_payments(self):
        paid = self.paid_amount
        if paid <= 0:
            if self.status not in {"draft", "sent"}:
                self.status = "sent"
            return
        if paid >= self.total:
            self.status = "paid"
        else:
            self.status = "partially_paid"
