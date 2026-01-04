from django.contrib import admin

from tasks.models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "priority", "status", "created_at")
    list_filter = ("status", "priority")
    search_fields = ("title", "description")
