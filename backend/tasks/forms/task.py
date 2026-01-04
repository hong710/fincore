from django import forms

from tasks.models import Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "priority"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-gray-200",
                    "placeholder": "Write a clear title",
                    "required": True,
                    "hx-trigger": "change delay:200ms",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "block w-full rounded-lg border-gray-200",
                    "rows": 3,
                }
            ),
            "priority": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-gray-200",
                    "min": 1,
                    "max": 5,
                }
            ),
        }

    def clean_title(self):
        title = self.cleaned_data["title"]
        if "placeholder" in title.lower():
            raise forms.ValidationError("Use actionable titles instead of placeholders.")
        return title
