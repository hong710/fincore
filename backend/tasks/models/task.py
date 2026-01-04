from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.PositiveSmallIntegerField(default=3)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("can_mark_done", "Can mark tasks as done"),
        ]

    def clean(self) -> None:
        if len(self.title.strip()) < 3:
            raise ValidationError({"title": "Title must be at least 3 characters long."})
        if not 1 <= self.priority <= 5:
            raise ValidationError({"priority": "Priority must be between 1 and 5."})

    def complete(self, user=None) -> None:
        if user and not user.has_perm("tasks.can_mark_done"):
            raise PermissionDenied("You cannot mark this task as done.")
        self.status = self.Status.DONE
        self.save(update_fields=["status", "updated_at"])

    @property
    def is_completed(self) -> bool:
        return self.status == self.Status.DONE

    def __str__(self) -> str:
        return self.title
