from django.db import models


class Account(models.Model):
    """
    Where money lives. Balance is always derived (no stored balance column).
    """

    ACCOUNT_TYPES = [
        ("checking", "Checking"),
        ("savings", "Savings"),
        ("credit_card", "Credit Card"),
        ("cash", "Cash"),
        ("loan", "Loan"),
    ]

    name = models.CharField(max_length=100, unique=True)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default="checking")
    institution = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Archive instead of delete. Inactive accounts stay in history but are not selectable for new activity.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def delete(self, using=None, keep_parents=False):
        """
        Enforce archival for accounts with history. If transactions exist, prevent hard delete.
        """
        if hasattr(self, "transactions") and self.transactions.exists():
            raise models.ProtectedError("Cannot delete account with transactions; archive via is_active.", [self])
        return super().delete(using=using, keep_parents=keep_parents)

    def __str__(self):
        return self.name
