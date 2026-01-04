from django.db import models


class Account(models.Model):
    """
    Where money lives. Balance is always derived (no stored balance column).
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
