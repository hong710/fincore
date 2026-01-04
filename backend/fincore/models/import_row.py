from django.db import models
from .import_batch import ImportBatch


class ImportRow(models.Model):
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    raw_row = models.JSONField()
    mapped = models.JSONField(default=dict)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Row {self.id} in {self.batch_id}"
