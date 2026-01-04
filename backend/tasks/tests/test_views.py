from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from tasks.models import Task


class TaskViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="casey", password="password", email="casey@example.com"
        )
        perms = Permission.objects.filter(
            codename__in=["add_task", "change_task", "can_mark_done"]
        )
        self.user.user_permissions.set(perms)
        self.client.login(username="casey", password="password")

    def test_dashboard_loads(self):
        response = self.client.get(reverse("tasks:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Server-driven task board")

    def test_create_task_htmx(self):
        response = self.client.post(
            reverse("tasks:create-task"),
            data={"title": "Plan launch", "priority": 3},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Task.objects.filter(title="Plan launch").exists())
        self.assertIn("HX-Trigger", response.headers)
        self.assertContains(response, "Create task")

    def test_complete_task_htmx(self):
        task = Task.objects.create(title="QA", priority=2)
        response = self.client.post(
            reverse("tasks:complete-task", kwargs={"pk": task.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertTrue(task.is_completed)
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn("Done", response.content.decode())
