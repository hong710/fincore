from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from tasks.models import Task


class TaskModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="owner", password="password"
        )

    def test_validation_enforced(self):
        task = Task(title="no", priority=6)
        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_complete_requires_permission(self):
        task = Task.objects.create(title="Ship release", priority=2)
        with self.assertRaises(PermissionDenied):
            task.complete(self.user)

        permission = Permission.objects.get(codename="can_mark_done")
        self.user.user_permissions.add(permission)
        task.complete(self.user)
        task.refresh_from_db()
        self.assertTrue(task.is_completed)
