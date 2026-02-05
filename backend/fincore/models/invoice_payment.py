from django.db import models

from .invoice import Invoice
from .transaction import Transaction


class InvoicePayment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    transaction = models.ForeignKey(
        Transaction, on_delete=models.PROTECT, related_name="invoice_payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    matched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "transaction"], name="uniq_invoice_transaction_payment"
            )
        ]

    def __str__(self):
        return f"{self.invoice.number} ↔ {self.transaction_id} {self.amount}"
