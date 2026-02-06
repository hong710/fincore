from django.db import models
from .account import Account
from .category import Category
from .transfer_group import TransferGroup
from .vendor import Vendor
from .import_batch import ImportBatch


class Transaction(models.Model):
    """
    Core financial event stored as a single entry.
    Kind rules:
    - income: amount > 0, category required
    - expense: amount < 0, category required
    - transfer: category required, transfer_group required, paired to sum zero
    - opening: category required; not real income/expense; excluded from P&L
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

    SOURCE_CHOICES = [
        ("manual", "Manual"),
        ("csv", "CSV Import"),
    ]

    date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    payee = models.CharField(max_length=255, blank=True, help_text="Other party involved; free text; direction determined by kind/amount.")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    transfer_group = models.ForeignKey(TransferGroup, on_delete=models.PROTECT, null=True, blank=True, related_name="transactions")
    is_imported = models.BooleanField(default=False, help_text="True when created from CSV import; manual/system otherwise.")
    is_locked = models.BooleanField(default=False, help_text="Prevents edits; set when reconciled or paired as a transfer.")
    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Nullable link to the import batch that created these rows.",
    )
    description = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=6, choices=SOURCE_CHOICES, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def save(self, *args, **kwargs):
        if not self.is_imported and self.kind != "transfer" and not self.category_id:
            raise ValueError("Category is required for non-imported transactions.")
        if self.category_id and self.kind != "transfer":
            self.kind = self.category.kind
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} {self.kind} {self.amount} {self.account}"

    @property
    def invoice_display_label(self):
        payments = list(self.invoice_payments.all())
        if not payments:
            return None
        if len(payments) == 1:
            number = payments[0].invoice.number
            suffix = number.split("-")[-1] if "-" in number else number
            return f"INV-{suffix}"
        return "Invoice Payment (Multiple)"

    @property
    def invoice_display_link(self):
        payments = list(self.invoice_payments.all())
        if len(payments) == 1:
            return payments[0].invoice_id
        return None
