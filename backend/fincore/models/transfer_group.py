from django.db import models


class TransferGroup(models.Model):
    """
    Groups paired transfer transactions; used for audit and future double-entry migration.
    """

    reference = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference
