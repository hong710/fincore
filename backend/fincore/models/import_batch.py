from django.db import models


class ImportBatch(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("validated", "Validated"),
        ("imported", "Imported"),
        ("failed", "Failed"),
    ]

    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    filename = models.CharField(max_length=255)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.filename} ({self.status})"
