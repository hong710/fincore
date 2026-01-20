from django.db import models


class Vendor(models.Model):
    KIND_CHOICES = [
        ("payer", "Payer"),
        ("payee", "Payee"),
    ]

    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=8, choices=KIND_CHOICES)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "kind")
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.kind})"
