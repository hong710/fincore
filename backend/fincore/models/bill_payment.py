from django.db import models
from .bill import Bill
from .transaction import Transaction


class BillPayment(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="payments")
    transaction = models.ForeignKey(
        Transaction, on_delete=models.PROTECT, related_name="bill_payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    matched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bill", "transaction"], name="uniq_bill_transaction_payment"
            )
        ]

    def __str__(self):
        return f"{self.bill.number} ↔ {self.transaction_id} {self.amount}"
