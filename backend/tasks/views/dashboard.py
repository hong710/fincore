from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from tasks.forms import TaskForm
from tasks.models import Task
from tasks.permissions import assert_can_complete, can_manage_tasks


@login_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    form = TaskForm()
    tasks = Task.objects.all()
    return render(
        request,
        "tasks/dashboard.html",
        {
            "form": form,
            "tasks": tasks,
        },
    )


@login_required
@require_POST
def create_task(request: HttpRequest) -> HttpResponse:
    if not can_manage_tasks(request.user):
        return HttpResponseForbidden("You do not have permission to add tasks.")

    form = TaskForm(request.POST)
    if form.is_valid():
        task = form.save()
        messages.success(request, "Task created.")
        if request.htmx:
            html = render_to_string(
                "tasks/components/task_form.html",
                {"form": TaskForm()},
                request=request,
            )
            return HttpResponse(html, headers={"HX-Trigger": "task-added"})
        return redirect("tasks:dashboard")

    if request.htmx:
        html = render_to_string(
            "tasks/components/task_form.html", {"form": form}, request=request
        )
        return HttpResponseBadRequest(html)

    return render(
        request,
        "tasks/dashboard.html",
        {"form": form, "tasks": Task.objects.all()},
        status=400,
    )


@login_required
@require_POST
def complete_task(request: HttpRequest, pk: int) -> HttpResponse:
    task = get_object_or_404(Task, pk=pk)
    assert_can_complete(request.user, task)
    task.complete(request.user)
    messages.info(request, f"Marked '{task.title}' as done.")

    if request.htmx:
        html = render_to_string(
            "tasks/components/task_row.html", {"task": task}, request=request
        )
        return HttpResponse(html, headers={"HX-Trigger": "task-updated"})

    return redirect("tasks:dashboard")


@login_required
@require_GET
def task_table(request: HttpRequest) -> HttpResponse:
    tasks = Task.objects.all()
    html = render_to_string("tasks/components/task_table.html", {"tasks": tasks}, request=request)
    return HttpResponse(html)
