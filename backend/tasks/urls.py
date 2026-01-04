from django.urls import path

from tasks import views

app_name = "tasks"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tasks/", views.task_table, name="task-table"),
    path("tasks/create/", views.create_task, name="create-task"),
    path("tasks/<int:pk>/complete/", views.complete_task, name="complete-task"),
]
