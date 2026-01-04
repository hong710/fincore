from django.contrib.auth.models import AbstractBaseUser

from tasks.models import Task


def can_manage_tasks(user: AbstractBaseUser) -> bool:
    """Centralized gate for creating/updating tasks."""
    if not user.is_authenticated:
        return False
    return user.has_perm("tasks.add_task") and user.has_perm("tasks.change_task")


def can_mark_done(user: AbstractBaseUser) -> bool:
    if not user.is_authenticated:
        return False
    return user.has_perm("tasks.can_mark_done")


def assert_can_complete(user: AbstractBaseUser, task: Task) -> None:
    if not can_mark_done(user):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("You do not have permission to complete tasks.")
