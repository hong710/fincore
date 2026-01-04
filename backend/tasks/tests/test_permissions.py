from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from tasks.permissions import can_manage_tasks, can_mark_done


class PermissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="owner", password="password"
        )

    def test_manage_requires_add_and_change(self):
        self.assertFalse(can_manage_tasks(self.user))
        perms = Permission.objects.filter(codename__in=["add_task", "change_task"])
        self.user.user_permissions.set(perms)
        self.assertTrue(can_manage_tasks(self.user))

    def test_mark_done_permission(self):
        self.assertFalse(can_mark_done(self.user))
        perm = Permission.objects.get(codename="can_mark_done")
        self.user.user_permissions.add(perm)
        self.assertTrue(can_mark_done(self.user))
